from fastapi import APIRouter
from pydantic import BaseModel, EmailStr

from digest.database import async_session
from digest.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


@router.post("/register", status_code=201)
async def register(body: RegisterRequest):
    async with async_session() as db:
        svc = AuthService(db)
        return await svc.register(body.email, body.password)


@router.post("/login")
async def login(body: LoginRequest):
    async with async_session() as db:
        svc = AuthService(db)
        return await svc.login(body.email, body.password)


@router.post("/refresh")
async def refresh(body: RefreshRequest):
    async with async_session() as db:
        svc = AuthService(db)
        return await svc.refresh(body.refresh_token)


@router.post("/logout")
async def logout(body: LogoutRequest):
    async with async_session() as db:
        svc = AuthService(db)
        return await svc.logout(body.refresh_token)
