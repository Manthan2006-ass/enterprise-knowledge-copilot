import pytest

pytestmark = pytest.mark.asyncio


async def test_send_message_in_own_thread(client, make_user):
    headers, _ = await make_user()
    thread_res = await client.post(
        "/api/threads", json={"title": "T", "workspace_id": None}, headers=headers
    )
    thread_id = thread_res.json()["thread_id"]

    res = await client.post(
        "/api/messages",
        json={"thread_id": thread_id, "content": "Hello"},
        headers=headers,
    )
    assert res.status_code == 200
    assert "message_id" in res.json()


async def test_message_in_nonexistent_thread_404s(client, make_user):
    headers, _ = await make_user()
    fake_id = "000000000000000000000000"
    res = await client.post(
        "/api/messages",
        json={"thread_id": fake_id, "content": "Hi"},
        headers=headers,
    )
    assert res.status_code == 404


async def test_list_messages_returns_saved_content(client, make_user):
    headers, _ = await make_user()
    thread_res = await client.post(
        "/api/threads", json={"title": "T", "workspace_id": None}, headers=headers
    )
    thread_id = thread_res.json()["thread_id"]
    await client.post(
        "/api/messages", json={"thread_id": thread_id, "content": "Hello"}, headers=headers
    )

    res = await client.get(f"/api/messages?thread_id={thread_id}", headers=headers)
    assert res.status_code == 200
    contents = [m["content"] for m in res.json()["messages"]]
    assert "Hello" in contents


# -----------------------------------------------------------------------
# Cross-user isolation. This is the single most important guarantee the
# entire app makes - everything else is secondary to "user B can never
# read or write user A's data." Every one of these should 404, not 403 or
# 200, matching the app's existing behavior (don't reveal existence either).
# -----------------------------------------------------------------------

async def test_user_cannot_read_another_users_thread_messages(client, make_user):
    headers_a, _ = await make_user()
    headers_b, _ = await make_user()

    thread_res = await client.post(
        "/api/threads", json={"title": "Private", "workspace_id": None}, headers=headers_a
    )
    thread_id = thread_res.json()["thread_id"]
    await client.post(
        "/api/messages", json={"thread_id": thread_id, "content": "Secret"}, headers=headers_a
    )

    res = await client.get(f"/api/messages?thread_id={thread_id}", headers=headers_b)
    assert res.status_code == 404


async def test_user_cannot_send_message_to_another_users_thread(client, make_user):
    headers_a, _ = await make_user()
    headers_b, _ = await make_user()

    thread_res = await client.post(
        "/api/threads", json={"title": "Private", "workspace_id": None}, headers=headers_a
    )
    thread_id = thread_res.json()["thread_id"]

    res = await client.post(
        "/api/messages",
        json={"thread_id": thread_id, "content": "Intruder"},
        headers=headers_b,
    )
    assert res.status_code == 404


async def test_user_cannot_upload_to_another_users_workspace(client, make_user, tmp_path):
    headers_a, _ = await make_user()
    headers_b, _ = await make_user()

    ws_res = await client.post(
        "/api/workspaces", json={"name": "Alice WS"}, headers=headers_a
    )
    ws_id = ws_res.json()["workspace_id"]

    file_path = tmp_path / "test.txt"
    file_path.write_text("Some private content.")

    with open(file_path, "rb") as f:
        res = await client.post(
            f"/api/workspaces/{ws_id}/documents/upload",
            headers=headers_b,
            files={"file": ("test.txt", f, "text/plain")},
        )
    assert res.status_code == 404


async def test_user_cannot_list_another_users_workspace_documents(client, make_user):
    headers_a, _ = await make_user()
    headers_b, _ = await make_user()

    ws_res = await client.post(
        "/api/workspaces", json={"name": "Alice WS"}, headers=headers_a
    )
    ws_id = ws_res.json()["workspace_id"]

    res = await client.get(f"/api/workspaces/{ws_id}/documents", headers=headers_b)
    assert res.status_code == 404
