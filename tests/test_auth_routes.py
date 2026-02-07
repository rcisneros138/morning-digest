import uuid
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from digest.app import create_app
from digest.auth import hash_password


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestRegister:
    async def test_register_success(self, client, db):
        email = f"reg-{uuid.uuid4().hex[:8]}@test.com"

        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.auth.async_session", mock_session):
            response = await client.post(
                "/auth/register",
                json={"email": email, "password": "testpass123"},
            )

        assert response.status_code == 201
        data = response.json()
        assert "user_id" in data
        assert "access_token" in data
        assert "refresh_token" in data

    async def test_register_duplicate_email(self, client, db):
        from digest.models import User

        email = f"dup-{uuid.uuid4().hex[:8]}@test.com"
        user = User(email=email, password_hash=hash_password("test"))
        db.add(user)
        await db.commit()

        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.auth.async_session", mock_session):
            response = await client.post(
                "/auth/register",
                json={"email": email, "password": "testpass123"},
            )

        assert response.status_code == 409


class TestLogin:
    async def test_login_success(self, client, db):
        from digest.models import User

        email = f"login-{uuid.uuid4().hex[:8]}@test.com"
        user = User(email=email, password_hash=hash_password("correctpass"))
        db.add(user)
        await db.commit()

        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.auth.async_session", mock_session):
            response = await client.post(
                "/auth/login",
                json={"email": email, "password": "correctpass"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    async def test_login_wrong_password(self, client, db):
        from digest.models import User

        email = f"login-bad-{uuid.uuid4().hex[:8]}@test.com"
        user = User(email=email, password_hash=hash_password("correctpass"))
        db.add(user)
        await db.commit()

        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.auth.async_session", mock_session):
            response = await client.post(
                "/auth/login",
                json={"email": email, "password": "wrongpass"},
            )

        assert response.status_code == 401


class TestRefresh:
    async def test_refresh_rotates_tokens(self, client, db):
        from digest.models import User

        email = f"refresh-{uuid.uuid4().hex[:8]}@test.com"
        user = User(email=email, password_hash=hash_password("test"))
        db.add(user)
        await db.commit()

        @asynccontextmanager
        async def mock_session():
            yield db

        # First login to get tokens
        with patch("digest.routes.auth.async_session", mock_session):
            login_resp = await client.post(
                "/auth/login",
                json={"email": email, "password": "test"},
            )
        refresh_token = login_resp.json()["refresh_token"]

        # Now refresh
        with patch("digest.routes.auth.async_session", mock_session):
            response = await client.post(
                "/auth/refresh",
                json={"refresh_token": refresh_token},
            )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["refresh_token"] != refresh_token


class TestLogout:
    async def test_logout_success(self, client, db):
        from digest.models import User

        email = f"logout-{uuid.uuid4().hex[:8]}@test.com"
        user = User(email=email, password_hash=hash_password("test"))
        db.add(user)
        await db.commit()

        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.auth.async_session", mock_session):
            login_resp = await client.post(
                "/auth/login",
                json={"email": email, "password": "test"},
            )
        refresh_token = login_resp.json()["refresh_token"]

        with patch("digest.routes.auth.async_session", mock_session):
            response = await client.post(
                "/auth/logout",
                json={"refresh_token": refresh_token},
            )

        assert response.status_code == 200
        assert response.json()["status"] == "ok"
