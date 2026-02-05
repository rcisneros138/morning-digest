import uuid
from datetime import datetime

import pytest

from digest.models import (
    Article,
    Digest,
    Source,
    SourceType,
    User,
    UserTier,
)
from digest.services.pipeline.collect import CollectStage


@pytest.fixture
async def user(db):
    u = User(email=f"collect-{uuid.uuid4().hex[:8]}@test.com", password_hash="x")
    db.add(u)
    await db.flush()
    return u


@pytest.fixture
async def source(db, user):
    s = Source(user_id=user.id, type=SourceType.rss, name="Test Feed")
    db.add(s)
    await db.flush()
    return s


def _make_article(source_id, title, published_at=None, content_text="content"):
    return Article(
        source_id=source_id,
        title=title,
        content_text=content_text,
        fingerprint=Article.generate_fingerprint(title, content_text),
        published_at=published_at,
    )


async def test_collect_all_when_no_prior_digest(db, user, source):
    a1 = _make_article(source.id, "Article 1")
    a2 = _make_article(source.id, "Article 2")
    db.add_all([a1, a2])
    await db.flush()

    stage = CollectStage()
    articles = await stage.collect(db, user.id)
    assert len(articles) == 2


async def test_collect_only_new_since_last_digest(db, user, source):
    # Create an old article
    old = _make_article(source.id, "Old Article", published_at=datetime(2026, 1, 1))
    db.add(old)
    await db.flush()

    # Create a digest at Jan 10
    digest = Digest(
        user_id=user.id,
        date=datetime(2026, 1, 10).date(),
        tier_at_creation=UserTier.free,
        generated_at=datetime(2026, 1, 10, 6, 0),
    )
    db.add(digest)
    await db.flush()

    # Create a new article after the digest
    new = _make_article(source.id, "New Article", published_at=datetime(2026, 1, 15))
    db.add(new)
    await db.flush()

    stage = CollectStage()
    articles = await stage.collect(db, user.id)
    assert len(articles) == 1
    assert articles[0].title == "New Article"


async def test_collect_uses_created_at_for_null_published(db, user, source):
    # Create digest
    digest = Digest(
        user_id=user.id,
        date=datetime(2026, 1, 10).date(),
        tier_at_creation=UserTier.free,
        generated_at=datetime(2026, 1, 10, 6, 0),
    )
    db.add(digest)
    await db.flush()

    # Article with no published_at (created_at is auto-set to now())
    article = _make_article(source.id, "No Pub Date")
    db.add(article)
    await db.flush()

    stage = CollectStage()
    articles = await stage.collect(db, user.id)
    # created_at is now() which is after the digest
    assert len(articles) == 1


async def test_collect_skips_inactive_sources(db, user):
    inactive = Source(
        user_id=user.id, type=SourceType.rss, name="Inactive", is_active=False
    )
    db.add(inactive)
    await db.flush()

    article = _make_article(inactive.id, "Should Not Appear")
    db.add(article)
    await db.flush()

    stage = CollectStage()
    articles = await stage.collect(db, user.id)
    assert len(articles) == 0


async def test_collect_empty_when_no_sources(db, user):
    stage = CollectStage()
    articles = await stage.collect(db, user.id)
    assert articles == []
