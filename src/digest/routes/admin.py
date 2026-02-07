from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Header, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from digest.config import settings
from digest.database import async_session
from digest.models import Article, Digest, Source, SourceType, User

router = APIRouter(prefix="/admin", tags=["admin"])


async def require_admin_key(x_admin_key: str = Header(...)) -> str:
    if not settings.admin_api_key or x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid admin key")
    return x_admin_key


@router.get("/stats")
async def get_stats(_: str = Depends(require_admin_key)):
    async with async_session() as db:
        user_count = await db.scalar(select(func.count()).select_from(User))
        article_count = await db.scalar(select(func.count()).select_from(Article))
        digest_count = await db.scalar(select(func.count()).select_from(Digest))

        source_rows = (
            await db.execute(
                select(Source.type, func.count()).group_by(Source.type)
            )
        ).all()
        sources_by_type = {row[0].value: row[1] for row in source_rows}

        return {
            "users": user_count,
            "articles": article_count,
            "digests": digest_count,
            "sources_by_type": sources_by_type,
        }


@router.get("/users")
async def list_users(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: str = Depends(require_admin_key),
):
    async with async_session() as db:
        stmt = select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
        users = (await db.scalars(stmt)).all()
        result = []
        for u in users:
            source_count = await db.scalar(
                select(func.count()).select_from(Source).where(Source.user_id == u.id)
            )
            digest_count = await db.scalar(
                select(func.count()).select_from(Digest).where(Digest.user_id == u.id)
            )
            result.append(
                {
                    "id": str(u.id),
                    "email": u.email,
                    "tier": u.tier.value,
                    "created_at": str(u.created_at),
                    "source_count": source_count,
                    "digest_count": digest_count,
                }
            )
        return result


@router.post("/tasks/ingest")
async def trigger_ingest(_: str = Depends(require_admin_key)):
    from digest.tasks.ingest import poll_all_rss_feeds

    poll_all_rss_feeds.delay()
    return {"status": "enqueued", "task": "poll_all_rss_feeds"}


@router.post("/tasks/digest/{user_id}")
async def trigger_digest(user_id: uuid.UUID, _: str = Depends(require_admin_key)):
    from digest.tasks.generate_digest import generate_user_digest

    generate_user_digest.delay(str(user_id))
    return {"status": "enqueued", "task": "generate_user_digest", "user_id": str(user_id)}
