import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_current_user_optional
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    create_signed_guest_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models import User, UserRole
from app.schemas import LoginRequest, SignupRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    response.set_cookie(
        key="access_token",
        value=access,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=settings.access_token_expire_minutes * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=settings.refresh_token_expire_days * 86400,
    )


@router.post("/signup", response_model=UserResponse)
async def signup(
    data: SignupRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Invalid email or password")

    user = User(
        name=data.name,
        email=data.email,
        phone=data.phone,
        password_hash=hash_password(data.password),
        role=UserRole.customer,
    )
    db.add(user)
    await db.flush()

    access = create_access_token(str(user.id), {"role": user.role.value})
    refresh = create_refresh_token(str(user.id))
    set_auth_cookies(response, access, refresh)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user or not user.password_hash or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access = create_access_token(str(user.id), {"role": user.role.value})
    refresh = create_refresh_token(str(user.id))
    set_auth_cookies(response, access, refresh)
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", secure=True, samesite="none")
    response.delete_cookie("refresh_token", secure=True, samesite="none")
    return {"ok": True}


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return user


@router.get("/google/login")
async def google_login():
    if not settings.google_client_id:
        raise HTTPException(status_code=501, detail="Google OAuth not configured")
    return {
        "url": f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={settings.google_client_id}&"
        f"redirect_uri={settings.frontend_url}/auth/google/callback&"
        "response_type=code&scope=openid email profile"
    }


@router.post("/google/callback", response_model=UserResponse)
async def google_callback(
    response: Response,
    code: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    if not settings.google_client_id:
        raise HTTPException(status_code=501, detail="Google OAuth not configured")

    import httpx

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": f"{settings.frontend_url}/auth/google/callback",
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Google authentication failed")
        tokens = token_resp.json()

        userinfo = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        profile = userinfo.json()

    google_id = profile["id"]
    email = profile["email"]
    name = profile.get("name", email.split("@")[0])

    result = await db.execute(select(User).where((User.google_id == google_id) | (User.email == email)))
    user = result.scalar_one_or_none()
    if not user:
        user = User(name=name, email=email, google_id=google_id, role=UserRole.customer)
        db.add(user)
        await db.flush()
    elif not user.google_id:
        user.google_id = google_id

    access = create_access_token(str(user.id), {"role": user.role.value})
    refresh = create_refresh_token(str(user.id))
    set_auth_cookies(response, access, refresh)
    return user
