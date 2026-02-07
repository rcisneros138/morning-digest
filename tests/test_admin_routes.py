import uuid
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from digest.app import create_app
from digest.models import Source, SourceType, User


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
    u = User(email=f"admin-{uuid.uuid4().hex[:8]}@test.com", password_hash="x")
    db.add(u)
    await db.flush()
    return u


ADMIN_KEY = "test-admin-key"


class TestAdminAuth:
    async def test_missing_key_returns_422(self, client):
        response = await client.get("/admin/stats")
        assert response.status_code == 422

    async def test_wrong_key_returns_403(self, client):
        with patch("digest.routes.admin.settings") as mock_settings:
            mock_settings.admin_api_key = ADMIN_KEY
            response = await client.get(
                "/admin/stats",
                headers={"X-Admin-Key": "wrong-key"},
            )
        assert response.status_code == 403


class TestGetStats:
    async def test_returns_stats(self, client, db, user):
        s = Source(
            user_id=user.id, type=SourceType.rss, name="Test", config={"url": "https://x.com/rss"}
        )
        db.add(s)
        await db.commit()

        @asynccontextmanager
        async def mock_session():
            yield db

        with (
            patch("digest.routes.admin.settings") as mock_settings,
            patch("digest.routes.admin.async_session", mock_session),
        ):
            mock_settings.admin_api_key = ADMIN_KEY
            response = await client.get(
                "/admin/stats",
                headers={"X-Admin-Key": ADMIN_KEY},
            )

        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert "articles" in data
        assert "digests" in data
        assert "sources_by_type" in data


class TestListUsers:
    async def test_returns_users(self, client, db, user):
        await db.commit()

        @asynccontextmanager
        async def mock_session():
            yield db

        with (
            patch("digest.routes.admin.settings") as mock_settings,
            patch("digest.routes.admin.async_session", mock_session),
        ):
            mock_settings.admin_api_key = ADMIN_KEY
            response = await client.get(
                "/admin/users",
                headers={"X-Admin-Key": ADMIN_KEY},
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert "email" in data[0]
        assert "source_count" in data[0]


class TestTriggerIngest:
    async def test_enqueues_ingest(self, client):
        mock_task = MagicMock()

        with (
            patch("digest.routes.admin.settings") as mock_settings,
            patch("digest.tasks.ingest.poll_all_rss_feeds", mock_task),
        ):
            mock_settings.admin_api_key = ADMIN_KEY
            response = await client.post(
                "/admin/tasks/ingest",
                headers={"X-Admin-Key": ADMIN_KEY},
            )

        assert response.status_code == 200
        assert response.json()["status"] == "enqueued"


class TestTriggerDigest:
    async def test_enqueues_digest(self, client):
        user_id = uuid.uuid4()
        mock_task = MagicMock()

        with (
            patch("digest.routes.admin.settings") as mock_settings,
            patch("digest.tasks.generate_digest.generate_user_digest", mock_task),
        ):
            mock_settings.admin_api_key = ADMIN_KEY
            response = await client.post(
                f"/admin/tasks/digest/{user_id}",
                headers={"X-Admin-Key": ADMIN_KEY},
            )

        assert response.status_code == 200
        assert response.json()["status"] == "enqueued"
