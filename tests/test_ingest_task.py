import uuid
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from digest.ingestion.rss import ParsedArticle
from digest.models import Source, SourceType, User
from digest.tasks.ingest import ingest_rss_source


async def test_ingest_rss_source_fetches_and_stores(db):
    user = User(email=f"{uuid.uuid4().hex[:8]}@test.com", password_hash="hash")
    db.add(user)
    await db.flush()

    source = Source(
        user_id=user.id,
        type=SourceType.rss,
        name="Test Feed",
        config={"url": "https://example.com/rss"},
    )
    db.add(source)
    await db.flush()

    mock_articles = [
        ParsedArticle(
            title="Article 1",
            url="https://example.com/1",
            content_html="<p>Content</p>",
            content_text="Content",
            author=None,
            published_at=datetime(2026, 2, 4),
            fingerprint="fp1",
        ),
    ]

    with patch("digest.tasks.ingest.RSSIngester") as MockIngester:
        mock_instance = MockIngester.return_value
        mock_instance.fetch_feed = AsyncMock(return_value=mock_articles)

        result = await ingest_rss_source(db, source)

    assert result == 1
    mock_instance.fetch_feed.assert_called_once_with("https://example.com/rss")


async def test_ingest_rss_source_updates_last_fetched(db):
    user = User(email=f"{uuid.uuid4().hex[:8]}@test.com", password_hash="hash")
    db.add(user)
    await db.flush()

    source = Source(
        user_id=user.id,
        type=SourceType.rss,
        name="Test Feed",
        config={"url": "https://example.com/rss"},
        last_fetched_at=None,
    )
    db.add(source)
    await db.flush()

    with patch("digest.tasks.ingest.RSSIngester") as MockIngester:
        mock_instance = MockIngester.return_value
        mock_instance.fetch_feed = AsyncMock(return_value=[])

        await ingest_rss_source(db, source)

    assert source.last_fetched_at is not None
