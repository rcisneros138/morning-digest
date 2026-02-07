from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from digest.services.email_sender import EmailSender


def _make_digest():
    article = SimpleNamespace(
        title="Test Article", url="https://example.com/article", id="art-1"
    )
    item = SimpleNamespace(article=article, ai_summary="A test summary", is_primary=True)
    group = SimpleNamespace(
        topic_label="Technology", summary="Tech news", items=[item], sort_order=0
    )
    digest = SimpleNamespace(
        id="digest-1",
        date=date(2026, 2, 1),
        groups=[group],
        user_id="user-1",
    )
    return digest


def _make_user():
    return SimpleNamespace(id="user-1", email="test@example.com")


class TestEmailSender:
    async def test_skips_when_not_configured(self):
        sender = EmailSender()
        with patch("digest.services.email_sender.settings") as mock_settings:
            mock_settings.mailgun_api_key = ""
            mock_settings.mailgun_domain = ""
            result = await sender.send_digest(_make_user(), _make_digest())
        assert result is False

    async def test_sends_email_when_configured(self):
        sender = EmailSender()
        mock_response = AsyncMock()
        mock_response.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        with (
            patch("digest.services.email_sender.settings") as mock_settings,
            patch("digest.services.email_sender.httpx.AsyncClient", return_value=mock_client),
        ):
            mock_settings.mailgun_api_key = "key-123"
            mock_settings.mailgun_domain = "mg.example.com"
            mock_settings.mailgun_from_email = "digest@mg.example.com"
            result = await sender.send_digest(_make_user(), _make_digest())

        assert result is True
        mock_client.post.assert_called_once()

    def test_render_html(self):
        sender = EmailSender()
        html = sender._render_html(_make_digest())
        assert "Test Article" in html
        assert "Technology" in html
        assert "example.com/article" in html

    def test_render_text(self):
        sender = EmailSender()
        text = sender._render_text(_make_digest())
        assert "Test Article" in text
        assert "Technology" in text
        assert "example.com/article" in text
