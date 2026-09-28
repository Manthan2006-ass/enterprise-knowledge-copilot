import pytest

pytestmark = pytest.mark.asyncio


async def test_create_workspace(client, make_user):
    headers, _ = await make_user()
    res = await client.post(
        "/api/workspaces", json={"name": "My Workspace"}, headers=headers
    )
    assert res.status_code == 200
    assert "workspace_id" in res.json()


async def test_create_workspace_requires_auth(client):
    res = await client.post("/api/workspaces", json={"name": "No Auth"})
    assert res.status_code == 401


async def test_list_workspaces_only_shows_own(client, make_user):
    headers_a, _ = await make_user()
    headers_b, _ = await make_user()

    await client.post("/api/workspaces", json={"name": "Alice WS"}, headers=headers_a)
    await client.post("/api/workspaces", json={"name": "Bob WS"}, headers=headers_b)

    res_a = await client.get("/api/workspaces", headers=headers_a)
    names = [w["name"] for w in res_a.json()["workspaces"]]

    assert "Alice WS" in names
    assert "Bob WS" not in names
