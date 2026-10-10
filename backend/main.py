import os
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager

from limiter import limiter
from database import db
from models import (
    UserSignupSchema,
    CreateWorkspaceRequest,
    UpdateWorkspaceRequest,
    CreateThreadRequest,
    CreateMessageRequest,
)
from auth import (
    get_current_user,
    hash_password,
    verify_password,
    create_access_token,
    to_object_id,
)

from chat import router as chat_router
from ingestion import router as ingestion_router
from llm_provider import chat_completion_sync


async def _ensure_vector_index():
    """Create the Atlas Vector Search index on db.chunks if it doesn't already exist.
    Safe to call on every startup — Atlas ignores the request if the index exists."""
    try:
        existing = await db.command({"listSearchIndexes": "chunks"})
        names = [idx.get("name") for idx in existing.get("cursor", {}).get("firstBatch", [])]
        if "vector_index" not in names:
            await db.command({
                "createSearchIndexes": "chunks",
                "indexes": [{
                    "name": "vector_index",
                    "type": "vectorSearch",
                    "definition": {
                        "fields": [
                            {
                                "type": "vector",
                                "path": "embedding",
                                "numDimensions": 384,
                                "similarity": "cosine",
                            },
                            {
                                "type": "filter",
                                "path": "workspace_id",
                            },
                        ]
                    },
                }],
            })
            print("[startup] Atlas vector search index 'vector_index' created.")
        else:
            print("[startup] Atlas vector search index 'vector_index' already exists.")
        # Regular index for fast workspace_id lookups on the chunks collection
        await db.chunks.create_index("workspace_id", background=True)
    except Exception as e:
        print(f"[startup] Vector index setup warning: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _ensure_vector_index()
    yield


app = FastAPI(title="Enterprise Knowledge Copilot", lifespan=lifespan)

# CORS setup: supports local Vite dev servers and cloud deployments (Vercel, custom domains)
allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]
frontend_url = os.getenv("FRONTEND_URL", "").strip()
if frontend_url:
    allowed_origins.extend([u.strip() for u in frontend_url.split(",") if u.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(chat_router)
app.include_router(ingestion_router)


# -----------------------------
# HEALTH CHECK
# -----------------------------

@app.get("/health")
async def health_check():
    await db.command("ping")
    return {"status": "healthy", "mongodb": "connected"}


@app.get("/debug/embed-test")
async def embed_test():
    """Diagnostic: tests whether the ONNX embedding function works on this host."""
    from starlette.concurrency import run_in_threadpool
    import traceback
    try:
        from embedding_utils import embed_query
        vec = await run_in_threadpool(embed_query, "test sentence for embedding")
        return {"status": "ok", "dims": len(vec), "sample": vec[:3]}
    except Exception as e:
        return {"status": "error", "error": str(e), "trace": traceback.format_exc()}


# -----------------------------
# AUTH
# -----------------------------

@app.post("/api/auth/signup")
@limiter.limit("5/minute")
async def signup(request: Request, payload: UserSignupSchema):
    existing_user = await db.users.find_one({"email": payload.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = hash_password(payload.password)
    user_doc = {"email": payload.email, "password": hashed_password}
    result = await db.users.insert_one(user_doc)

    return {"user_id": str(result.inserted_id), "message": "Signup successful"}


@app.post("/api/auth/login")
@limiter.limit("5/minute")
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    user = await db.users.find_one({"email": form_data.username})
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect email or password")

    if not verify_password(form_data.password, user["password"]):
        raise HTTPException(status_code=400, detail="Incorrect email or password")

    token = create_access_token({"sub": str(user["_id"])})
    return {"access_token": token, "token_type": "bearer"}


@app.get("/api/me")
async def get_me(user_id: str = Depends(get_current_user)):
    return {"message": "You are authenticated", "user_id": user_id}


# -----------------------------
# WORKSPACES
# -----------------------------

@app.post("/api/workspaces")
async def create_workspace(
    body: CreateWorkspaceRequest,
    user_id: str = Depends(get_current_user),
):
    workspace = {
        "name": body.name,
        "user_id": user_id,
        "is_public": body.is_public,
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.workspaces.insert_one(workspace)

    return {
        "workspace_id": str(result.inserted_id),
        "message": "Workspace created successfully",
    }


@app.get("/api/workspaces")
async def list_workspaces(user_id: str = Depends(get_current_user)):
    # Show workspaces this user owns, PLUS any workspace anyone has marked
    # public - so a flagship/shared workspace shows up for every logged-in
    # user, not just its creator.
    cursor = db.workspaces.find({
        "$or": [
            {"user_id": user_id},
            {"is_public": True},
        ]
    })
    workspaces = []
    async for w in cursor:
        workspaces.append({
            "workspace_id": str(w["_id"]),
            "name": w["name"],
            "is_public": w.get("is_public", False),
            "is_owner": w["user_id"] == user_id,
            "created_at": w["created_at"],
        })
    return {"workspaces": workspaces}


@app.patch("/api/workspaces/{workspace_id}")
async def update_workspace(
    workspace_id: str,
    body: UpdateWorkspaceRequest,
    user_id: str = Depends(get_current_user),
):
    # Owner-only - only the creator can rename a workspace or toggle its
    # public/private visibility. Being ABLE to use a public workspace
    # doesn't mean you're allowed to reconfigure it.
    workspace = await db.workspaces.find_one({
        "_id": to_object_id(workspace_id, "workspace_id"),
        "user_id": user_id,
    })
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    update_fields = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    if update_fields:
        await db.workspaces.update_one(
            {"_id": workspace["_id"]},
            {"$set": update_fields},
        )

    return {"message": "Workspace updated successfully"}


@app.get("/api/workspaces/{workspace_id}/suggested-questions")
async def get_suggested_questions(
    workspace_id: str,
    user_id: str = Depends(get_current_user),
):
    """Ask the LLM to generate 3 suggested questions based on this workspace's documents.
    Shows up as clickable chips in the UI when a user opens a fresh chat thread."""
    import json
    from starlette.concurrency import run_in_threadpool

    workspace = await db.workspaces.find_one({
        "_id": to_object_id(workspace_id, "workspace_id"),
        "$or": [
            {"user_id": user_id},
            {"is_public": True},
        ]
    })
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    # Fetch a few sample chunks from this workspace to ground the questions
    cursor = db.chunks.find({"workspace_id": workspace_id}, {"text": 1, "_id": 0}).limit(5)
    docs = []
    async for chunk in cursor:
        if chunk.get("text"):
            docs.append(chunk["text"])
    if not docs:
        return {"questions": [
            "What topics does this workspace cover?",
            "Summarise the key ideas in the documents.",
            "What are the most important takeaways?",
        ]}

    context = "\n\n".join(docs[:5])
    prompt = (
        "You are an AI assistant. Based on the following excerpts from a user's documents, "
        "suggest exactly 3 short, interesting questions the user could ask to learn more. "
        "Return ONLY a JSON array of 3 strings, no extra text or markdown.\n\n"
        f"Excerpts:\n{context}\n\nOutput JSON Array:"
    )

    try:
        content = await run_in_threadpool(
            chat_completion_sync,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        # Strip markdown code fences if the model wraps its output
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        questions = json.loads(content.strip())
        if not isinstance(questions, list) or len(questions) < 1:
            raise ValueError("Not a valid list")
        return {"questions": questions[:3]}
    except Exception as e:
        print(f"[suggested-questions] LLM parse error: {e}")
        return {"questions": [
            "What topics does this workspace cover?",
            "Summarise the key ideas in the documents.",
            "What are the most important takeaways?",
        ]}


# -----------------------------
# THREADS
# -----------------------------

@app.post("/api/threads")
async def create_thread(
    body: CreateThreadRequest,
    user_id: str = Depends(get_current_user),
):
    # Only validate a workspace if one was actually provided.
    # workspace_id == None means this is a "Normal Chat" thread with no RAG.
    if body.workspace_id is not None:
        # Allow access if the user owns this workspace, OR it's public -
        # anyone can start a chat thread inside a shared workspace, even
        # though only the owner can upload new documents into it.
        workspace = await db.workspaces.find_one({
            "_id": to_object_id(body.workspace_id, "workspace_id"),
            "$or": [
                {"user_id": user_id},
                {"is_public": True},
            ],
        })
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

    thread = {
        "workspace_id": body.workspace_id,
        "user_id": user_id,
        "title": body.title,
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.threads.insert_one(thread)

    return {
        "thread_id": str(result.inserted_id),
        "message": "Thread created successfully",
    }


@app.get("/api/threads")
async def list_threads(
    workspace_id: str | None = None,
    user_id: str = Depends(get_current_user),
):
    query = {"user_id": user_id}
    if workspace_id is not None:
        query["workspace_id"] = workspace_id

    cursor = db.threads.find(query).sort("created_at", -1)
    threads = []
    async for t in cursor:
        threads.append({
            "thread_id": str(t["_id"]),
            "workspace_id": t["workspace_id"],
            "title": t["title"],
            "created_at": t["created_at"],
        })
    return {"threads": threads}


@app.delete("/api/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    user_id: str = Depends(get_current_user),
):
    thread = await db.threads.find_one({
        "_id": to_object_id(thread_id, "thread_id"),
        "user_id": user_id,
    })
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Delete the thread and all its messages together — orphaned messages
    # waste storage and could leak context if a thread_id is ever reused.
    await db.threads.delete_one({"_id": thread["_id"]})
    await db.messages.delete_many({"thread_id": thread_id})

    return {"message": "Thread deleted successfully"}



# -----------------------------
# MESSAGES
# -----------------------------

@app.post("/api/messages")
async def create_message(
    body: CreateMessageRequest,
    user_id: str = Depends(get_current_user),
):
    thread = await db.threads.find_one({
        "_id": to_object_id(body.thread_id, "thread_id"),
        "user_id": user_id,
    })
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    message = {
        "user_id": user_id,
        "workspace_id": thread["workspace_id"],  # inherited from thread, not client input
        "thread_id": body.thread_id,
        "role": "user",
        "content": body.content,
        "created_at": datetime.now(timezone.utc),
    }
    result = await db.messages.insert_one(message)

    return {
        "message_id": str(result.inserted_id),
        "message": "Message saved successfully",
    }


@app.get("/api/messages")
async def list_messages(
    thread_id: str,
    user_id: str = Depends(get_current_user),
):
    thread = await db.threads.find_one({
        "_id": to_object_id(thread_id, "thread_id"),
        "user_id": user_id,
    })
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    cursor = db.messages.find({"thread_id": thread_id}).sort("created_at", 1)
    messages = []
    async for m in cursor:
        messages.append({
            "message_id": str(m["_id"]),
            "role": m["role"],
            "content": m["content"],
            "created_at": m["created_at"],
        })
    return {"messages": messages}
