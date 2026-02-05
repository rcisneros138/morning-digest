import uuid
from datetime import date, datetime

import pytest
from sqlalchemy import select

from digest.models import (
    Article,
    Digest,
    DigestGroup,
    DigestItem,
    InteractionType,
    Source,
    SourceType,
    User,
    UserInteraction,
    UserTier,
)


@pytest.fixture
async def user(db):
    u = User(email=f"digest-{uuid.uuid4().hex[:8]}@test.com", password_hash="x")
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
        content_text="Some content here for testing.",
        fingerprint=Article.generate_fingerprint("Test Article", "Some content here for testing."),
    )
    db.add(a)
    await db.flush()
    return a


async def test_create_digest(db, user):
    digest = Digest(
        user_id=user.id,
        date=date(2026, 1, 15),
        tier_at_creation=UserTier.free,
        generated_at=datetime(2026, 1, 15, 6, 0, 0),
    )
    db.add(digest)
    await db.flush()

    result = await db.get(Digest, digest.id)
    assert result is not None
    assert result.user_id == user.id
    assert result.date == date(2026, 1, 15)
    assert result.tier_at_creation == UserTier.free


async def test_digest_unique_constraint(db, user):
    d1 = Digest(
        user_id=user.id,
        date=date(2026, 2, 1),
        tier_at_creation=UserTier.free,
        generated_at=datetime(2026, 2, 1, 6, 0, 0),
    )
    db.add(d1)
    await db.flush()

    d2 = Digest(
        user_id=user.id,
        date=date(2026, 2, 1),
        tier_at_creation=UserTier.free,
        generated_at=datetime(2026, 2, 1, 7, 0, 0),
    )
    db.add(d2)
    with pytest.raises(Exception):
        await db.flush()


async def test_digest_group_item_chain(db, user, article):
    digest = Digest(
        user_id=user.id,
        date=date(2026, 1, 20),
        tier_at_creation=UserTier.paid,
        generated_at=datetime(2026, 1, 20, 6, 0, 0),
    )
    db.add(digest)
    await db.flush()

    group = DigestGroup(
        digest_id=digest.id,
        topic_label="Technology",
        sort_order=0,
        summary="A group about tech.",
    )
    db.add(group)
    await db.flush()

    item = DigestItem(
        group_id=group.id,
        article_id=article.id,
        sort_order=0,
        ai_summary="AI-generated summary.",
        is_primary=True,
    )
    db.add(item)
    await db.flush()

    # Verify relationships
    await db.refresh(digest, ["groups"])
    assert len(digest.groups) == 1
    assert digest.groups[0].topic_label == "Technology"

    await db.refresh(group, ["items"])
    assert len(group.items) == 1
    assert group.items[0].is_primary is True
    assert group.items[0].ai_summary == "AI-generated summary."


async def test_user_interaction(db, user, article):
    interaction = UserInteraction(
        user_id=user.id,
        article_id=article.id,
        type=InteractionType.saved,
    )
    db.add(interaction)
    await db.flush()

    result = await db.get(UserInteraction, interaction.id)
    assert result is not None
    assert result.type == InteractionType.saved
    assert result.user_id == user.id
    assert result.article_id == article.id


async def test_digest_item_defaults(db, user, article):
    digest = Digest(
        user_id=user.id,
        date=date(2026, 3, 1),
        tier_at_creation=UserTier.free,
        generated_at=datetime(2026, 3, 1, 6, 0, 0),
    )
    db.add(digest)
    await db.flush()

    group = DigestGroup(digest_id=digest.id, topic_label="General", sort_order=0)
    db.add(group)
    await db.flush()

    item = DigestItem(group_id=group.id, article_id=article.id, sort_order=0)
    db.add(item)
    await db.flush()

    assert item.is_primary is False
    assert item.ai_summary is None
    assert group.summary is None
