from unittest.mock import AsyncMock, patch

import pytest

from digest.services.llm import DeduplicationResult, GroupingResult, LLMService


@pytest.fixture
def llm():
    return LLMService(model="test-model", api_key="test-key")


def _mock_response(content: str):
    mock = AsyncMock()
    mock.return_value.choices = [AsyncMock(message=AsyncMock(content=content))]
    return mock


async def test_find_semantic_duplicates(llm):
    articles = [
        {"title": "AI Breakthrough", "content_text": "New model released"},
        {"title": "AI Breakthrough Today", "content_text": "A new model was released"},
        {"title": "Stock Market", "content_text": "Markets are up"},
    ]
    mock = _mock_response('{"groups": [[0, 1]]}')
    with patch("digest.services.llm.litellm.acompletion", mock):
        result = await llm.find_semantic_duplicates(articles)

    assert isinstance(result, DeduplicationResult)
    assert result.groups == [[0, 1]]


async def test_find_semantic_duplicates_empty(llm):
    mock = _mock_response('{"groups": []}')
    with patch("digest.services.llm.litellm.acompletion", mock):
        result = await llm.find_semantic_duplicates([{"title": "A", "content_text": "B"}])

    assert result.groups == []


async def test_find_semantic_duplicates_filters_singles(llm):
    mock = _mock_response('{"groups": [[0], [1, 2]]}')
    with patch("digest.services.llm.litellm.acompletion", mock):
        result = await llm.find_semantic_duplicates([
            {"title": "A", "content_text": "a"},
            {"title": "B", "content_text": "b"},
            {"title": "C", "content_text": "c"},
        ])

    assert result.groups == [[1, 2]]


async def test_find_semantic_duplicates_fallback_on_error(llm):
    mock = AsyncMock(side_effect=Exception("API error"))
    with patch("digest.services.llm.litellm.acompletion", mock):
        result = await llm.find_semantic_duplicates(
            [{"title": "A", "content_text": "a"}], max_retries=0
        )

    assert result.groups == []


async def test_group_and_summarize(llm):
    articles = [
        {"title": "AI News", "content_text": "AI stuff"},
        {"title": "Sports", "content_text": "Game results"},
    ]
    response = {
        "groups": [
            {
                "topic_label": "Artificial Intelligence",
                "article_indices": [0],
                "primary_index": 0,
                "group_summary": "AI developments",
                "article_summaries": {"0": "Summary of AI news"},
            },
            {
                "topic_label": "Sports",
                "article_indices": [1],
                "primary_index": 1,
                "group_summary": "Sports results",
                "article_summaries": {"1": "Summary of sports"},
            },
        ]
    }
    import json

    mock = _mock_response(json.dumps(response))
    with patch("digest.services.llm.litellm.acompletion", mock):
        result = await llm.group_and_summarize(articles)

    assert isinstance(result, GroupingResult)
    assert len(result.groups) == 2
    assert result.groups[0].topic_label == "Artificial Intelligence"
    assert result.groups[0].primary_index == 0
    assert result.groups[0].article_summaries[0] == "Summary of AI news"


async def test_group_and_summarize_fallback_on_error(llm):
    mock = AsyncMock(side_effect=Exception("API error"))
    with patch("digest.services.llm.litellm.acompletion", mock):
        result = await llm.group_and_summarize(
            [{"title": "A", "content_text": "a"}], max_retries=0
        )

    assert result.groups == []
