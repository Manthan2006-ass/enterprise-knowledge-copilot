import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

import chromadb
from chromadb.utils import embedding_functions
from ollama import Client as OllamaClient

from database import db
from auth import get_current_user, to_object_id
from models import ChatPayloadSchema

router = APIRouter(prefix="/api/chat", tags=["chat"])

# -----------------------------
# Shared ChromaDB + embedding setup
# One collection for ALL workspaces — isolation is enforced via the
# user_id + workspace_id metadata filter on every query, never by
# trusting a client-supplied value.
# -----------------------------
DB_PATH = "./chroma_db"
chroma_client = chromadb.PersistentClient(path=DB_PATH)

# Defaults to localhost for normal local dev. Inside Docker, "localhost"
# refers to THIS container, not the Ollama container - docker-compose
# overrides this via an environment variable to the service name instead
# (e.g. http://ollama:11434).
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Default timeout is too short for embedding/generation on CPU under load —
# same fix applied in ingestion.py.
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

CHAT_MODEL = "llama3.2:3b"  # change to whatever model you've pulled in Ollama


def format_timestamp(seconds: float) -> str:
    """Converts raw seconds into MM:SS, matching the original playlist project's citation style."""
    minutes = int(seconds // 60)
    remaining_secs = int(seconds % 60)
    return f"{minutes:02d}:{remaining_secs:02d}"


# Words that signal a question depends on prior conversation context
# ("what about IT", "explain THIS more") and therefore needs rewriting into
# a standalone query before vector search. A short query (<=3 words) is
# also usually a follow-up shorthand ("go on", "why though").
PRONOUNS = {"it", "this", "that", "these", "those", "they", "them", "he", "she", "his", "her"}


def needs_condensation(query: str) -> bool:
    tokens = set(query.lower().split())
    return bool(tokens & PRONOUNS) or len(tokens) <= 3


def condense_query(user_query: str, history: list) -> str:
    """Rewrites a multi-turn follow-up into a standalone search query. Ported from incompress.py."""
    if not history:
        return user_query

    history_str = ""
    for msg in history[-4:]:
        history_str += f"{msg['role'].upper()}: {msg['content']}\n"

    condense_prompt = (
        "Given the following conversation history and a follow-up question, "
        "rephrase the follow-up question into a standalone query that can be used "
        "to search a vector database. Do NOT answer the question. Only return the rewritten query text.\n\n"
        f"Chat History:\n{history_str}\n"
        f"Follow-up Question: {user_query}\n"
        "Standalone Query:"
    )

    response = custom_ollama_client.chat(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": condense_prompt}],
        options={"temperature": 0.0},
    )
    return response["message"]["content"].strip()


async def get_recent_history(thread_id: str, limit: int = 8) -> list:
    """Pull the last few messages from Mongo to give the model conversational memory."""
    cursor = db.messages.find({"thread_id": thread_id}).sort("created_at", -1).limit(limit)
    msgs = []
    async for m in cursor:
        msgs.append({"role": m["role"], "content": m["content"]})
    msgs.reverse()  # oldest first
    return msgs


def sse_event(data: dict) -> str:
    """Format a dict as a proper Server-Sent Event line."""
    return f"data: {json.dumps(data)}\n\n"


async def workspace_has_documents(workspace_id: str) -> bool:
    """Checks whether ANY document has ever been uploaded to this workspace —
    independent of whether a specific query finds something relevant, and
    independent of WHO is currently asking. A public workspace's documents
    were uploaded by its owner, not necessarily the current viewer, so this
    must check by workspace_id alone - checking the viewer's own user_id too
    would incorrectly report "empty" for every non-owner."""
    count = await db.documents.count_documents({"workspace_id": workspace_id})
    return count > 0


async def stream_chat_response(user_id: str, thread_id: str, workspace_id: str | None, question: str):
    history = await get_recent_history(thread_id)

    # A workspace with zero documents uploaded behaves exactly like Normal
    # Chat — no retrieval, no refusal, just plain conversation. Grounding
    # only kicks in once at least one document exists in THIS workspace.
    has_docs = False
    if workspace_id is not None:
        has_docs = await workspace_has_documents(workspace_id)

    # Chunks with a cosine distance above this are treated as "not actually
    # relevant" and dropped, rather than being force-fed to the model just
    # because they were the closest of a bad set. Tune this if you find it's
    # too strict (dropping real matches) or too loose (letting noise through).
    DISTANCE_THRESHOLD = 1.0

    context_stream = ""
    has_timestamps = False

    if workspace_id is not None and has_docs:
        # Workspace thread WITH documents -> do RAG retrieval, scoped to this exact user + workspace
        # Only pay for an extra LLM inference pass when the question actually
        # looks like a follow-up ("what about it?", short shorthand). A
        # self-contained question searches with its own text directly,
        # roughly halving latency on CPU for the common case.
        if history and needs_condensation(question):
            search_query = condense_query(question, history)
        else:
            search_query = question

        results = collection.query(
            query_texts=[search_query],
            n_results=4,
            # Filtered by workspace_id ONLY. Access to this workspace was
            # already authorized when the thread was created (owner check
            # or is_public check in main.py's create_thread) - filtering
            # again by the CURRENT user's id here would incorrectly return
            # zero chunks for anyone chatting in a public workspace who
            # isn't the original document uploader.
            where={"workspace_id": workspace_id},
        )
        retrieved_docs = results.get("documents", [[]])[0]
        retrieved_meta = results.get("metadatas", [[]])[0]
        retrieved_dist = results.get("distances", [[]])[0]

        idx = 0
        for doc, meta, dist in zip(retrieved_docs, retrieved_meta, retrieved_dist):
            if dist > DISTANCE_THRESHOLD:
                continue  # too dissimilar to actually be relevant — drop it
            idx += 1
            if "start_time" in meta and "end_time" in meta:
                has_timestamps = True
                start_str = format_timestamp(meta["start_time"])
                end_str = format_timestamp(meta["end_time"])
                context_stream += (
                    f"\n--- Source {idx}: Lecture {meta.get('video_number', '?')} - "
                    f"{meta.get('video_title', meta.get('source', 'unknown'))} "
                    f"[{start_str}-{end_str}] ---\n{doc}\n"
                )
            else:
                context_stream += f"\n--- Source {idx} ({meta.get('source', 'unknown')}) ---\n{doc}\n"

    if workspace_id is not None and context_stream and has_timestamps:
        system_prompt = (
            "You are an expert AI Teaching Assistant for this workspace's video lecture playlist. "
            "Answer strictly using the provided transcript context blocks below — do not use outside "
            "or general knowledge. For every factual claim or concept you mention, you MUST cite the "
            "source in the exact format [Lecture XX at MM:SS], using the lecture number and start "
            "timestamp shown in the context block's [MM:SS-MM:SS] range (use the FIRST timestamp in "
            "that range). "
            "Example of the exact citation format required: [Lecture 11 at 03:15]. "
            "Always include the timestamp — never write just 'Lecture 11' or 'Source 1' without the "
            "'at MM:SS' part. If the context doesn't contain the answer, say exactly: "
            "\"I don't have information about this in this workspace's documents.\""
        )
        user_prompt = f"Context:\n{context_stream}\n\nQuestion: {question}"
    elif workspace_id is not None and context_stream:
        system_prompt = (
            "You are a document-based assistant for this specific workspace. "
            "Answer ONLY using the provided context below. Do not use any outside "
            "or general knowledge, even if you know the topic. If the context "
            "does not contain the answer, say exactly: "
            "\"I don't have information about this in this workspace's documents.\" "
            "Do not guess or fill gaps with your own knowledge."
        )
        user_prompt = f"Context:\n{context_stream}\n\nQuestion: {question}"
    elif workspace_id is not None and has_docs:
        # A workspace WITH documents, but nothing relevant was retrieved for
        # THIS query — refuse explicitly instead of silently answering from
        # general knowledge. This is different from an empty workspace below.
        system_prompt = (
            "You are a document-based assistant for this workspace. No relevant "
            "information was found for this question. Tell the user clearly, in "
            "one or two sentences, that you don't have information on this in "
            "this workspace's documents, and suggest they upload relevant material "
            "or rephrase the question. Do not answer from general knowledge."
        )
        user_prompt = question
    else:
        # Either true Normal Chat (workspace_id is None), or a workspace
        # with zero documents uploaded so far — both get plain conversation,
        # no retrieval, no refusal.
        system_prompt = "You are a helpful assistant."
        user_prompt = question

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_prompt})

    full_response = ""
    stream = custom_ollama_client.chat(
        model=CHAT_MODEL,
        messages=messages,
        options={"temperature": 0.0},
        stream=True,
    )

    for chunk in stream:
        token = chunk["message"]["content"]
        full_response += token
        yield sse_event({"token": token})

    # Persist the assistant's full reply once streaming is done
    await db.messages.insert_one({
        "user_id": user_id,
        "workspace_id": workspace_id,
        "thread_id": thread_id,
        "role": "assistant",
        "content": full_response,
        "created_at": datetime.now(timezone.utc),
    })

    yield sse_event({"done": True})


@router.post("/stream")
async def chat_stream(
    body: ChatPayloadSchema,
    user_id: str = Depends(get_current_user),
):
    # Confirm the thread exists and belongs to this user before doing anything else
    thread = await db.threads.find_one({
        "_id": to_object_id(body.thread_id, "thread_id"),
        "user_id": user_id,
    })
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Save the user's message immediately (don't wait for the stream to finish)
    await db.messages.insert_one({
        "user_id": user_id,
        "workspace_id": thread["workspace_id"],
        "thread_id": body.thread_id,
        "role": "user",
        "content": body.question,
        "created_at": datetime.now(timezone.utc),
    })

    return StreamingResponse(
        stream_chat_response(user_id, body.thread_id, thread["workspace_id"], body.question),
        media_type="text/event-stream",
    )
