from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from digest.models import Digest, DigestGroup, DigestItem


class DigestStore:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _base_query(self):
        return (
            select(Digest)
            .options(
                selectinload(Digest.groups)
                .selectinload(DigestGroup.items)
                .selectinload(DigestItem.article)
            )
        )

    async def get_latest(self, user_id: uuid.UUID) -> Digest | None:
        stmt = (
            self._base_query()
            .where(Digest.user_id == user_id)
            .order_by(Digest.date.desc())
            .limit(1)
        )
        return await self.db.scalar(stmt)

    async def get_by_id(self, digest_id: uuid.UUID) -> Digest | None:
        stmt = self._base_query().where(Digest.id == digest_id)
        return await self.db.scalar(stmt)

    async def list_digests(
        self, user_id: uuid.UUID, limit: int = 20, offset: int = 0
    ) -> list[Digest]:
        stmt = (
            select(Digest)
            .where(Digest.user_id == user_id)
            .order_by(Digest.date.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self.db.scalars(stmt)).all())
