from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from digest.auth import get_current_user_id
from digest.database import async_session
from digest.models import SourceType
from digest.services.source_store import SourceStore

router = APIRouter(prefix="/sources", tags=["sources"])


class SourceCreateRequest(BaseModel):
    type: SourceType
    name: str
    config: dict = {}


class SourceUpdateRequest(BaseModel):
    name: str | None = None
    config: dict | None = None
    is_active: bool | None = None


class SourceResponse(BaseModel):
    id: uuid.UUID
    type: SourceType
    name: str
    config: dict
    is_active: bool

    model_config = {"from_attributes": True}


@router.post("/", status_code=201, response_model=SourceResponse)
async def create_source(
    body: SourceCreateRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    async with async_session() as db:
        store = SourceStore(db)
        source = await store.create(user_id, body.type, body.name, body.config)
        await db.commit()
        return SourceResponse.model_validate(source)


@router.get("/", response_model=list[SourceResponse])
async def list_sources(user_id: uuid.UUID = Depends(get_current_user_id)):
    async with async_session() as db:
        store = SourceStore(db)
        sources = await store.list_for_user(user_id)
        return [SourceResponse.model_validate(s) for s in sources]


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    async with async_session() as db:
        store = SourceStore(db)
        source = await store._get_owned(source_id, user_id)
        return SourceResponse.model_validate(source)


@router.patch("/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: uuid.UUID,
    body: SourceUpdateRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    async with async_session() as db:
        store = SourceStore(db)
        source = await store.update(
            source_id, user_id, name=body.name, config=body.config, is_active=body.is_active
        )
        await db.commit()
        return SourceResponse.model_validate(source)


@router.delete("/{source_id}", status_code=204)
async def delete_source(
    source_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    async with async_session() as db:
        store = SourceStore(db)
        await store.delete(source_id, user_id)
        await db.commit()
