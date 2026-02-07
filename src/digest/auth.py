from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from digest.config import settings

bearer_scheme = HTTPBearer()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def create_access_token(user_id: uuid.UUID) -> str:
    expires = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "exp": expires,
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: uuid.UUID) -> tuple[str, datetime]:
    expires = datetime.now(UTC) + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload = {
        "sub": str(user_id),
        "exp": expires,
        "type": "refresh",
        "jti": uuid.uuid4().hex,
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    # Return naive UTC datetime for DB storage (matching project convention)
    return token, expires.replace(tzinfo=None)


def decode_token(token: str, expected_type: str = "access") -> uuid.UUID:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if payload.get("type") != expected_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    return uuid.UUID(payload["sub"])


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> uuid.UUID:
    return decode_token(credentials.credentials, expected_type="access")
