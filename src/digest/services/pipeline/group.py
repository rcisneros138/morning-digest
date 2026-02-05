from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field

from digest.models import Article, UserTier
from digest.services.llm import LLMService
from digest.services.pipeline.dedup import DedupGroup

logger = logging.getLogger(__name__)

# Common English stop words for TF-IDF
_STOP_WORDS = frozenset(
    "a an the is are was were be been being have has had do does did will would "
    "shall should may might can could of in to for on with at by from as into "
    "through during before after above below between out off over under again "
    "further then once here there when where why how all each every both few "
    "more most other some such no nor not only own same so than too very and "
    "but if or because until while about against".split()
)


@dataclass
class TopicGroup:
    topic_label: str
    articles: list[Article]
    primary_index: int = 0
    group_summary: str | None = None
    article_summaries: dict[int, str] = field(default_factory=dict)


class GroupStage:
    def __init__(self, llm: LLMService | None = None):
        self.llm = llm

    async def group(
        self, dedup_groups: list[DedupGroup], tier: UserTier
    ) -> list[TopicGroup]:
        if not dedup_groups:
            return []

        # Extract primaries for grouping
        primaries = [g.primary for g in dedup_groups]

        if tier == UserTier.paid and self.llm:
            result = await self._llm_group(primaries)
            if result:
                return result
            logger.warning("LLM grouping failed, falling back to TF-IDF")

        return self._tfidf_group(primaries)

    def _tokenize(self, text: str) -> list[str]:
        words = re.findall(r"[a-z]+", (text or "").lower())
        return [w for w in words if w not in _STOP_WORDS and len(w) > 2]

    def _tfidf_group(self, articles: list[Article]) -> list[TopicGroup]:
        if not articles:
            return []

        # Build document term frequencies
        doc_tokens: list[list[str]] = []
        doc_tf: list[dict[str, float]] = []
        df: dict[str, int] = {}

        for a in articles:
            text = f"{a.title or ''} {a.content_text or ''}"
            tokens = self._tokenize(text)
            doc_tokens.append(tokens)

            # Term frequency
            tf: dict[str, float] = {}
            for t in tokens:
                tf[t] = tf.get(t, 0) + 1
            total = len(tokens) or 1
            for t in tf:
                tf[t] /= total
            doc_tf.append(tf)

            # Document frequency
            for t in set(tokens):
                df[t] = df.get(t, 0) + 1

        n = len(articles)

        # TF-IDF keywords per document (top 10)
        doc_keywords: list[set[str]] = []
        for tf in doc_tf:
            scored = {}
            for term, freq in tf.items():
                idf = math.log((n + 1) / (df.get(term, 0) + 1)) + 1
                scored[term] = freq * idf
            top = sorted(scored, key=scored.get, reverse=True)[:10]
            doc_keywords.append(set(top))

        # Greedy grouping: 2+ shared keywords
        assigned: set[int] = set()
        groups: list[TopicGroup] = []

        for i in range(n):
            if i in assigned:
                continue
            cluster = [i]
            assigned.add(i)
            for j in range(i + 1, n):
                if j in assigned:
                    continue
                shared = doc_keywords[i] & doc_keywords[j]
                if len(shared) >= 2:
                    cluster.append(j)
                    assigned.add(j)

            cluster_articles = [articles[idx] for idx in cluster]
            # Topic label from shared keywords
            if len(cluster) > 1:
                shared_all = doc_keywords[cluster[0]]
                for idx in cluster[1:]:
                    shared_all = shared_all & doc_keywords[idx]
                if not shared_all:
                    shared_all = doc_keywords[cluster[0]]
                label = ", ".join(sorted(shared_all)[:3]).title()
            else:
                label = ", ".join(sorted(doc_keywords[i])[:3]).title()

            groups.append(
                TopicGroup(
                    topic_label=label or "General",
                    articles=cluster_articles,
                    primary_index=0,
                )
            )

        return groups

    async def _llm_group(self, articles: list[Article]) -> list[TopicGroup] | None:
        batch_size = 20
        all_groups: list[TopicGroup] = []

        for start in range(0, len(articles), batch_size):
            batch = articles[start : start + batch_size]
            batch_dicts = [
                {"title": a.title, "content_text": a.content_text or ""}
                for a in batch
            ]

            try:
                result = await self.llm.group_and_summarize(batch_dicts)
            except Exception:
                logger.exception("LLM grouping failed for batch")
                return None

            if not result.groups:
                return None

            for g in result.groups:
                group_articles = [batch[i] for i in g.article_indices]
                # Map batch-local primary_index to group-local index
                primary_pos = (
                    g.article_indices.index(g.primary_index)
                    if g.primary_index in g.article_indices
                    else 0
                )
                all_groups.append(
                    TopicGroup(
                        topic_label=g.topic_label,
                        articles=group_articles,
                        primary_index=primary_pos,
                        group_summary=g.group_summary,
                        article_summaries={
                            g.article_indices.index(k)
                            if k in g.article_indices
                            else k: v
                            for k, v in g.article_summaries.items()
                        },
                    )
                )

        return all_groups
