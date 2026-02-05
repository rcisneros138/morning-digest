import uuid
from datetime import datetime

import pytest

from digest.models import (
    Article,
    InteractionType,
    Source,
    SourceType,
    User,
    UserInteraction,
    UserTier,
)
from digest.services.pipeline.group import TopicGroup
from digest.services.pipeline.rank import RankStage


def _article(title="Title", published_at=None):
    a = Article(
        id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        title=title,
        content_text="content",
        fingerprint=Article.generate_fingerprint(title, "content"),
        published_at=published_at,
        created_at=datetime(2026, 1, 1),
    )
    return a


async def test_base_rank_by_article_count():
    big = TopicGroup(
        topic_label="Big",
        articles=[_article("A1"), _article("A2"), _article("A3")],
    )
    small = TopicGroup(
        topic_label="Small",
        articles=[_article("B1")],
    )
    medium = TopicGroup(
        topic_label="Medium",
        articles=[_article("C1"), _article("C2")],
    )

    stage = RankStage()
    result = await stage.rank([small, big, medium], UserTier.free)

    assert [g.topic_label for g in result] == ["Big", "Medium", "Small"]


async def test_items_sorted_by_recency():
    old = _article("Old", published_at=datetime(2026, 1, 1))
    new = _article("New", published_at=datetime(2026, 1, 15))
    group = TopicGroup(topic_label="Test", articles=[old, new])

    stage = RankStage()
    result = await stage.rank([group], UserTier.free)

    assert result[0].articles[0].title == "New"
    assert result[0].articles[1].title == "Old"


async def test_empty_groups():
    stage = RankStage()
    result = await stage.rank([], UserTier.free)
    assert result == []


@pytest.fixture
async def user(db):
    u = User(email=f"rank-{uuid.uuid4().hex[:8]}@test.com", password_hash="x")
    db.add(u)
    await db.flush()
    return u


@pytest.fixture
async def source(db, user):
    s = Source(user_id=user.id, type=SourceType.rss, name="Test Feed")
    db.add(s)
    await db.flush()
    return s


async def test_personalized_rank_boosts_saved(db, user, source):
    # Create articles in DB for interaction tracking
    liked_art = Article(
        source_id=source.id,
        title="Liked Article",
        content_text="content",
        fingerprint=Article.generate_fingerprint("Liked Article", "content"),
    )
    db.add(liked_art)
    await db.flush()

    # User saved this article (weight=3)
    interaction = UserInteraction(
        user_id=user.id,
        article_id=liked_art.id,
        type=InteractionType.saved,
    )
    db.add(interaction)
    await db.flush()

    # Group with liked article (1 article, but has personalization boost)
    liked_group = TopicGroup(topic_label="Liked", articles=[liked_art])
    # Group with 2 articles but no interactions
    other1 = _article("Other1")
    other2 = _article("Other2")
    big_group = TopicGroup(topic_label="Big", articles=[other1, other2])

    stage = RankStage()
    result = await stage.rank(
        [big_group, liked_group], UserTier.paid, db=db, user_id=user.id
    )

    # liked_group: base=1 + 3*0.5=2.5 -> total=2.5
    # big_group: base=2 + 0 -> total=2.0
    assert result[0].topic_label == "Liked"


async def test_personalized_rank_dismissed_penalizes(db, user, source):
    disliked_art = Article(
        source_id=source.id,
        title="Disliked Article",
        content_text="bad content",
        fingerprint=Article.generate_fingerprint("Disliked Article", "bad content"),
    )
    db.add(disliked_art)
    await db.flush()

    interaction = UserInteraction(
        user_id=user.id,
        article_id=disliked_art.id,
        type=InteractionType.dismissed,
    )
    db.add(interaction)
    await db.flush()

    penalized = TopicGroup(
        topic_label="Penalized",
        articles=[disliked_art, _article("Filler")],
    )
    neutral = TopicGroup(
        topic_label="Neutral",
        articles=[_article("N1"), _article("N2")],
    )

    stage = RankStage()
    result = await stage.rank(
        [penalized, neutral], UserTier.paid, db=db, user_id=user.id
    )

    # penalized: base=2 + (-2*0.5) = 1.0
    # neutral: base=2 + 0 = 2.0
    assert result[0].topic_label == "Neutral"


async def test_paid_no_interactions_falls_back_to_base(db, user):
    big = TopicGroup(
        topic_label="Big",
        articles=[_article("A"), _article("B"), _article("C")],
    )
    small = TopicGroup(topic_label="Small", articles=[_article("D")])

    stage = RankStage()
    result = await stage.rank(
        [small, big], UserTier.paid, db=db, user_id=user.id
    )

    assert result[0].topic_label == "Big"
