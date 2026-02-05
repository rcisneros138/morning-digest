from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import litellm

from digest.config import settings

logger = logging.getLogger(__name__)

DEDUP_PROMPT = """\
You are a deduplication assistant. Given a list of articles (index, title, snippet), \
identify groups of articles that cover the same story or event.

Return JSON: {{"groups": [[idx, idx, ...], ...]}}
Only include groups with 2+ articles. Indices not in any group are unique.

Articles:
{articles}
"""

GROUPING_PROMPT = """\
You are a content curator. Given a list of articles (index, title, snippet), \
group them by topic, provide a label and summary for each group, \
mark the primary (most comprehensive) article in each group, \
and write a brief summary for each article.

Return JSON:
{{"groups": [
  {{
    "topic_label": "string",
    "article_indices": [idx, ...],
    "primary_index": idx,
    "group_summary": "string",
    "article_summaries": {{"idx": "summary", ...}}
  }},
  ...
]}}

Every article must appear in exactly one group. Single-article groups are fine.

Articles:
{articles}
"""


@dataclass
class DeduplicationResult:
    groups: list[list[int]] = field(default_factory=list)


@dataclass
class GroupResult:
    topic_label: str
    article_indices: list[int]
    primary_index: int
    group_summary: str
    article_summaries: dict[int, str]


@dataclass
class GroupingResult:
    groups: list[GroupResult] = field(default_factory=list)


def _format_articles(articles: list[dict]) -> str:
    lines = []
    for i, a in enumerate(articles):
        title = a.get("title", "")
        snippet = (a.get("content_text") or "")[:200]
        lines.append(f"[{i}] {title} — {snippet}")
    return "\n".join(lines)


class LLMService:
    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        temperature: float | None = None,
        timeout: int | None = None,
    ):
        self.model = model or settings.llm_model
        self.api_key = api_key or settings.llm_api_key
        self.temperature = temperature if temperature is not None else settings.llm_temperature
        self.timeout = timeout or settings.llm_timeout

    async def _call(self, prompt: str) -> dict:
        response = await litellm.acompletion(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=self.temperature,
            timeout=self.timeout,
            api_key=self.api_key or None,
        )
        text = response.choices[0].message.content
        return json.loads(text)

    async def find_semantic_duplicates(
        self, articles: list[dict], max_retries: int = 2
    ) -> DeduplicationResult:
        prompt = DEDUP_PROMPT.format(articles=_format_articles(articles))
        for attempt in range(max_retries + 1):
            try:
                data = await self._call(prompt)
                groups = [list(g) for g in data.get("groups", []) if len(g) >= 2]
                return DeduplicationResult(groups=groups)
            except Exception:
                if attempt == max_retries:
                    logger.exception("LLM dedup failed after retries")
                    return DeduplicationResult()
        return DeduplicationResult()

    async def group_and_summarize(
        self, articles: list[dict], max_retries: int = 2
    ) -> GroupingResult:
        prompt = GROUPING_PROMPT.format(articles=_format_articles(articles))
        for attempt in range(max_retries + 1):
            try:
                data = await self._call(prompt)
                groups = []
                for g in data.get("groups", []):
                    groups.append(
                        GroupResult(
                            topic_label=g["topic_label"],
                            article_indices=g["article_indices"],
                            primary_index=g["primary_index"],
                            group_summary=g.get("group_summary", ""),
                            article_summaries={
                                int(k): v
                                for k, v in g.get("article_summaries", {}).items()
                            },
                        )
                    )
                return GroupingResult(groups=groups)
            except Exception:
                if attempt == max_retries:
                    logger.exception("LLM grouping failed after retries")
                    return GroupingResult()
        return GroupingResult()
