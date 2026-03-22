"""
history/routers.py

GET    /api/v1/history        — история конвертаций пользователя
DELETE /api/v1/history/{id}   — удалить запись из истории
DELETE /api/v1/history        — очистить всю историю
"""

from fastapi import APIRouter, Depends, HTTPException

from src.database import get_history, delete_history_item
from src.api.deps import get_current_user
from src.api.history.schemas import HistoryItem, HistoryListResponse

router = APIRouter()


@router.get("", response_model=HistoryListResponse, summary="История конвертаций")
async def list_history(user=Depends(get_current_user)):
    items = get_history(user["id"])
    return HistoryListResponse(
        items=[HistoryItem(**item) for item in items],
        total=len(items),
    )


@router.delete("/{item_id}", summary="Удалить запись истории")
async def delete_item(item_id: int, user=Depends(get_current_user)):
    deleted = delete_history_item(item_id, user["id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return {"message": "Запись удалена"}


@router.delete("", summary="Очистить всю историю")
async def clear_history(user=Depends(get_current_user)):
    items = get_history(user["id"])
    for item in items:
        delete_history_item(item["id"], user["id"])
    return {"message": f"Удалено {len(items)} записей"}
