import uuid

import pytest
from sqlalchemy import select

from digest.models import Article, Source, SourceType, User, UserTier


async def test_create_user(db):
    user = User(email="test@example.com", password_hash="fakehash")
    db.add(user)
    await db.flush()

    result = await db.execute(select(User).where(User.email == "test@example.com"))
    fetched = result.scalar_one()

    assert fetched.email == "test@example.com"
    assert fetched.tier == UserTier.free
    assert fetched.timezone == "UTC"
    assert fetched.digest_time == "06:00"


async def test_create_source_with_user(db):
    user = User(email="src@example.com", password_hash="fakehash")
    db.add(user)
    await db.flush()

    source = Source(
        user_id=user.id,
        type=SourceType.rss,
        name="Hacker News",
        config={"url": "https://news.ycombinator.com/rss"},
    )
    db.add(source)
    await db.flush()

    result = await db.execute(select(Source).where(Source.user_id == user.id))
    fetched = result.scalar_one()

    assert fetched.name == "Hacker News"
    assert fetched.type == SourceType.rss
    assert fetched.config["url"] == "https://news.ycombinator.com/rss"
    assert fetched.is_active is True


async def test_create_article_with_fingerprint(db):
    user = User(email="art@example.com", password_hash="fakehash")
    db.add(user)
    await db.flush()

    source = Source(user_id=user.id, type=SourceType.rss, name="Test Feed")
    db.add(source)
    await db.flush()

    fingerprint = Article.generate_fingerprint("Test Title", "Test content here")
    article = Article(
        source_id=source.id,
        title="Test Title",
        content_text="Test content here",
        fingerprint=fingerprint,
    )
    db.add(article)
    await db.flush()

    result = await db.execute(select(Article).where(Article.source_id == source.id))
    fetched = result.scalar_one()

    assert fetched.title == "Test Title"
    assert fetched.fingerprint == fingerprint


async def test_fingerprint_deterministic():
    fp1 = Article.generate_fingerprint("Same Title", "Same content")
    fp2 = Article.generate_fingerprint("Same Title", "Same content")
    assert fp1 == fp2


async def test_fingerprint_case_insensitive():
    fp1 = Article.generate_fingerprint("My Title", "Some content")
    fp2 = Article.generate_fingerprint("MY TITLE", "SOME CONTENT")
    assert fp1 == fp2
