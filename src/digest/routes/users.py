from __future__ import annotations

import re
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from digest.auth import get_current_user_id
from digest.database import async_session
from digest.models import User, UserTier
from sqlalchemy import select

router = APIRouter(prefix="/users", tags=["users"])


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    tier: UserTier
    timezone: str
    digest_time: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    timezone: str | None = None
    digest_time: str | None = None
    email: EmailStr | None = None


_DIGEST_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


@router.get("/me", response_model=UserResponse)
async def get_me(user_id: uuid.UUID = Depends(get_current_user_id)):
    async with async_session() as db:
        user = await db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return UserResponse.model_validate(user)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UserUpdateRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    async with async_session() as db:
        user = await db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if body.timezone is not None:
            try:
                ZoneInfo(body.timezone)
            except (KeyError, ValueError):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Invalid timezone",
                )
            user.timezone = body.timezone

        if body.digest_time is not None:
            if not _DIGEST_TIME_RE.match(body.digest_time):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="digest_time must be HH:MM format",
                )
            h, m = body.digest_time.split(":")
            if not (0 <= int(h) <= 23 and 0 <= int(m) <= 59):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="digest_time must be a valid time",
                )
            user.digest_time = body.digest_time

        if body.email is not None:
            existing = await db.scalar(
                select(User).where(User.email == body.email, User.id != user_id)
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already in use",
                )
            user.email = body.email

        await db.commit()
        await db.refresh(user)
        return UserResponse.model_validate(user)
