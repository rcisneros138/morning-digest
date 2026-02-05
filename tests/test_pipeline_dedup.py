import uuid
from unittest.mock import AsyncMock, patch

import pytest

from digest.models import Article, UserTier
from digest.services.llm import DeduplicationResult, LLMService
from digest.services.pipeline.dedup import DedupStage


def _article(title="Title", content_text="content", fingerprint=None):
    a = Article(
        id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        title=title,
        content_text=content_text,
        fingerprint=fingerprint or Article.generate_fingerprint(title, content_text),
    )
    return a


async def test_fingerprint_dedup_groups_same_fingerprint():
    fp = Article.generate_fingerprint("Same Title", "Same content")
    a1 = _article("Same Title", "Same content", fingerprint=fp)
    a2 = _article("Same Title", "Same content but longer text here", fingerprint=fp)

    stage = DedupStage()
    groups = await stage.dedup([a1, a2], UserTier.free)

    assert len(groups) == 1
    # Longer content_text should be primary
    assert groups[0].primary.content_text == "Same content but longer text here"
    assert len(groups[0].duplicates) == 1


async def test_fingerprint_dedup_unique_articles():
    a1 = _article("Article A", "Content A")
    a2 = _article("Article B", "Content B")

    stage = DedupStage()
    groups = await stage.dedup([a1, a2], UserTier.free)

    assert len(groups) == 2
    for g in groups:
        assert len(g.duplicates) == 0


async def test_dedup_empty_list():
    stage = DedupStage()
    groups = await stage.dedup([], UserTier.free)
    assert groups == []


async def test_paid_tier_semantic_dedup():
    a1 = _article("AI Breakthrough", "New model released today")
    a2 = _article("AI Model Launch", "A new AI model was launched")
    a3 = _article("Stock Market Update", "Markets are up today")

    llm = LLMService(model="test", api_key="test")
    mock_dedup = AsyncMock(
        return_value=DeduplicationResult(groups=[[0, 1]])
    )

    stage = DedupStage(llm=llm)
    with patch.object(llm, "find_semantic_duplicates", mock_dedup):
        groups = await stage.dedup([a1, a2, a3], UserTier.paid)

    assert len(groups) == 2
    # a1 and a2 should be merged
    merged = [g for g in groups if len(g.duplicates) > 0]
    assert len(merged) == 1
    assert merged[0].primary.title == "AI Breakthrough"
    assert len(merged[0].duplicates) == 1


async def test_paid_tier_fallback_on_llm_failure():
    a1 = _article("Article A", "Content A")
    a2 = _article("Article B", "Content B")

    llm = LLMService(model="test", api_key="test")
    mock_dedup = AsyncMock(side_effect=Exception("API Error"))

    stage = DedupStage(llm=llm)
    with patch.object(llm, "find_semantic_duplicates", mock_dedup):
        groups = await stage.dedup([a1, a2], UserTier.paid)

    # Should fall back gracefully - still have 2 groups
    assert len(groups) == 2


async def test_free_tier_skips_semantic():
    a1 = _article("AI Breakthrough", "New model released today")
    a2 = _article("AI Model Launch", "A new AI model was launched")

    llm = LLMService(model="test", api_key="test")
    mock_dedup = AsyncMock()

    stage = DedupStage(llm=llm)
    with patch.object(llm, "find_semantic_duplicates", mock_dedup):
        groups = await stage.dedup([a1, a2], UserTier.free)

    # LLM should not be called for free tier
    mock_dedup.assert_not_called()
    assert len(groups) == 2
