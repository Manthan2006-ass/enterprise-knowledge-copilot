import io
import json
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request
from starlette.concurrency import run_in_threadpool

from limiter import limiter
from pypdf import PdfReader
import docx

from database import db
from auth import get_current_user, to_object_id
from embedding_utils import embed_texts

router = APIRouter(prefix="/api/workspaces", tags=["ingestion"])

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
BATCH_SIZE = 20
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


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


def _embed_and_build_docs(chunks, metadatas, doc_id):
    """Synchronous helper: embed all chunks in batches and return MongoDB docs."""
    mongo_docs = []
    for i in range(0, len(chunks), BATCH_SIZE):
        batch_texts = chunks[i:i + BATCH_SIZE]
        batch_metas = metadatas[i:i + BATCH_SIZE]
        embeddings = embed_texts(batch_texts)
        for j, (text, meta, emb) in enumerate(zip(batch_texts, batch_metas, embeddings)):
            mongo_docs.append({
                **meta,
                "doc_id": doc_id,
                "chunk_index": i + j,
                "text": text,
                "embedding": emb,
            })
    return mongo_docs


@router.post("/{workspace_id}/documents/upload")
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
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
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 5MB.")

    text = await run_in_threadpool(extract_text, file.filename, content)
    if not text.strip():
        raise HTTPException(status_code=400, detail="No extractable text found in file")

    chunks = await run_in_threadpool(chunk_text, text)
    if not chunks:
        raise HTTPException(status_code=400, detail="File produced no usable chunks")

    doc_id = str(uuid.uuid4())
    base_meta = {
        "user_id": user_id,
        "workspace_id": workspace_id,
        "source": file.filename,
    }
    metadatas = [base_meta for _ in chunks]

    # Embed all chunks and build MongoDB docs (CPU-bound → run off event loop)
    mongo_docs = await run_in_threadpool(_embed_and_build_docs, chunks, metadatas, doc_id)
    if mongo_docs:
        await db.chunks.insert_many(mongo_docs)

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
    # Allow access if owned OR public
    workspace = await db.workspaces.find_one({
        "_id": to_object_id(workspace_id, "workspace_id"),
        "$or": [
            {"user_id": user_id},
            {"is_public": True},
        ],
    })
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

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
@limiter.limit("10/minute")
async def upload_transcript(
    request: Request,
    workspace_id: str,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
):
    """
    Uploads a pre-transcribed JSON file and indexes each chunk WITH its
    start/end timestamps into MongoDB Atlas Vector Search, so chat.py can
    cite [Lecture XX at MM:SS] when answering.

    Expected JSON shape:
    {
      "chunks": [
        {"number": "12", "title": "...", "start": 45.2, "end": 62.8, "text": "..."},
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
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Transcript file too large. Maximum size is 5MB.")

    try:
        data = await run_in_threadpool(json.loads, content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON transcript file")

    raw_chunks = data.get("chunks", [])
    if not raw_chunks:
        raise HTTPException(status_code=400, detail="No chunks found in transcript JSON")

    doc_id = str(uuid.uuid4())
    texts, metadatas = [], []

    for chunk in raw_chunks:
        text = (chunk.get("text") or "").strip()
        if not text:
            continue
        texts.append(text)
        metadatas.append({
            "user_id": user_id,
            "workspace_id": workspace_id,
            "source": chunk.get("title", file.filename),
            "video_number": str(chunk.get("number", "unknown")),
            "video_title": chunk.get("title", file.filename),
            "start_time": float(chunk.get("start", 0)),
            "end_time": float(chunk.get("end", 0)),
            "has_timestamps": True,
        })

    if not texts:
        raise HTTPException(status_code=400, detail="Transcript produced no usable text chunks")

    # Embed all chunks (CPU-bound → off event loop)
    mongo_docs = await run_in_threadpool(_embed_and_build_docs, texts, metadatas, doc_id)
    if mongo_docs:
        await db.chunks.insert_many(mongo_docs)

    await db.documents.insert_one({
        "workspace_id": workspace_id,
        "user_id": user_id,
        "filename": file.filename,
        "chunk_count": len(texts),
        "doc_id": doc_id,
        "has_timestamps": True,
        "uploaded_at": datetime.now(timezone.utc),
    })

    return {
        "doc_id": doc_id,
        "filename": file.filename,
        "chunks_indexed": len(texts),
        "message": "Transcript uploaded and indexed with timestamps",
    }
