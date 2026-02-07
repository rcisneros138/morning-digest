from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from digest.auth import get_current_user_id
from digest.database import async_session
from digest.models import InteractionType, UserInteraction
from digest.services.digest_store import DigestStore

router = APIRouter(prefix="/digests", tags=["digests"])


class ArticleResponse(BaseModel):
    id: uuid.UUID
    title: str
    url: str | None
    author: str | None
    ai_summary: str | None
    is_primary: bool

    model_config = {"from_attributes": True}


class GroupResponse(BaseModel):
    id: uuid.UUID
    topic_label: str
    sort_order: int
    summary: str | None
    articles: list[ArticleResponse]

    model_config = {"from_attributes": True}


class DigestResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    date: str
    tier_at_creation: str
    generated_at: str
    groups: list[GroupResponse]

    model_config = {"from_attributes": True}


class DigestListItem(BaseModel):
    id: uuid.UUID
    date: str
    tier_at_creation: str
    generated_at: str

    model_config = {"from_attributes": True}


class InteractionRequest(BaseModel):
    article_id: uuid.UUID
    type: InteractionType


def _serialize_digest(digest) -> dict:
    groups = []
    for g in digest.groups:
        articles = []
        for item in g.items:
            articles.append(
                ArticleResponse(
                    id=item.article.id,
                    title=item.article.title,
                    url=item.article.url,
                    author=item.article.author,
                    ai_summary=item.ai_summary,
                    is_primary=item.is_primary,
                )
            )
        groups.append(
            GroupResponse(
                id=g.id,
                topic_label=g.topic_label,
                sort_order=g.sort_order,
                summary=g.summary,
                articles=articles,
            )
        )
    return DigestResponse(
        id=digest.id,
        user_id=digest.user_id,
        date=str(digest.date),
        tier_at_creation=digest.tier_at_creation.value,
        generated_at=str(digest.generated_at),
        groups=groups,
    )


@router.get("/latest")
async def get_latest_digest(user_id: uuid.UUID = Depends(get_current_user_id)):
    async with async_session() as db:
        store = DigestStore(db)
        digest = await store.get_latest(user_id)
        if not digest:
            raise HTTPException(status_code=404, detail="No digest found")
        return _serialize_digest(digest)


@router.get("/", response_model=list[DigestListItem])
async def list_digests(
    user_id: uuid.UUID = Depends(get_current_user_id),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    async with async_session() as db:
        store = DigestStore(db)
        digests = await store.list_digests(user_id, limit=limit, offset=offset)
        return [
            DigestListItem(
                id=d.id,
                date=str(d.date),
                tier_at_creation=d.tier_at_creation.value,
                generated_at=str(d.generated_at),
            )
            for d in digests
        ]


@router.get("/{digest_id}")
async def get_digest(
    digest_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    async with async_session() as db:
        store = DigestStore(db)
        digest = await store.get_by_id(digest_id)
        if not digest:
            raise HTTPException(status_code=404, detail="Digest not found")
        if digest.user_id != user_id:
            raise HTTPException(status_code=404, detail="Digest not found")
        return _serialize_digest(digest)


@router.post("/interactions", status_code=201)
async def create_interaction(
    body: InteractionRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    async with async_session() as db:
        interaction = UserInteraction(
            user_id=user_id,
            article_id=body.article_id,
            type=body.type,
        )
        db.add(interaction)
        await db.commit()
        return {"status": "created", "id": str(interaction.id)}
