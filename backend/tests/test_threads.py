import pytest

pytestmark = pytest.mark.asyncio


async def test_create_normal_chat_thread(client, make_user):
    headers, _ = await make_user()
    res = await client.post(
        "/api/threads",
        json={"title": "Normal Chat", "workspace_id": None},
        headers=headers,
    )
    assert res.status_code == 200
    assert "thread_id" in res.json()


async def test_create_workspace_thread(client, make_user):
    headers, _ = await make_user()
    ws_res = await client.post("/api/workspaces", json={"name": "WS"}, headers=headers)
    ws_id = ws_res.json()["workspace_id"]

    res = await client.post(
        "/api/threads",
        json={"title": "WS Thread", "workspace_id": ws_id},
        headers=headers,
    )
    assert res.status_code == 200
    assert "thread_id" in res.json()


async def test_create_thread_with_nonexistent_workspace_404s(client, make_user):
    headers, _ = await make_user()
    fake_id = "000000000000000000000000"  # valid ObjectId shape, doesn't exist
    res = await client.post(
        "/api/threads",
        json={"title": "Bad", "workspace_id": fake_id},
        headers=headers,
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "Workspace not found"


async def test_create_thread_with_malformed_workspace_id_400s(client, make_user):
    headers, _ = await make_user()
    res = await client.post(
        "/api/threads",
        json={"title": "Bad", "workspace_id": "not-a-valid-object-id"},
        headers=headers,
    )
    assert res.status_code == 400


async def test_list_threads_only_shows_own(client, make_user):
    headers_a, _ = await make_user()
    headers_b, _ = await make_user()

    await client.post(
        "/api/threads", json={"title": "Alice Thread", "workspace_id": None}, headers=headers_a
    )
    await client.post(
        "/api/threads", json={"title": "Bob Thread", "workspace_id": None}, headers=headers_b
    )

    res_a = await client.get("/api/threads", headers=headers_a)
    titles = [t["title"] for t in res_a.json()["threads"]]

    assert "Alice Thread" in titles
    assert "Bob Thread" not in titles
