"""langfuse_client.py — Langfuse клиент для трекинга токенов GigaChat."""

import os
from langfuse import Langfuse
from src.config import settings

_client: Langfuse | None = None


def get_langfuse_client() -> Langfuse | None:
    """Возвращает Langfuse клиент если ключи заданы, иначе None."""
    global _client
    if _client:
        return _client
    if not settings.LANGFUSE_SECRET_KEY or not settings.LANGFUSE_PUBLIC_KEY:
        return None
    _client = Langfuse(
        secret_key=settings.LANGFUSE_SECRET_KEY,
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        host=settings.LANGFUSE_BASE_URL,
    )
    return _client


def log_generation(name: str, prompt: str, completion: str, prompt_tokens: int, completion_tokens: int):
    """Логирует один вызов модели с разбивкой токенов на input/output."""
    client = get_langfuse_client()
    if not client:
        return
    obs = client.start_observation(
        name=name,
        as_type="generation",
        input=prompt,
        output=completion,
        model="GigaChat",
        usage_details={
            "input":  prompt_tokens,
            "output": completion_tokens,
            "total":  prompt_tokens + completion_tokens,
        },
    )
    obs.end()
