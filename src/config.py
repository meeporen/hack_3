"""config.py — Application settings (Pydantic BaseSettings)"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # JWT
    SECRET_KEY: str = "change-me-in-production-32-chars!!"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24h

    # GigaChat / LLM
    GIGACHAT_API_KEY: str = ""
    GIGACHAT_MODEL: str = "GigaChat-2-Max"

    # Storage (mock JSON paths — при реальном DB заменить)
    USERS_FILE: str = "data/users.json"
    HISTORY_FILE: str = "data/history.json"
    UPLOAD_DIR: str = "uploads"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
