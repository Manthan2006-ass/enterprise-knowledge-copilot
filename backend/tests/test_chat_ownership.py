import pytest

pytestmark = pytest.mark.asyncio

# NOTE: These tests only cover the ownership check in POST /api/chat/stream,
# which runs and returns 404 BEFORE any call to Ollama/ChromaDB. They do NOT
# require Ollama to be running. Actually testing a real streamed answer is a
# separate, slower integration concern - see the note at the bottom of this
# file if you want to add that later.


async def test_chat_stream_404_for_nonexistent_thread(client, make_user):
    headers, _ = await make_user()
    fake_id = "000000000000000000000000"

    res = await client.post(
        "/api/chat/stream",
        json={"thread_id": fake_id, "workspace_id": None, "question": "hi"},
        headers=headers,
    )
    assert res.status_code == 404


async def test_chat_stream_404_for_another_users_thread(client, make_user):
    headers_a, _ = await make_user()
    headers_b, _ = await make_user()

    thread_res = await client.post(
        "/api/threads", json={"title": "T", "workspace_id": None}, headers=headers_a
    )
    thread_id = thread_res.json()["thread_id"]

    res = await client.post(
        "/api/chat/stream",
        json={"thread_id": thread_id, "workspace_id": None, "question": "hi"},
        headers=headers_b,
    )
    assert res.status_code == 404


async def test_chat_stream_requires_auth(client, make_user):
    headers, _ = await make_user()
    thread_res = await client.post(
        "/api/threads", json={"title": "T", "workspace_id": None}, headers=headers
    )
    thread_id = thread_res.json()["thread_id"]

    res = await client.post(
        "/api/chat/stream",
        json={"thread_id": thread_id, "workspace_id": None, "question": "hi"},
        # no headers at all
    )
    assert res.status_code == 401


# -----------------------------------------------------------------------
# NOT covered here (requires a live Ollama + populated ChromaDB, so these
# are slow, environment-dependent integration tests rather than unit tests):
#   - actually streaming a real answer end to end
#   - workspace RAG retrieval returning correct, isolated chunks
#   - the has_docs empty-workspace-behaves-like-normal-chat branch
#   - the distance-threshold filtering behavior
#
# If you want these covered later, mark them with @pytest.mark.integration,
# require Ollama running in CI, and skip them by default with
# `pytest -m "not integration"` in fast local/CI runs.
# -----------------------------------------------------------------------
