import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from limiter import limiter

from database import db
from auth import get_current_user, to_object_id
from models import ChatPayloadSchema
from llm_provider import chat_completion_sync, chat_completion_stream
from embedding_utils import embed_query

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Cosine similarity threshold: results below this are treated as irrelevant.
# Atlas vectorSearch score ranges 0–1 (1 = identical, 0 = completely unrelated).
SIMILARITY_THRESHOLD = 0.30

# Atlas vector search index name (must match what you created in the Atlas UI
# or via the create_vector_index.py script).
VECTOR_INDEX_NAME = "vector_index"


def format_timestamp(seconds: float) -> str:
    """Converts raw seconds into MM:SS citation style."""
    minutes = int(seconds // 60)
    remaining_secs = int(seconds % 60)
    return f"{minutes:02d}:{remaining_secs:02d}"


# Words that signal a question depends on prior conversation context.
PRONOUNS = {"it", "this", "that", "these", "those", "they", "them", "he", "she", "his", "her"}


def needs_condensation(query: str) -> bool:
    tokens = set(query.lower().split())
    return bool(tokens & PRONOUNS) or len(tokens) <= 3


def condense_query(user_query: str, history: list) -> str:
    """Rewrites a multi-turn follow-up into a standalone search query."""
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

    return chat_completion_sync(
        messages=[{"role": "user", "content": condense_prompt}],
        temperature=0.0,
    )


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
    """Check whether ANY document has been uploaded to this workspace."""
    count = await db.documents.count_documents({"workspace_id": workspace_id})
    return count > 0


async def vector_search(query_text: str, workspace_id: str, n_results: int = 4) -> list[dict]:
    """
    Query MongoDB Atlas Vector Search.
    Returns a list of chunk dicts with keys: text, score, and all metadata fields.
    """
    # Embedding is synchronous (ONNX CPU inference) — run off event loop
    query_vector = await run_in_threadpool(embed_query, query_text)

    pipeline = [
        {
            "$vectorSearch": {
                "index": VECTOR_INDEX_NAME,
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": n_results * 10,
                "limit": n_results,
                "filter": {"workspace_id": {"$eq": workspace_id}},
            }
        },
        {
            "$project": {
                "_id": 0,
                "text": 1,
                "source": 1,
                "video_number": 1,
                "video_title": 1,
                "start_time": 1,
                "end_time": 1,
                "has_timestamps": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]

    results = []
    async for doc in db.chunks.aggregate(pipeline):
        results.append(doc)
    return results


async def stream_chat_response(user_id: str, thread_id: str, workspace_id: str | None, question: str):
    history = await get_recent_history(thread_id)

    has_docs = False
    if workspace_id is not None:
        has_docs = await workspace_has_documents(workspace_id)

    context_stream = ""
    has_timestamps = False

    if workspace_id is not None and has_docs:
        # Rewrite follow-up questions into standalone queries before vector search
        if history and needs_condensation(question):
            search_query = await run_in_threadpool(condense_query, question, history)
        else:
            search_query = question

        results = await vector_search(search_query, workspace_id, n_results=4)

        idx = 0
        for chunk in results:
            score = chunk.get("score", 0)
            if score < SIMILARITY_THRESHOLD:
                continue  # too dissimilar — drop it
            idx += 1
            if chunk.get("has_timestamps") and "start_time" in chunk and "end_time" in chunk:
                has_timestamps = True
                start_str = format_timestamp(chunk["start_time"])
                end_str = format_timestamp(chunk["end_time"])
                context_stream += (
                    f"\n--- Source {idx}: Lecture {chunk.get('video_number', '?')} - "
                    f"{chunk.get('video_title', chunk.get('source', 'unknown'))} "
                    f"[{start_str}-{end_str}] ---\n{chunk['text']}\n"
                )
            else:
                context_stream += f"\n--- Source {idx} ({chunk.get('source', 'unknown')}) ---\n{chunk['text']}\n"

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
        # Workspace WITH documents but nothing relevant retrieved for this query
        system_prompt = (
            "You are a document-based assistant for this workspace. No relevant "
            "information was found for this question. Tell the user clearly, in "
            "one or two sentences, that you don't have information on this in "
            "this workspace's documents, and suggest they upload relevant material "
            "or rephrase the question. Do not answer from general knowledge."
        )
        user_prompt = question
    else:
        # Normal Chat (no workspace) or workspace with zero documents — plain conversation
        system_prompt = "You are a helpful assistant."
        user_prompt = question

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_prompt})

    full_response = ""
    for token in chat_completion_stream(messages, temperature=0.0):
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
@limiter.limit("15/minute")
async def chat_stream(
    request: Request,
    body: ChatPayloadSchema,
    user_id: str = Depends(get_current_user),
):
    thread = await db.threads.find_one({
        "_id": to_object_id(body.thread_id, "thread_id"),
        "user_id": user_id,
    })
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

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
