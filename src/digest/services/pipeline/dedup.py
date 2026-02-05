from __future__ import annotations

import logging
from dataclasses import dataclass, field

from digest.models import Article, UserTier
from digest.services.llm import LLMService

logger = logging.getLogger(__name__)


@dataclass
class DedupGroup:
    primary: Article
    duplicates: list[Article] = field(default_factory=list)


class DedupStage:
    def __init__(self, llm: LLMService | None = None):
        self.llm = llm

    async def dedup(
        self, articles: list[Article], tier: UserTier
    ) -> list[DedupGroup]:
        if not articles:
            return []

        # Phase 1: fingerprint dedup (both tiers)
        groups = self._fingerprint_dedup(articles)

        if tier == UserTier.paid and self.llm:
            # Phase 2: semantic dedup on primaries
            groups = await self._semantic_dedup(groups)

        return groups

    def _fingerprint_dedup(self, articles: list[Article]) -> list[DedupGroup]:
        by_fingerprint: dict[str, list[Article]] = {}
        for a in articles:
            by_fingerprint.setdefault(a.fingerprint, []).append(a)

        groups = []
        for fp_articles in by_fingerprint.values():
            # Pick longest content_text as primary
            sorted_arts = sorted(
                fp_articles,
                key=lambda a: len(a.content_text or ""),
                reverse=True,
            )
            groups.append(
                DedupGroup(primary=sorted_arts[0], duplicates=sorted_arts[1:])
            )
        return groups

    async def _semantic_dedup(
        self, groups: list[DedupGroup]
    ) -> list[DedupGroup]:
        primaries = [g.primary for g in groups]
        if len(primaries) <= 1:
            return groups

        # Build lookup from primary to its group
        primary_to_group = {id(g.primary): g for g in groups}

        # Process in batches of 50
        batch_size = 50
        merged_indices: set[int] = set()
        final_groups: list[DedupGroup] = []

        for start in range(0, len(primaries), batch_size):
            batch = primaries[start : start + batch_size]
            batch_dicts = [
                {"title": a.title, "content_text": a.content_text or ""}
                for a in batch
            ]

            try:
                result = await self.llm.find_semantic_duplicates(batch_dicts)
            except Exception:
                logger.exception("Semantic dedup failed, using fingerprint-only results")
                result = None

            if result and result.groups:
                for sem_group in result.groups:
                    # Map batch-local indices to global indices
                    global_indices = [start + i for i in sem_group]
                    # Merge: first becomes primary, rest become duplicates
                    lead_idx = global_indices[0]
                    lead_group = primary_to_group[id(primaries[lead_idx])]
                    for idx in global_indices[1:]:
                        other_group = primary_to_group[id(primaries[idx])]
                        lead_group.duplicates.append(other_group.primary)
                        lead_group.duplicates.extend(other_group.duplicates)
                        merged_indices.add(idx)

        # Collect unmerged groups + merged lead groups
        for i, primary in enumerate(primaries):
            if i not in merged_indices:
                final_groups.append(primary_to_group[id(primary)])

        return final_groups
