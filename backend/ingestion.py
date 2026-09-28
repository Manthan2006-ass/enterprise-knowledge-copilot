import io
import json
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from starlette.concurrency import run_in_threadpool

import chromadb
from chromadb.utils import embedding_functions
from ollama import Client as OllamaClient
from pypdf import PdfReader
import docx

from database import db
from auth import get_current_user, to_object_id

router = APIRouter(prefix="/api/workspaces", tags=["ingestion"])

# Same collection instance/config as chat.py — must match exactly, since
# both files query and write to the same ChromaDB collection.
DB_PATH = "./chroma_db"
chroma_client = chromadb.PersistentClient(path=DB_PATH)

# Defaults to localhost for normal local dev. Inside Docker, "localhost"
# refers to THIS container, not the Ollama container - docker-compose
# overrides this via an environment variable to the service name instead
# (e.g. http://ollama:11434).
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Default timeout is too short for embedding large batches on CPU —
# without this, a big upload can crash with a ConnectionError/timeout
# partway through.
custom_ollama_client = OllamaClient(
    host=OLLAMA_BASE_URL,
    timeout=300.0,
)

ollama_ef = embedding_functions.OllamaEmbeddingFunction(
    url=f"{OLLAMA_BASE_URL}/api/embeddings",
    model_name="bge-m3:latest",
)
ollama_ef._client = custom_ollama_client

collection = chroma_client.get_or_create_collection(
    name="workspace_documents",
    embedding_function=ollama_ef,
    metadata={"hnsw:space": "cosine"},
)

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
BATCH_SIZE = 20


def extract_text(filename: str, content: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    elif lower.endswith(".docx"):
        document = docx.Document(io.BytesIO(content))
        return "\n".join(p.text for p in document.paragraphs)
    elif lower.endswith(".txt"):
        return content.decode("utf-8", errors="ignore")
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type. Use PDF, DOCX, or TXT.")


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return [c.strip() for c in chunks if c.strip()]


@router.post("/{workspace_id}/documents/upload")
async def upload_document(
    workspace_id: str,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
):
    # Ownership check — never trust workspace_id alone
    workspace = await db.workspaces.find_one({
        "_id": to_object_id(workspace_id, "workspace_id"),
        "user_id": user_id,
    })
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    content = await file.read()
    # PdfReader/docx.Document are synchronous, CPU-bound parsers — running
    # them directly inside this async def would freeze FastAPI's single
    # event loop, stalling every other user's streaming chat until parsing
    # finishes. run_in_threadpool moves the blocking work off the event loop.
    text = await run_in_threadpool(extract_text, file.filename, content)
    if not text.strip():
        raise HTTPException(status_code=400, detail="No extractable text found in file")

    chunks = await run_in_threadpool(chunk_text, text)
    if not chunks:
        raise HTTPException(status_code=400, detail="File produced no usable chunks")

    doc_id = str(uuid.uuid4())
    ids = [f"{doc_id}_{i}" for i in range(len(chunks))]
    metadatas = [
        {
            "user_id": user_id,
            "workspace_id": workspace_id,
            "source": file.filename,
            "chunk_index": i,
        }
        for i in range(len(chunks))
    ]

    # collection.add() makes a synchronous HTTP call to Ollama for embeddings
    # and writes to disk — also blocking, also moved off the event loop.
    for i in range(0, len(chunks), BATCH_SIZE):
        await run_in_threadpool(
            collection.add,
            documents=chunks[i:i + BATCH_SIZE],
            metadatas=metadatas[i:i + BATCH_SIZE],
            ids=ids[i:i + BATCH_SIZE],
        )

    await db.documents.insert_one({
        "workspace_id": workspace_id,
        "user_id": user_id,
        "filename": file.filename,
        "chunk_count": len(chunks),
        "doc_id": doc_id,
        "uploaded_at": datetime.now(timezone.utc),
    })

    return {
        "doc_id": doc_id,
        "filename": file.filename,
        "chunks_indexed": len(chunks),
        "message": "Document uploaded and indexed successfully",
    }


@router.get("/{workspace_id}/documents")
async def list_documents(
    workspace_id: str,
    user_id: str = Depends(get_current_user),
):
    # Allow access if owned OR public - anyone can SEE what's indexed in a
    # shared workspace, even though only the owner can upload into it.
    workspace = await db.workspaces.find_one({
        "_id": to_object_id(workspace_id, "workspace_id"),
        "$or": [
            {"user_id": user_id},
            {"is_public": True},
        ],
    })
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Filter by workspace_id ONLY, not also user_id - documents in a public
    # workspace were uploaded by the OWNER, not the current viewer, so
    # filtering by the viewer's own user_id would incorrectly return nothing
    # for anyone except the original uploader.
    cursor = db.documents.find({"workspace_id": workspace_id})
    docs = []
    async for d in cursor:
        docs.append({
            "doc_id": d["doc_id"],
            "filename": d["filename"],
            "chunk_count": d["chunk_count"],
            "uploaded_at": d["uploaded_at"],
        })
    return {"documents": docs}


@router.post("/{workspace_id}/documents/upload-transcript")
async def upload_transcript(
    workspace_id: str,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
):
    """
    Uploads a pre-transcribed JSON file (the output of mp3tojson.py + merge_chunks.py
    from the video-lecture pipeline) and indexes each chunk WITH its start/end
    timestamps, so chat.py can cite [Lecture XX at MM:SS] when answering from it.

    Expected JSON shape:
    {
      "chunks": [
        {"number": "12", "title": "Attention Mechanism", "start": 45.2, "end": 62.8, "text": "..."},
        ...
      ]
    }
    """
    workspace = await db.workspaces.find_one({
        "_id": to_object_id(workspace_id, "workspace_id"),
        "user_id": user_id,
    })
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    content = await file.read()
    try:
        data = await run_in_threadpool(json.loads, content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON transcript file")

    chunks = data.get("chunks", [])
    if not chunks:
        raise HTTPException(status_code=400, detail="No chunks found in transcript JSON")

    doc_id = str(uuid.uuid4())
    documents, metadatas, ids = [], [], []

    for i, chunk in enumerate(chunks):
        text = (chunk.get("text") or "").strip()
        if not text:
            continue
        documents.append(text)
        metadatas.append({
            "user_id": user_id,
            "workspace_id": workspace_id,
            "source": chunk.get("title", file.filename),
            "video_number": chunk.get("number", "unknown"),
            "video_title": chunk.get("title", file.filename),
            "start_time": float(chunk.get("start", 0)),
            "end_time": float(chunk.get("end", 0)),
            "chunk_index": i,
        })
        ids.append(f"{doc_id}_{i}")

    if not documents:
        raise HTTPException(status_code=400, detail="Transcript produced no usable text chunks")

    for i in range(0, len(documents), BATCH_SIZE):
        await run_in_threadpool(
            collection.add,
            documents=documents[i:i + BATCH_SIZE],
            metadatas=metadatas[i:i + BATCH_SIZE],
            ids=ids[i:i + BATCH_SIZE],
        )

    await db.documents.insert_one({
        "workspace_id": workspace_id,
        "user_id": user_id,
        "filename": file.filename,
        "chunk_count": len(documents),
        "doc_id": doc_id,
        "has_timestamps": True,
        "uploaded_at": datetime.now(timezone.utc),
    })

    return {
        "doc_id": doc_id,
        "filename": file.filename,
        "chunks_indexed": len(documents),
        "message": "Transcript uploaded and indexed with timestamps",
    }

