from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from digest.models import Source, SourceType


class SourceStore:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self, user_id: uuid.UUID, type: SourceType, name: str, config: dict
    ) -> Source:
        self._validate_config(type, config)
        source = Source(user_id=user_id, type=type, name=name, config=config)
        self.db.add(source)
        await self.db.flush()
        return source

    async def list_for_user(self, user_id: uuid.UUID) -> list[Source]:
        stmt = (
            select(Source)
            .where(Source.user_id == user_id, Source.is_active.is_(True))
            .order_by(Source.created_at.desc())
        )
        return list((await self.db.scalars(stmt)).all())

    async def get_by_id(self, source_id: uuid.UUID) -> Source | None:
        return await self.db.get(Source, source_id)

    async def update(
        self,
        source_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str | None = None,
        config: dict | None = None,
        is_active: bool | None = None,
    ) -> Source:
        source = await self._get_owned(source_id, user_id)
        if name is not None:
            source.name = name
        if config is not None:
            self._validate_config(source.type, config)
            source.config = config
        if is_active is not None:
            source.is_active = is_active
        await self.db.flush()
        return source

    async def delete(self, source_id: uuid.UUID, user_id: uuid.UUID) -> None:
        source = await self._get_owned(source_id, user_id)
        source.is_active = False
        await self.db.flush()

    async def _get_owned(self, source_id: uuid.UUID, user_id: uuid.UUID) -> Source:
        source = await self.db.get(Source, source_id)
        if not source or source.user_id != user_id:
            raise HTTPException(status_code=404, detail="Source not found")
        return source

    @staticmethod
    def _validate_config(type: SourceType, config: dict) -> None:
        if type == SourceType.rss and not config.get("url"):
            raise HTTPException(
                status_code=422,
                detail="RSS sources require a 'url' in config",
            )
        if type == SourceType.reddit and not config.get("subreddit"):
            raise HTTPException(
                status_code=422,
                detail="Reddit sources require a 'subreddit' in config",
            )
