"""Integration tests for the full curation pipeline."""

import json
import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import pytest

from digest.models import (
    Article,
    Source,
    SourceType,
    User,
    UserTier,
)
from digest.services.llm import DeduplicationResult, GroupingResult, GroupResult, LLMService
from digest.services.pipeline.orchestrator import Orchestrator


@pytest.fixture
async def free_user(db):
    u = User(
        email=f"free-{uuid.uuid4().hex[:8]}@test.com",
        password_hash="x",
        tier=UserTier.free,
    )
    db.add(u)
    await db.flush()
    return u


@pytest.fixture
async def paid_user(db):
    u = User(
        email=f"paid-{uuid.uuid4().hex[:8]}@test.com",
        password_hash="x",
        tier=UserTier.paid,
    )
    db.add(u)
    await db.flush()
    return u


@pytest.fixture
async def source_for(db):
    async def _make(user):
        s = Source(user_id=user.id, type=SourceType.rss, name="Integration Feed")
        db.add(s)
        await db.flush()
        return s

    return _make


def _add_articles(db, source_id, articles_data):
    articles = []
    for data in articles_data:
        a = Article(
            source_id=source_id,
            title=data["title"],
            content_text=data.get("content_text", "Default content"),
            url=data.get("url"),
            author=data.get("author"),
            published_at=data.get("published_at"),
            fingerprint=data.get("fingerprint")
            or Article.generate_fingerprint(
                data["title"], data.get("content_text", "Default content")
            ),
        )
        db.add(a)
        articles.append(a)
    return articles


# ---------- Free tier integration ----------


async def test_free_tier_full_pipeline(db, free_user, source_for):
    source = await source_for(free_user)

    # 10 articles: 2 share a fingerprint (duplicates), rest are unique
    dup_fp = Article.generate_fingerprint("Breaking News", "Big event happened today")
    articles_data = [
        {
            "title": "Breaking News",
            "content_text": "Big event happened today",
            "fingerprint": dup_fp,
            "published_at": datetime(2026, 2, 1, 10, 0),
        },
        {
            "title": "Breaking News",
            "content_text": "Big event happened today with more detail and context",
            "fingerprint": dup_fp,
            "published_at": datetime(2026, 2, 1, 11, 0),
        },
        {
            "title": "Python programming tutorial basics",
            "content_text": "Learn python programming with this tutorial on basics and fundamentals",
            "published_at": datetime(2026, 2, 1, 9, 0),
        },
        {
            "title": "Python web development guide",
            "content_text": "Building web applications with python django programming framework",
            "published_at": datetime(2026, 2, 1, 8, 0),
        },
        {
            "title": "Stock market analysis report",
            "content_text": "Financial stock market analysis shows growth in technology sector",
            "published_at": datetime(2026, 2, 1, 7, 0),
        },
        {
            "title": "New electric vehicle launch",
            "content_text": "Latest electric vehicle launched by major manufacturer today",
            "published_at": datetime(2026, 2, 1, 6, 0),
        },
        {
            "title": "Climate change research findings",
            "content_text": "New research reveals climate change impact on global temperatures",
            "published_at": datetime(2026, 2, 1, 5, 0),
        },
        {
            "title": "Space exploration mission update",
            "content_text": "NASA space exploration mission reaches new milestone achievement",
            "published_at": datetime(2026, 2, 1, 4, 0),
        },
        {
            "title": "Healthcare innovation breakthrough",
            "content_text": "Medical healthcare innovation brings new treatment options available",
            "published_at": datetime(2026, 2, 1, 3, 0),
        },
        {
            "title": "Artificial intelligence advances",
            "content_text": "Recent artificial intelligence machine learning advances change industry",
            "published_at": datetime(2026, 2, 1, 2, 0),
        },
    ]

    _add_articles(db, source.id, articles_data)
    await db.flush()

    orch = Orchestrator()
    digest = await orch.generate(
        db, free_user.id, UserTier.free, digest_date=date(2026, 2, 2)
    )

    assert digest is not None
    assert digest.user_id == free_user.id
    assert digest.date == date(2026, 2, 2)
    assert digest.tier_at_creation == UserTier.free

    await db.refresh(digest, ["groups"])
    assert len(digest.groups) >= 1

    # Verify structure
    total_items = 0
    for group in digest.groups:
        assert group.topic_label != ""
        assert group.sort_order >= 0
        # Free tier: no group summaries
        assert group.summary is None

        await db.refresh(group, ["items"])
        assert len(group.items) >= 1

        for item in group.items:
            assert item.sort_order >= 0
            # Free tier: no AI summaries
            assert item.ai_summary is None
            total_items += 1

    # 10 articles - 1 duplicate = 9 unique articles in digest
    assert total_items == 9


