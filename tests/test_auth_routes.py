import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from digest.app import create_app
from digest.auth import create_password_reset_token, hash_password


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


class TestForgotPassword:
    async def test_forgot_password_existing_email(self, client, db):
        from digest.models import User

        email = f"forgot-{uuid.uuid4().hex[:8]}@test.com"
        user = User(email=email, password_hash=hash_password("test"))
        db.add(user)
        await db.commit()

        @asynccontextmanager
        async def mock_session():
            yield db

        with (
            patch("digest.routes.auth.async_session", mock_session),
            patch(
                "digest.services.auth_service.EmailSender.send_password_reset",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_send,
        ):
            response = await client.post(
                "/auth/forgot-password",
                json={"email": email},
            )

        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        mock_send.assert_called_once()

    async def test_forgot_password_unknown_email(self, client, db):
        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.auth.async_session", mock_session):
            response = await client.post(
                "/auth/forgot-password",
                json={"email": "nobody@test.com"},
            )

        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestResetPassword:
    async def test_reset_password_success(self, client, db):
        from digest.models import User

        email = f"reset-{uuid.uuid4().hex[:8]}@test.com"
        user = User(email=email, password_hash=hash_password("oldpass"))
        db.add(user)
        await db.commit()

        token = create_password_reset_token(user)

        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.auth.async_session", mock_session):
            response = await client.post(
                "/auth/reset-password",
                json={"token": token, "new_password": "newpass123"},
            )

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

        # Verify can login with new password
        with patch("digest.routes.auth.async_session", mock_session):
            login_resp = await client.post(
                "/auth/login",
                json={"email": email, "password": "newpass123"},
            )
        assert login_resp.status_code == 200

    async def test_reset_password_token_reuse(self, client, db):
        from digest.models import User

        email = f"reuse-{uuid.uuid4().hex[:8]}@test.com"
        user = User(email=email, password_hash=hash_password("oldpass"))
        db.add(user)
        await db.commit()

        token = create_password_reset_token(user)

        @asynccontextmanager
        async def mock_session():
            yield db

        # First reset succeeds
        with patch("digest.routes.auth.async_session", mock_session):
            resp1 = await client.post(
                "/auth/reset-password",
                json={"token": token, "new_password": "newpass1"},
            )
        assert resp1.status_code == 200

        # Second reset with same token fails (fingerprint changed)
        with patch("digest.routes.auth.async_session", mock_session):
            resp2 = await client.post(
                "/auth/reset-password",
                json={"token": token, "new_password": "newpass2"},
            )
        assert resp2.status_code == 400

    async def test_reset_password_invalid_token(self, client, db):
        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.auth.async_session", mock_session):
            response = await client.post(
                "/auth/reset-password",
                json={"token": "garbage", "new_password": "newpass"},
            )

        assert response.status_code == 400
