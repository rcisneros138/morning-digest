from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from digest.models import Article, Digest, Source


class CollectStage:
    async def collect(self, db: AsyncSession, user_id: uuid.UUID) -> list[Article]:
        # Find last digest date for the user
        last_digest = await db.scalar(
            select(Digest.generated_at)
            .where(Digest.user_id == user_id)
            .order_by(Digest.generated_at.desc())
            .limit(1)
        )

        # Get active source IDs for this user
        source_ids = (
            await db.scalars(
                select(Source.id).where(
                    Source.user_id == user_id,
                    Source.is_active.is_(True),
                )
            )
        ).all()

        if not source_ids:
            return []

        # Build article query
        stmt = select(Article).where(Article.source_id.in_(source_ids))

        if last_digest is not None:
            # Articles published or created after last digest
            stmt = stmt.where(
                (Article.published_at > last_digest)
                | (
                    Article.published_at.is_(None)
                    & (Article.created_at > last_digest)
                )
            )

        stmt = stmt.order_by(Article.created_at.desc())

        result = await db.scalars(stmt)
        return list(result.all())
