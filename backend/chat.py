import asyncio
import json
import re
import time
from datetime import datetime, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from auth import get_current_user, to_object_id
from database import db
from embedding_utils import embed_query
from llm_provider import chat_completion_stream, chat_completion_sync

router = APIRouter(prefix="/api/chat", tags=["chat"])

PRONOUNS = {"it", "this", "that", "these", "those", "they", "them", "he", "she", "his", "her"}


def needs_condensation(query: str) -> bool:
    """Returns True only if the user query contains ambiguous pronouns or shorthand tokens."""
    tokens = set(query.lower().split())
    return bool(tokens & PRONOUNS) or len(tokens) <= 3


def condense_query(question: str, history: list[dict]) -> str:
    """Rewrites a follow-up query using chat history into a standalone search phrase."""
    history_str = ""
    for msg in history[-4:]:
        role = "User" if msg.get("role") == "user" else "Assistant"
        history_str += f"{role}: {msg.get('content', '')}\n"

    condense_prompt = (
        "Given the following chat history and a follow-up question, rephrase the "
        "follow-up question to be a standalone question that includes all relevant context.\n\n"
        f"Chat History:\n{history_str}\n"
        f"Follow-up Question: {question}\n\n"
        "Standalone Question:"
    )
    
    messages = [{"role": "user", "content": condense_prompt}]
    return chat_completion_sync(messages, temperature=0.0)


class StreamChatPayload(BaseModel):
    workspace_id: str
    thread_id: str
    question: str = Field(..., min_length=1)


@router.post("/stream")
async def stream_chat(
    payload: StreamChatPayload,
    user_id: str = Depends(get_current_user)
):
    # ---- TIMER: start ----
    t0 = time.perf_counter()
    t = t0

    def lap(label: str):
        nonlocal t
        now = time.perf_counter()
        print(f"[TIMER] {label}: {now - t:.2f}s (total {now - t0:.2f}s)")
        t = now

    thread_oid = to_object_id(payload.thread_id, "thread_id")

    # 1. Dual ObjectId / string lookup for multi-tenant workspace validation
    ws_query = {"$or": [{"user_id": user_id}, {"is_public": True}]}
    try:
        ws_oid = ObjectId(payload.workspace_id)
        ws_query["_id"] = {"$in": [ws_oid, payload.workspace_id]}
    except Exception:
        ws_query["_id"] = payload.workspace_id

    async def load_workspace():
        return await db.workspaces.find_one(ws_query)

    async def load_history():
        # FIX: take the 10 MOST RECENT messages, then put them back in chronological order
        recent = await db.messages.find({"thread_id": str(thread_oid)}).sort("created_at", -1).to_list(10)
        return list(reversed(recent))

    # SPEED-UP: start embedding the raw question right away (in a worker thread)
    # so it runs while the two MongoDB lookups below are in flight.
    embed_task = asyncio.ensure_future(asyncio.to_thread(embed_query, payload.question))

    # SPEED-UP: workspace check and history fetch run in parallel, not one after the other.
    workspace, history_docs = await asyncio.gather(load_workspace(), load_history())
    lap("workspace + history (parallel)")

    if not workspace:
        embed_task.cancel()
        raise HTTPException(status_code=404, detail="Workspace not found")

    # CONDITIONAL PRONOUN ROUTER
    if history_docs and needs_condensation(payload.question):
        embed_task.cancel()  # raw-question embedding is not what we want here
        search_query = await asyncio.to_thread(condense_query, payload.question, history_docs)
        lap("condense (LLM call)")
        query_vector = await asyncio.to_thread(embed_query, search_query)
    else:
        query_vector = await embed_task
    lap("embed query (wait)")

    # 5. Atlas $vectorSearch aggregation pipeline
    pipeline = [
        {
            "$vectorSearch": {
                "index": "vector_index",
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": 50,
                "limit": 5,
                "filter": {"workspace_id": payload.workspace_id}
            }
        },
        {
            "$project": {
                "text": 1,
                "video_number": 1,
                "video_title": 1,
                "source": 1,
                "lecture_number": 1,
                "start_time": 1,
                "end_time": 1,
                "score": {"$meta": "vectorSearchScore"}
            }
        }
    ]

    try:
        chunks = await db.chunks.aggregate(pipeline).to_list(5)
    except Exception:
        chunks = []
    lap("vector search")

    context_str = ""
    for c in chunks:
        raw_lec = c.get("video_number") or c.get("lecture_number") or ""
        try:
            lec = f"{int(raw_lec):02d}"
        except (ValueError, TypeError):
            lec = str(raw_lec) if raw_lec else "01"

        start = c.get("start_time", 0)
        mins, secs = divmod(int(start), 60)
        time_str = f"{mins:02d}:{secs:02d}"
        context_str += f"[Lecture {lec} at {time_str}] {c.get('text', '')}\n\n"

    system_prompt = (
        "You are an AI teaching assistant for this video lecture course. Answer the question "
        "accurately and thoroughly using the provided context below.\n"
        "MANDATORY CITATION RULE:\n"
        "Always cite source timestamps inline using the exact format [Lecture XX at MM:SS] "
        "(for example: [Lecture 19 at 11:30]) whenever referencing concepts or quotes from the transcripts.\n"
        "NEVER use 'Lecture N/A' — always cite the exact lecture number and timestamp provided in each context block.\n\n"
        f"Context:\n{context_str}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": payload.question}
    ]

    # SPEED-UP: save the user message in the background instead of waiting for it.
    asyncio.ensure_future(db.messages.insert_one({
        "thread_id": str(thread_oid),
        "user_id": user_id,
        "role": "user",
        "content": payload.question,
        "created_at": datetime.now(timezone.utc)
    }))
    lap("save user message (background)")

    async def event_generator():
        full_assistant_reply = ""
        first = True
        # FIX: pull tokens from the sync generator in a worker thread so the
        # event loop (and other users' requests) is never blocked while streaming.
        stream_iter = await asyncio.to_thread(
            lambda: iter(chat_completion_stream(messages, temperature=0.0))
        )
        _done = object()
        while True:
            token = await asyncio.to_thread(next, stream_iter, _done)
            if token is _done:
                break
            if first:
                lap("LLM first token")
                first = False
            full_assistant_reply += token
            # FIX: frontend (api.js) expects JSON events like {"token": "..."}
            yield f"data: {json.dumps({'token': token})}\n\n"
        lap("LLM full answer")
        # FIX: frontend only finishes the message when it receives {"done": true}
        yield f"data: {json.dumps({'done': True})}\n\n"

        # Save assistant message to MongoDB upon completion
        await db.messages.insert_one({
            "thread_id": str(thread_oid),
            "user_id": user_id,
            "role": "assistant",
            "content": full_assistant_reply,
            "created_at": datetime.now(timezone.utc)
        })

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )