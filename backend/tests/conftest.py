import os

# Point at an isolated test database BEFORE importing anything that reads
# config/database at import time. python-dotenv's load_dotenv() does NOT
# override variables already set in os.environ, so setting these here first
# guarantees tests never touch your real dev/prod MongoDB data.
os.environ["DB_NAME"] = "enterprise_copilot_test_db"
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")

import itertools

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from motor.motor_asyncio import AsyncIOMotorClient

import database
import main
import chat
import ingestion
from main import app

_email_counter = itertools.count(1)


@pytest_asyncio.fixture(autouse=True)
async def _fresh_mongo_client_per_test():
    """
    Motor's AsyncIOMotorClient binds internal async primitives (locks, etc.)
    to whichever event loop is running the first time it's used. pytest-
    asyncio creates a NEW event loop for each test function by default, so
    reusing the app's single import-time Motor client across tests causes
    'RuntimeError: Event loop is closed' starting from the 2nd test.

    Fix: create a fresh client bound to THIS test's loop, then patch every
    module that already did `from database import db` at import time (they
    each hold their own copy of that reference) so the whole app sees the
    fresh client for the duration of this one test. No need to restructure
    database.py or how main/chat/ingestion import db.
    """
    fresh_client = AsyncIOMotorClient(os.environ["MONGO_URI"])
    fresh_db = fresh_client[os.environ["DB_NAME"]]

    database.client = fresh_client
    database.db = fresh_db
    main.db = fresh_db
    chat.db = fresh_db
    ingestion.db = fresh_db

    yield

    fresh_client.close()


@pytest_asyncio.fixture
async def client(_fresh_mongo_client_per_test):
    """An async HTTP client wired directly to the FastAPI app - no real
    network calls, no server process needed. Depends on the fresh-client
    fixture explicitly so the DB is always ready before any request."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(autouse=True)
async def clean_db(_fresh_mongo_client_per_test):
    """Wipes test-relevant collections after every test. Depends on the
    fresh-client fixture explicitly, so cleanup always targets THIS test's
    client (via database.db, looked up fresh here, not a stale import-time
    reference) and runs before that client gets closed."""
    yield
    for name in ["users", "workspaces", "threads", "messages", "documents"]:
        await database.db[name].delete_many({})


@pytest_asyncio.fixture
def make_user(client):
    """
    Factory fixture: call `await make_user()` inside a test to get a fresh,
    unique signed-up-and-logged-in user. Returns (auth_headers, user_id).

    Using a factory (instead of one fixed user) lets a single test create
    multiple independent users - essential for isolation tests.
    """

    async def _make_user():
        n = next(_email_counter)
        email = f"user{n}@test.com"
        password = "testpass123"

        await client.post("/api/auth/signup", json={"email": email, "password": password})
        login_res = await client.post(
            "/api/auth/login",
            data={"username": email, "password": password},
        )
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        me_res = await client.get("/api/me", headers=headers)
        user_id = me_res.json()["user_id"]

        return headers, user_id

    return _make_user