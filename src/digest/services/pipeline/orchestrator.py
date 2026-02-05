from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from digest.models import Digest, DigestGroup, DigestItem, UserTier
from digest.services.llm import LLMService
from digest.services.pipeline.collect import CollectStage
from digest.services.pipeline.dedup import DedupStage
from digest.services.pipeline.group import GroupStage
from digest.services.pipeline.rank import RankStage


class Orchestrator:
    def __init__(self, llm: LLMService | None = None):
        self.collect_stage = CollectStage()
        self.dedup_stage = DedupStage(llm=llm)
        self.group_stage = GroupStage(llm=llm)
        self.rank_stage = RankStage()

    async def generate(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        tier: UserTier,
        digest_date: date | None = None,
    ) -> Digest | None:
        # Stage 1: Collect
        articles = await self.collect_stage.collect(db, user_id)
        if not articles:
            return None

        # Stage 2: Dedup
        dedup_groups = await self.dedup_stage.dedup(articles, tier)
        if not dedup_groups:
            return None

        # Stage 3: Group
        topic_groups = await self.group_stage.group(dedup_groups, tier)
        if not topic_groups:
            return None

        # Stage 4: Rank
        ranked = await self.rank_stage.rank(
            topic_groups, tier, db=db, user_id=user_id
        )

        # Build DB records
        now = datetime.now(UTC).replace(tzinfo=None)
        digest = Digest(
            user_id=user_id,
            date=digest_date or now.date(),
            tier_at_creation=tier,
            generated_at=now,
        )
        db.add(digest)
        await db.flush()

        for sort_order, tg in enumerate(ranked):
            group = DigestGroup(
                digest_id=digest.id,
                topic_label=tg.topic_label,
                sort_order=sort_order,
                summary=tg.group_summary,
            )
            db.add(group)
            await db.flush()

            for item_order, article in enumerate(tg.articles):
                is_primary = item_order == tg.primary_index
                ai_summary = tg.article_summaries.get(item_order)
                item = DigestItem(
                    group_id=group.id,
                    article_id=article.id,
                    sort_order=item_order,
                    ai_summary=ai_summary,
                    is_primary=is_primary,
                )
                db.add(item)

            await db.flush()

        return digest
