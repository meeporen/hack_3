"""langfuse_client.py — Langfuse v3 клиент."""

import os
from src.config import settings


def get_langfuse_client():
    if not settings.LANGFUSE_SECRET_KEY or not settings.LANGFUSE_PUBLIC_KEY:
        return None
    os.environ["LANGFUSE_SECRET_KEY"] = settings.LANGFUSE_SECRET_KEY
    os.environ["LANGFUSE_PUBLIC_KEY"]  = settings.LANGFUSE_PUBLIC_KEY
    os.environ["LANGFUSE_HOST"]        = settings.LANGFUSE_HOST
    try:
        from langfuse import get_client
        return get_client()
    except Exception as e:
        print(f"[langfuse] Ошибка инициализации: {e}")
        return None
