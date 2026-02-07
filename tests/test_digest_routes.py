import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from digest.app import create_app
from digest.auth import get_current_user_id
from digest.models import (
    Article,
    Digest,
    DigestGroup,
    DigestItem,
    InteractionType,
    Source,
    SourceType,
    User,
    UserTier,
)


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app, user):
    app.dependency_overrides[get_current_user_id] = lambda: user.id
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def user(db):
    u = User(email=f"routes-{uuid.uuid4().hex[:8]}@test.com", password_hash="x")
    db.add(u)
    await db.flush()
    return u


@pytest.fixture
async def source(db, user):
    s = Source(user_id=user.id, type=SourceType.rss, name="Test Feed")
    db.add(s)
    await db.flush()
    return s


@pytest.fixture
async def article(db, source):
    a = Article(
        source_id=source.id,
        title="Test Article",
        content_text="Test content",
        url="https://example.com/article",
        author="Author",
        fingerprint=Article.generate_fingerprint("Test Article", "Test content"),
    )
    db.add(a)
    await db.flush()
    return a


@pytest.fixture
async def digest_with_data(db, user, article):
    digest = Digest(
        user_id=user.id,
        date=date(2026, 2, 1),
        tier_at_creation=UserTier.free,
        generated_at=datetime(2026, 2, 1, 6, 0, 0),
    )
    db.add(digest)
    await db.flush()

    group = DigestGroup(
        digest_id=digest.id,
        topic_label="Technology",
        sort_order=0,
    )
    db.add(group)
    await db.flush()

    item = DigestItem(
        group_id=group.id,
        article_id=article.id,
        sort_order=0,
        is_primary=True,
    )
    db.add(item)
    await db.flush()
    await db.commit()

    return digest


class TestGetLatestDigest:
    async def test_returns_latest_digest(self, client, db, digest_with_data):
        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.digests.async_session", mock_session):
            response = await client.get("/digests/latest")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(digest_with_data.id)
        assert data["date"] == "2026-02-01"
        assert len(data["groups"]) == 1
        assert data["groups"][0]["topic_label"] == "Technology"
        assert len(data["groups"][0]["articles"]) == 1
        assert data["groups"][0]["articles"][0]["title"] == "Test Article"
        assert data["groups"][0]["articles"][0]["is_primary"] is True

    async def test_returns_404_when_no_digest(self, client, db, user):
        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.digests.async_session", mock_session):
            response = await client.get("/digests/latest")

        assert response.status_code == 404


class TestGetDigestById:
    async def test_returns_digest(self, client, db, digest_with_data):
        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.digests.async_session", mock_session):
            response = await client.get(f"/digests/{digest_with_data.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(digest_with_data.id)

    async def test_returns_404_for_unknown_id(self, client, db):
        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.digests.async_session", mock_session):
            response = await client.get(f"/digests/{uuid.uuid4()}")

        assert response.status_code == 404

    async def test_returns_404_for_other_users_digest(self, app, db, digest_with_data):
        other_user_id = uuid.uuid4()
        app.dependency_overrides[get_current_user_id] = lambda: other_user_id
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as other_client:

            @asynccontextmanager
            async def mock_session():
                yield db

            with patch("digest.routes.digests.async_session", mock_session):
                response = await other_client.get(f"/digests/{digest_with_data.id}")

        assert response.status_code == 404


class TestListDigests:
    async def test_returns_digest_list(self, client, db, digest_with_data):
        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.digests.async_session", mock_session):
            response = await client.get("/digests/")

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["id"] == str(digest_with_data.id)

    async def test_returns_empty_list(self, client, db, user):
        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.digests.async_session", mock_session):
            response = await client.get("/digests/")

        assert response.status_code == 200
        assert response.json() == []


class TestCreateInteraction:
    async def test_creates_interaction(self, client, db, user, article):
        await db.commit()

        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.digests.async_session", mock_session):
            response = await client.post(
                "/digests/interactions",
                json={
                    "article_id": str(article.id),
                    "type": "saved",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "created"
        assert "id" in data
