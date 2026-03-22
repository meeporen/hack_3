"""
auth/routers.py — Authentication endpoints

POST /api/v1/auth/login     — вход (email + password → JWT)
POST /api/v1/auth/register  — регистрация
POST /api/v1/auth/logout    — выход (клиентский — токен инвалидируется на фронте)
GET  /api/v1/auth/me        — текущий пользователь
PATCH /api/v1/auth/photo    — обновить фото профиля
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status, Depends
from jose import jwt
from passlib.context import CryptContext

from src.config   import settings
from src.database import get_user_by_email, create_user, update_user
from src.api.deps import get_current_user

from src.api.auth.schemas import (
    LoginRequest, RegisterRequest, TokenResponse,
    UserOut, PhotoUpdateRequest, MessageResponse,
)

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _verify_password(plain: str, hashed: str) -> bool:
    # Поддержка нехешированных паролей (mock данные)
    if not hashed.startswith("$2"):
        return plain == hashed
    return pwd_context.verify(plain, hashed)


def _create_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": str(user_id), "exp": expire},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )


def _user_out(user: dict) -> UserOut:
    return UserOut(
        id=user["id"],
        name=user["name"],
        email=user["email"],
        role=user.get("role", "user"),
        photo=user.get("photo"),
        createdAt=user.get("createdAt", ""),
    )


# ── POST /login ───────────────────────────────────────────────────────
@router.post("/login", response_model=TokenResponse, summary="Вход в систему")
async def login(body: LoginRequest):
    user = get_user_by_email(body.email)
    if not user or not _verify_password(body.password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
        )
    token = _create_token(user["id"])
    return TokenResponse(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=_user_out(user),
    )


# ── POST /register ────────────────────────────────────────────────────
@router.post("/register", response_model=TokenResponse, status_code=201, summary="Регистрация")
async def register(body: RegisterRequest):
    if get_user_by_email(body.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Пользователь с таким email уже существует",
        )
    new_user = create_user({
        "name": body.name,
        "email": body.email,
        "password": _hash_password(body.password),
        "role": "user",
        "photo": None,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    })
    token = _create_token(new_user["id"])
    return TokenResponse(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=_user_out(new_user),
    )


# ── POST /logout ──────────────────────────────────────────────────────
@router.post("/logout", response_model=MessageResponse, summary="Выход")
async def logout(_user=Depends(get_current_user)):
    # При stateless JWT — токен инвалидируется на клиенте.
    # Для blacklist: добавить токен в Redis/DB.
    return MessageResponse(message="Выход выполнен")


# ── GET /me ───────────────────────────────────────────────────────────
@router.get("/me", response_model=UserOut, summary="Текущий пользователь")
async def me(user=Depends(get_current_user)):
    return _user_out(user)


# ── PATCH /photo ──────────────────────────────────────────────────────
@router.patch("/photo", response_model=UserOut, summary="Обновить фото профиля")
async def update_photo(body: PhotoUpdateRequest, user=Depends(get_current_user)):
    updated = update_user(user["id"], {"photo": body.photo})
    if not updated:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return _user_out(updated)
