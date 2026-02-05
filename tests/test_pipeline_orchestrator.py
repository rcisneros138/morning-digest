import uuid
from datetime import date, datetime

import pytest

from digest.models import (
    Article,
    Digest,
    DigestGroup,
    DigestItem,
    Source,
    SourceType,
    User,
    UserTier,
)
from digest.services.pipeline.orchestrator import Orchestrator


@pytest.fixture
async def user(db):
    u = User(email=f"orch-{uuid.uuid4().hex[:8]}@test.com", password_hash="x")
    db.add(u)
    await db.flush()
    return u


@pytest.fixture
async def source(db, user):
    s = Source(user_id=user.id, type=SourceType.rss, name="Test Feed")
    db.add(s)
    await db.flush()
    return s


def _add_article(db, source_id, title, content_text="content", fingerprint=None, published_at=None):
    a = Article(
        source_id=source_id,
        title=title,
        content_text=content_text,
        fingerprint=fingerprint or Article.generate_fingerprint(title, content_text),
        published_at=published_at,
    )
    db.add(a)
    return a


async def test_orchestrator_returns_none_when_no_articles(db, user):
    orch = Orchestrator()
    result = await orch.generate(db, user.id, UserTier.free)
    assert result is None


async def test_orchestrator_creates_digest_with_groups(db, user, source):
    _add_article(db, source.id, "Tech Article", "Python programming tutorial guide")
    _add_article(db, source.id, "Sports News", "Football match results and scores")
    await db.flush()

    orch = Orchestrator()
    digest = await orch.generate(
        db, user.id, UserTier.free, digest_date=date(2026, 2, 1)
    )

    assert digest is not None
    assert digest.user_id == user.id
    assert digest.date == date(2026, 2, 1)
    assert digest.tier_at_creation == UserTier.free

    await db.refresh(digest, ["groups"])
    assert len(digest.groups) >= 1

    # Every group should have items
    for group in digest.groups:
        await db.refresh(group, ["items"])
        assert len(group.items) >= 1
        assert group.topic_label != ""


async def test_orchestrator_deduplicates(db, user, source):
    fp = Article.generate_fingerprint("Same Story", "Same content text here")
    _add_article(db, source.id, "Same Story", "Same content text here", fingerprint=fp)
    _add_article(db, source.id, "Same Story", "Same content text here and more", fingerprint=fp)
    _add_article(db, source.id, "Different Story", "Completely different content")
    await db.flush()

    orch = Orchestrator()
    digest = await orch.generate(db, user.id, UserTier.free)

    assert digest is not None
    await db.refresh(digest, ["groups"])

    # Count total items across all groups
    total_items = 0
    for group in digest.groups:
        await db.refresh(group, ["items"])
        total_items += len(group.items)

    # Should have 2 items (one deduped pair primary + one unique), not 3
    assert total_items == 2


async def test_orchestrator_free_tier_no_summaries(db, user, source):
    _add_article(db, source.id, "Article One", "Content for article one")
    await db.flush()

    orch = Orchestrator()
    digest = await orch.generate(db, user.id, UserTier.free)

    assert digest is not None
    await db.refresh(digest, ["groups"])
    for group in digest.groups:
        assert group.summary is None
        await db.refresh(group, ["items"])
        for item in group.items:
            assert item.ai_summary is None


async def test_orchestrator_sort_order_set(db, user, source):
    _add_article(db, source.id, "Article A", "Content about python programming")
    _add_article(db, source.id, "Article B", "Content about java programming")
    _add_article(db, source.id, "Article C", "Content about stock markets")
    await db.flush()

    orch = Orchestrator()
    digest = await orch.generate(db, user.id, UserTier.free)

    assert digest is not None
    await db.refresh(digest, ["groups"])
    for i, group in enumerate(digest.groups):
        assert group.sort_order == i
        await db.refresh(group, ["items"])
        for j, item in enumerate(group.items):
            assert item.sort_order == j


async def test_orchestrator_does_not_commit(db, user, source):
    _add_article(db, source.id, "Test Article", "Some content here for testing")
    await db.flush()

    orch = Orchestrator()
    digest = await orch.generate(db, user.id, UserTier.free)
    assert digest is not None

    # Session should still be dirty/flushed but not committed
    # We can rollback and the digest should disappear
    await db.rollback()

    result = await db.get(Digest, digest.id)
    assert result is None
