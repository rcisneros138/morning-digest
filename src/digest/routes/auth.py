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


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


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


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest):
    async with async_session() as db:
        svc = AuthService(db)
        return await svc.forgot_password(body.email)


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest):
    async with async_session() as db:
        svc = AuthService(db)
        return await svc.reset_password(body.token, body.new_password)
