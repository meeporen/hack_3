"""
database.py — Mock JSON file database
Заменить на реальный ORM (SQLAlchemy / Tortoise) при подключении БД.
"""

import json
import os
from typing import Any

from src.config import settings


def _read(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def _write(path: str, data: list[dict]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Users ─────────────────────────────────────────────────────────────
def get_all_users() -> list[dict]:
    return _read(settings.USERS_FILE)


def get_user_by_email(email: str) -> dict | None:
    return next(
        (u for u in get_all_users() if u["email"].lower() == email.lower()),
        None,
    )


def get_user_by_id(user_id: int) -> dict | None:
    return next((u for u in get_all_users() if u["id"] == user_id), None)


def create_user(user_data: dict) -> dict:
    users = get_all_users()
    user_data["id"] = (max((u["id"] for u in users), default=0) + 1)
    users.append(user_data)
    _write(settings.USERS_FILE, users)
    return user_data


def update_user(user_id: int, fields: dict) -> dict | None:
    users = get_all_users()
    for u in users:
        if u["id"] == user_id:
            u.update(fields)
            _write(settings.USERS_FILE, users)
            return u
    return None


# ── History ───────────────────────────────────────────────────────────
def get_history(user_id: int) -> list[dict]:
    return [h for h in _read(settings.HISTORY_FILE) if h.get("user_id") == user_id]


def add_history(item: dict) -> dict:
    history = _read(settings.HISTORY_FILE)
    item["id"] = max((h["id"] for h in history), default=0) + 1
    history.append(item)
    _write(settings.HISTORY_FILE, history)
    return item


def delete_history_item(item_id: int, user_id: int) -> bool:
    history = _read(settings.HISTORY_FILE)
    new_history = [h for h in history if not (h["id"] == item_id and h["user_id"] == user_id)]
    if len(new_history) == len(history):
        return False
    _write(settings.HISTORY_FILE, new_history)
    return True
