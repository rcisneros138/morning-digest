import uuid
from contextlib import asynccontextmanager
from unittest.mock import patch

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


class TestInboundWebhook:
    async def test_health_check(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    async def test_inbound_email_accepted(self, client, db):
        user = User(email="realuser@gmail.com", password_hash="hash")
        db.add(user)
        await db.flush()

        source = Source(
            user_id=user.id,
            type=SourceType.newsletter,
            name="Morning Brew",
            config={"forwarding_address": "user-abc123@digest.app"},
        )
        db.add(source)
        await db.flush()
        await db.commit()

        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.inbound.async_session", mock_session):
            response = await client.post(
                "/webhooks/inbound",
                data={
                    "sender": "newsletter@morningbrew.com",
                    "subject": "Morning Brew - Feb 4",
                    "body-html": "<p>Top stories today</p>",
                    "body-plain": "Top stories today",
                    "recipient": "user-abc123@digest.app",
                },
            )

        assert response.status_code == 200

    async def test_inbound_email_unknown_recipient_returns_406(self, client, db):
        @asynccontextmanager
        async def mock_session():
            yield db

        with patch("digest.routes.inbound.async_session", mock_session):
            response = await client.post(
                "/webhooks/inbound",
                data={
                    "sender": "spam@example.com",
                    "subject": "Spam",
                    "body-html": "<p>Buy now</p>",
                    "body-plain": "Buy now",
                    "recipient": "nonexistent@digest.app",
                },
            )

        assert response.status_code == 406
