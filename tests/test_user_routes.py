import uuid
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from digest.app import create_app
from digest.auth import get_current_user_id, hash_password


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def user(db):
    from digest.models import User

    u = User(
        email=f"user-{uuid.uuid4().hex[:8]}@test.com",
        password_hash=hash_password("testpass"),
        timezone="UTC",
        digest_time="06:00",
    )
    db.add(u)
    await db.commit()
    return u


class TestGetMe:
    async def test_get_me_success(self, client, app, db, user):
        app.dependency_overrides[get_current_user_id] = lambda: user.id

        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.users.async_session", mock_session):
            response = await client.get("/users/me")

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == user.email
        assert data["timezone"] == "UTC"
        assert data["digest_time"] == "06:00"
        assert data["tier"] == "free"
        assert "id" in data
        assert "created_at" in data

        app.dependency_overrides.clear()

    async def test_get_me_unauthenticated(self, client):
        response = await client.get("/users/me")
        assert response.status_code in (401, 403)


class TestUpdateMe:
    async def test_update_timezone(self, client, app, db, user):
        app.dependency_overrides[get_current_user_id] = lambda: user.id

        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.users.async_session", mock_session):
            response = await client.patch(
                "/users/me", json={"timezone": "America/New_York"}
            )

        assert response.status_code == 200
        assert response.json()["timezone"] == "America/New_York"
        app.dependency_overrides.clear()

    async def test_update_invalid_timezone(self, client, app, db, user):
        app.dependency_overrides[get_current_user_id] = lambda: user.id

        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.users.async_session", mock_session):
            response = await client.patch(
                "/users/me", json={"timezone": "Not/A/Timezone"}
            )

        assert response.status_code == 422
        app.dependency_overrides.clear()

    async def test_update_digest_time(self, client, app, db, user):
        app.dependency_overrides[get_current_user_id] = lambda: user.id

        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.users.async_session", mock_session):
            response = await client.patch(
                "/users/me", json={"digest_time": "08:30"}
            )

        assert response.status_code == 200
        assert response.json()["digest_time"] == "08:30"
        app.dependency_overrides.clear()

    async def test_update_invalid_digest_time(self, client, app, db, user):
        app.dependency_overrides[get_current_user_id] = lambda: user.id

        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.users.async_session", mock_session):
            response = await client.patch(
                "/users/me", json={"digest_time": "25:00"}
            )

        assert response.status_code == 422
        app.dependency_overrides.clear()

    async def test_update_invalid_digest_time_format(self, client, app, db, user):
        app.dependency_overrides[get_current_user_id] = lambda: user.id

        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.users.async_session", mock_session):
            response = await client.patch(
                "/users/me", json={"digest_time": "8am"}
            )

        assert response.status_code == 422
        app.dependency_overrides.clear()

    async def test_update_email(self, client, app, db, user):
        app.dependency_overrides[get_current_user_id] = lambda: user.id
        new_email = f"new-{uuid.uuid4().hex[:8]}@test.com"

        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.users.async_session", mock_session):
            response = await client.patch(
                "/users/me", json={"email": new_email}
            )

        assert response.status_code == 200
        assert response.json()["email"] == new_email
        app.dependency_overrides.clear()

    async def test_update_email_duplicate(self, client, app, db, user):
        from digest.models import User as UserModel

        other = UserModel(
            email=f"other-{uuid.uuid4().hex[:8]}@test.com",
            password_hash=hash_password("test"),
        )
        db.add(other)
        await db.commit()

        app.dependency_overrides[get_current_user_id] = lambda: user.id

        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.users.async_session", mock_session):
            response = await client.patch(
                "/users/me", json={"email": other.email}
            )

        assert response.status_code == 409
        app.dependency_overrides.clear()

    async def test_update_multiple_fields(self, client, app, db, user):
        app.dependency_overrides[get_current_user_id] = lambda: user.id

        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.users.async_session", mock_session):
            response = await client.patch(
                "/users/me",
                json={"timezone": "Europe/London", "digest_time": "07:00"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["timezone"] == "Europe/London"
        assert data["digest_time"] == "07:00"
        app.dependency_overrides.clear()
