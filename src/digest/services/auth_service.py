from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from digest.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)
from digest.models import RefreshToken, User


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, email: str, password: str) -> dict:
        existing = await self.db.scalar(select(User).where(User.email == email))
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
            )

        user = User(email=email, password_hash=hash_password(password))
        self.db.add(user)
        await self.db.flush()

        access_token = create_access_token(user.id)
        refresh_token, expires_at = create_refresh_token(user.id)

        rt = RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh_token),
            expires_at=expires_at,
        )
        self.db.add(rt)
        await self.db.commit()

        return {
            "user_id": str(user.id),
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

    async def login(self, email: str, password: str) -> dict:
        user = await self.db.scalar(select(User).where(User.email == email))
        if not user or not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )

        access_token = create_access_token(user.id)
        refresh_token, expires_at = create_refresh_token(user.id)

        rt = RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh_token),
            expires_at=expires_at,
        )
        self.db.add(rt)
        await self.db.commit()

        return {
            "user_id": str(user.id),
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

    async def refresh(self, refresh_token_str: str) -> dict:
        user_id = decode_token(refresh_token_str, expected_type="refresh")

        token_h = hash_token(refresh_token_str)
        stored = await self.db.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_h,
                RefreshToken.revoked_at.is_(None),
            )
        )
        if not stored:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
            )

        # Rotate: revoke old, issue new
        stored.revoked_at = datetime.now(UTC).replace(tzinfo=None)

        new_access = create_access_token(user_id)
        new_refresh, expires_at = create_refresh_token(user_id)

        rt = RefreshToken(
            user_id=user_id,
            token_hash=hash_token(new_refresh),
            expires_at=expires_at,
        )
        self.db.add(rt)
        await self.db.commit()

        return {
            "access_token": new_access,
            "refresh_token": new_refresh,
        }

    async def logout(self, refresh_token_str: str) -> dict:
        token_h = hash_token(refresh_token_str)
        stored = await self.db.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_h,
                RefreshToken.revoked_at.is_(None),
            )
        )
        if stored:
            stored.revoked_at = datetime.now(UTC).replace(tzinfo=None)
            await self.db.commit()

        return {"status": "ok"}
