import uuid
from unittest.mock import AsyncMock, patch

import pytest

from digest.models import Article, UserTier
from digest.services.llm import GroupingResult, GroupResult, LLMService
from digest.services.pipeline.dedup import DedupGroup
from digest.services.pipeline.group import GroupStage


def _article(title="Title", content_text="content"):
    return Article(
        id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        title=title,
        content_text=content_text,
        fingerprint=Article.generate_fingerprint(title, content_text),
    )


def _dedup_group(article):
    return DedupGroup(primary=article)


async def test_tfidf_groups_related_articles():
    a1 = _article(
        "Python machine learning tutorial",
        "Learn about python programming and machine learning algorithms with tensorflow",
    )
    a2 = _article(
        "Python deep learning guide",
        "Guide to python programming and deep learning with machine learning libraries",
    )
    a3 = _article(
        "Stock market analysis today",
        "Financial markets showed gains in the stock trading session today",
    )

    groups_in = [_dedup_group(a) for a in [a1, a2, a3]]
    stage = GroupStage()
    result = await stage.group(groups_in, UserTier.free)

    # a1 and a2 share python/machine/learning keywords, a3 is separate
    assert len(result) == 2
    sizes = sorted([len(g.articles) for g in result])
    assert sizes == [1, 2]


async def test_tfidf_single_article():
    a1 = _article("Unique Article", "Completely unique content here")
    stage = GroupStage()
    result = await stage.group([_dedup_group(a1)], UserTier.free)

    assert len(result) == 1
    assert len(result[0].articles) == 1


async def test_tfidf_no_summaries():
    a1 = _article("Article One", "Some content about technology")
    stage = GroupStage()
    result = await stage.group([_dedup_group(a1)], UserTier.free)

    assert result[0].group_summary is None
    assert result[0].article_summaries == {}


async def test_empty_input():
    stage = GroupStage()
    result = await stage.group([], UserTier.free)
    assert result == []


async def test_paid_tier_llm_grouping():
    a1 = _article("AI News", "AI developments today")
    a2 = _article("Sports Update", "Game results from today")

    llm = LLMService(model="test", api_key="test")
    mock_group = AsyncMock(
        return_value=GroupingResult(
            groups=[
                GroupResult(
                    topic_label="Artificial Intelligence",
                    article_indices=[0],
                    primary_index=0,
                    group_summary="AI developments",
                    article_summaries={0: "Summary of AI"},
                ),
                GroupResult(
                    topic_label="Sports",
                    article_indices=[1],
                    primary_index=1,
                    group_summary="Sports results",
                    article_summaries={1: "Summary of sports"},
                ),
            ]
        )
    )

    stage = GroupStage(llm=llm)
    with patch.object(llm, "group_and_summarize", mock_group):
        result = await stage.group(
            [_dedup_group(a1), _dedup_group(a2)], UserTier.paid
        )

    assert len(result) == 2
    assert result[0].topic_label == "Artificial Intelligence"
    assert result[0].group_summary == "AI developments"
    assert result[1].topic_label == "Sports"


async def test_paid_tier_fallback_to_tfidf():
    a1 = _article("Python tutorial guide", "Learn python programming basics here")
    a2 = _article("Java tutorial guide", "Learn java programming basics today")

    llm = LLMService(model="test", api_key="test")
    mock_group = AsyncMock(side_effect=Exception("API Error"))

    stage = GroupStage(llm=llm)
    with patch.object(llm, "group_and_summarize", mock_group):
        result = await stage.group(
            [_dedup_group(a1), _dedup_group(a2)], UserTier.paid
        )

    # Should fall back to TF-IDF grouping
    assert len(result) >= 1
    # No AI summaries in fallback
    for g in result:
        assert g.group_summary is None


async def test_tfidf_topic_labels_generated():
    a1 = _article(
        "Python web development",
        "Building web applications with python django framework development",
    )
    stage = GroupStage()
    result = await stage.group([_dedup_group(a1)], UserTier.free)

    assert len(result) == 1
    # Label should be generated from keywords
    assert result[0].topic_label != ""
    assert result[0].topic_label != "General"