# ---------- Paid tier integration ----------


async def test_paid_tier_full_pipeline(db, paid_user, source_for):
    source = await source_for(paid_user)

    articles_data = [
        {
            "title": "AI Model Released",
            "content_text": "A major new AI model was released by leading company",
            "published_at": datetime(2026, 2, 1, 10, 0),
        },
        {
            "title": "New AI System Launches",
            "content_text": "New artificial intelligence system launches with advanced capabilities",
            "published_at": datetime(2026, 2, 1, 9, 0),
        },
        {
            "title": "Stock Market Rally",
            "content_text": "Markets surged today on positive economic data reports",
            "published_at": datetime(2026, 2, 1, 8, 0),
        },
        {
            "title": "Tech Earnings Report",
            "content_text": "Major tech company reports record quarterly earnings growth",
            "published_at": datetime(2026, 2, 1, 7, 0),
        },
    ]

    added = _add_articles(db, source.id, articles_data)
    await db.flush()

    # Canned LLM responses
    dedup_response = DeduplicationResult(groups=[[0, 1]])  # AI articles are duplicates

    grouping_response = GroupingResult(
        groups=[
            GroupResult(
                topic_label="Artificial Intelligence",
                article_indices=[0],
                primary_index=0,
                group_summary="Major AI developments this week.",
                article_summaries={0: "A new AI model was released."},
            ),
            GroupResult(
                topic_label="Financial Markets",
                article_indices=[1, 2],
                primary_index=1,
                group_summary="Markets and tech earnings update.",
                article_summaries={
                    1: "Markets rallied on positive data.",
                    2: "Tech company reports record earnings.",
                },
            ),
        ]
    )

    llm = LLMService(model="test", api_key="test")

    with (
        patch.object(
            llm, "find_semantic_duplicates", AsyncMock(return_value=dedup_response)
        ),
        patch.object(
            llm, "group_and_summarize", AsyncMock(return_value=grouping_response)
        ),
    ):
        orch = Orchestrator(llm=llm)
        digest = await orch.generate(
            db, paid_user.id, UserTier.paid, digest_date=date(2026, 2, 2)
        )

    assert digest is not None
    assert digest.tier_at_creation == UserTier.paid

    await db.refresh(digest, ["groups"])
    assert len(digest.groups) == 2

    # Verify AI summaries present
    has_group_summary = False
    has_ai_summary = False
    has_primary = False

    for group in digest.groups:
        if group.summary:
            has_group_summary = True

        await db.refresh(group, ["items"])
        for item in group.items:
            if item.ai_summary:
                has_ai_summary = True
            if item.is_primary:
                has_primary = True

    assert has_group_summary, "Paid tier should have group summaries"
    assert has_ai_summary, "Paid tier should have AI article summaries"
    assert has_primary, "Paid tier should mark primary articles"


# ---------- Edge cases ----------


async def test_no_articles_returns_none(db, free_user, source_for):
    await source_for(free_user)

    orch = Orchestrator()
    digest = await orch.generate(db, free_user.id, UserTier.free)
    assert digest is None


async def test_all_duplicates_still_produces_digest(db, free_user, source_for):
    source = await source_for(free_user)

    fp = Article.generate_fingerprint("Same Story", "Same content everywhere")
    articles_data = [
        {"title": "Same Story", "content_text": "Same content everywhere", "fingerprint": fp},
        {"title": "Same Story", "content_text": "Same content everywhere plus extra", "fingerprint": fp},
        {"title": "Same Story", "content_text": "Same content everywhere plus even more", "fingerprint": fp},
    ]

    _add_articles(db, source.id, articles_data)
    await db.flush()

    orch = Orchestrator()
    digest = await orch.generate(db, free_user.id, UserTier.free)

    assert digest is not None
    await db.refresh(digest, ["groups"])

    total_items = 0
    for group in digest.groups:
        await db.refresh(group, ["items"])
        total_items += len(group.items)

    # All 3 share fingerprint, so only 1 primary survives
    assert total_items == 1
