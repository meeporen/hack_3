"""auth/schemas.py — Request / Response модели для авторизации"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class LoginRequest(BaseModel):
    email: EmailStr = Field(..., example="ivan@sber.ru")
    password: str   = Field(..., min_length=1, example="password")


class RegisterRequest(BaseModel):
    name:     str      = Field(..., min_length=2, max_length=100, example="Иван Иванов")
    email:    EmailStr = Field(..., example="ivan@sber.ru")
    password: str      = Field(..., min_length=6, example="secret123")


class UserOut(BaseModel):
    id:        int
    name:      str
    email:     str
    role:      str
    photo:     Optional[str] = None   # base64 или URL
    createdAt: str


class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    expires_in:   int          # секунды
    user:         UserOut


class PhotoUpdateRequest(BaseModel):
    photo: str = Field(..., description="base64-encoded image")


class MessageResponse(BaseModel):
    message: str
