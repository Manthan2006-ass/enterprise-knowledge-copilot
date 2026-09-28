import pytest

pytestmark = pytest.mark.asyncio


async def test_signup_creates_user(client):
    res = await client.post(
        "/api/auth/signup", json={"email": "alice@test.com", "password": "alicepass123"}
    )
    assert res.status_code == 200
    data = res.json()
    assert "user_id" in data
    assert data["message"] == "Signup successful"


async def test_signup_duplicate_email_rejected(client):
    await client.post(
        "/api/auth/signup", json={"email": "bob@test.com", "password": "bobpass123"}
    )
    res = await client.post(
        "/api/auth/signup", json={"email": "bob@test.com", "password": "different"}
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Email already registered"


async def test_login_success_returns_token(client):
    await client.post(
        "/api/auth/signup", json={"email": "carol@test.com", "password": "carolpass123"}
    )
    res = await client.post(
        "/api/auth/login",
        data={"username": "carol@test.com", "password": "carolpass123"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


async def test_login_wrong_password_rejected(client):
    await client.post(
        "/api/auth/signup", json={"email": "dave@test.com", "password": "davepass123"}
    )
    res = await client.post(
        "/api/auth/login",
        data={"username": "dave@test.com", "password": "wrongpassword"},
    )
    assert res.status_code == 400


async def test_login_nonexistent_user_rejected(client):
    res = await client.post(
        "/api/auth/login",
        data={"username": "ghost@test.com", "password": "whatever"},
    )
    assert res.status_code == 400


async def test_me_requires_auth(client):
    res = await client.get("/api/me")
    assert res.status_code == 401


async def test_me_rejects_garbage_token(client):
    res = await client.get(
        "/api/me", headers={"Authorization": "Bearer not-a-real-jwt"}
    )
    assert res.status_code == 401


async def test_me_returns_own_user_id_with_valid_token(client, make_user):
    headers, user_id = await make_user()
    res = await client.get("/api/me", headers=headers)
    assert res.status_code == 200
    assert res.json()["user_id"] == user_id
