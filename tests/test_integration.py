"""
End-to-end test: create a user with RSS and Reddit sources,
run ingestion against real feeds, verify articles are stored.
"""
import uuid

import pytest
from sqlalchemy import func, select

from digest.models import Article, Source, SourceType, User
from digest.tasks.ingest import ingest_reddit_source, ingest_rss_source


@pytest.mark.integration
async def test_ingest_real_rss_feed(db):
    """Fetch a real RSS feed and store articles."""
    user = User(email=f"{uuid.uuid4().hex[:8]}@test.com", password_hash="hash")
    db.add(user)
    await db.flush()

    source = Source(
        user_id=user.id,
        type=SourceType.rss,
        name="Hacker News",
        config={"url": "https://hnrss.org/frontpage?count=5"},
    )
    db.add(source)
    await db.flush()

    count = await ingest_rss_source(db, source)

    assert count > 0
    assert source.last_fetched_at is not None

    result = await db.execute(
        select(func.count()).select_from(Article).where(Article.source_id == source.id)
    )
    stored_count = result.scalar()
    assert stored_count == count


@pytest.mark.integration
async def test_ingest_real_reddit_feed(db):
    """Fetch a real Reddit subreddit RSS feed and store articles."""
    user = User(email=f"{uuid.uuid4().hex[:8]}@test.com", password_hash="hash")
    db.add(user)
    await db.flush()

    source = Source(
        user_id=user.id,
        type=SourceType.reddit,
        name="r/python",
        config={"subreddit": "python"},
    )
    db.add(source)
    await db.flush()

    count = await ingest_reddit_source(db, source)

    assert count > 0
    assert source.last_fetched_at is not None


@pytest.mark.integration
async def test_dedup_prevents_double_ingest(db):
    """Running ingestion twice doesn't create duplicate articles."""
    user = User(email=f"{uuid.uuid4().hex[:8]}@test.com", password_hash="hash")
    db.add(user)
    await db.flush()

    source = Source(
        user_id=user.id,
        type=SourceType.rss,
        name="HN Small",
        config={"url": "https://hnrss.org/frontpage?count=3"},
    )
    db.add(source)
    await db.flush()

    first_count = await ingest_rss_source(db, source)
    second_count = await ingest_rss_source(db, source)

    assert first_count > 0
    assert second_count == 0  # all duplicates skipped
