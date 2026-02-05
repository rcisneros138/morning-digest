from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from digest.models import InteractionType, UserInteraction, UserTier
from digest.services.pipeline.group import TopicGroup

INTERACTION_WEIGHTS: dict[InteractionType, float] = {
    InteractionType.read: 1.0,
    InteractionType.tapped_through: 2.0,
    InteractionType.saved: 3.0,
    InteractionType.dismissed: -2.0,
}

PERSONALIZATION_DAMPEN = 0.5


class RankStage:
    async def rank(
        self,
        groups: list[TopicGroup],
        tier: UserTier,
        db: AsyncSession | None = None,
        user_id: uuid.UUID | None = None,
    ) -> list[TopicGroup]:
        if not groups:
            return []

        # Sort items within each group by published_at desc
        for group in groups:
            group.articles.sort(
                key=lambda a: (a.published_at or a.created_at),
                reverse=True,
            )

        if tier == UserTier.paid and db and user_id:
            return await self._personalized_rank(groups, db, user_id)

        return self._base_rank(groups)

    def _base_rank(self, groups: list[TopicGroup]) -> list[TopicGroup]:
        return sorted(groups, key=lambda g: len(g.articles), reverse=True)

    async def _personalized_rank(
        self,
        groups: list[TopicGroup],
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> list[TopicGroup]:
        # Fetch user interaction history
        interactions = (
            await db.scalars(
                select(UserInteraction).where(
                    UserInteraction.user_id == user_id
                )
            )
        ).all()

        if not interactions:
            return self._base_rank(groups)

        # Build per-article score from interaction history
        article_scores: dict[uuid.UUID, float] = defaultdict(float)
        for interaction in interactions:
            weight = INTERACTION_WEIGHTS.get(interaction.type, 0)
            article_scores[interaction.article_id] += weight

        # Score each group based on its articles' interaction scores
        group_scores: list[tuple[float, int, TopicGroup]] = []
        for idx, group in enumerate(groups):
            base = len(group.articles)
            personalization = sum(
                article_scores.get(a.id, 0) for a in group.articles
            )
            score = base + personalization * PERSONALIZATION_DAMPEN
            group_scores.append((score, idx, group))

        group_scores.sort(key=lambda x: x[0], reverse=True)
        return [g for _, _, g in group_scores]
