import uuid
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from digest.app import create_app
from digest.auth import get_current_user_id
from digest.models import Source, SourceType, User


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def user(db):
    u = User(email=f"src-{uuid.uuid4().hex[:8]}@test.com", password_hash="x")
    db.add(u)
    await db.flush()
    return u


@pytest.fixture
async def client(app, user):
    app.dependency_overrides[get_current_user_id] = lambda: user.id
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


class TestCreateSource:
    async def test_create_rss_source(self, client, db):
        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.sources.async_session", mock_session):
            response = await client.post(
                "/sources/",
                json={
                    "type": "rss",
                    "name": "Hacker News",
                    "config": {"url": "https://news.ycombinator.com/rss"},
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Hacker News"
        assert data["type"] == "rss"
        assert data["is_active"] is True

    async def test_create_rss_without_url_fails(self, client, db):
        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.sources.async_session", mock_session):
            response = await client.post(
                "/sources/",
                json={"type": "rss", "name": "Bad Feed", "config": {}},
            )

        assert response.status_code == 422

    async def test_create_reddit_source(self, client, db):
        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.sources.async_session", mock_session):
            response = await client.post(
                "/sources/",
                json={
                    "type": "reddit",
                    "name": "Python",
                    "config": {"subreddit": "python"},
                },
            )

        assert response.status_code == 201
        assert response.json()["type"] == "reddit"


class TestListSources:
    async def test_list_sources(self, client, db, user):
        s = Source(
            user_id=user.id,
            type=SourceType.rss,
            name="Test",
            config={"url": "https://example.com/rss"},
        )
        db.add(s)
        await db.commit()

        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.sources.async_session", mock_session):
            response = await client.get("/sources/")

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1


class TestUpdateSource:
    async def test_update_name(self, client, db, user):
        s = Source(
            user_id=user.id,
            type=SourceType.rss,
            name="Old Name",
            config={"url": "https://example.com/rss"},
        )
        db.add(s)
        await db.commit()

        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.sources.async_session", mock_session):
            response = await client.patch(
                f"/sources/{s.id}",
                json={"name": "New Name"},
            )

        assert response.status_code == 200
        assert response.json()["name"] == "New Name"


class TestDeleteSource:
    async def test_soft_delete(self, client, db, user):
        s = Source(
            user_id=user.id,
            type=SourceType.rss,
            name="To Delete",
            config={"url": "https://example.com/rss"},
        )
        db.add(s)
        await db.commit()

        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.sources.async_session", mock_session):
            response = await client.delete(f"/sources/{s.id}")

        assert response.status_code == 204

    async def test_delete_other_users_source_fails(self, app, db, user):
        s = Source(
            user_id=user.id,
            type=SourceType.rss,
            name="Not Yours",
            config={"url": "https://example.com/rss"},
        )
        db.add(s)
        await db.commit()

        other_id = uuid.uuid4()
        app.dependency_overrides[get_current_user_id] = lambda: other_id
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as other_client:

            @asynccontextmanager
            async def mock_session():
                yield db

            with patch("digest.routes.sources.async_session", mock_session):
                response = await other_client.delete(f"/sources/{s.id}")

        assert response.status_code == 404
