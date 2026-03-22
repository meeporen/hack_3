"""
chat/routers.py — WebSocket chat (streaming LLM responses)

WS  /api/v1/chat/ws?token=<jwt>   — real-time чат с GigaChat
GET /api/v1/chat/history           — история чата текущего пользователя
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from jose import JWTError, jwt

from src.config import settings
from src.database import get_user_by_id

router = APIRouter()

# In-memory chat history (заменить на DB)
_chat_sessions: dict[int, list[dict]] = {}


@router.websocket("/ws")
async def chat_ws(
    websocket: WebSocket,
    token: str = Query(..., description="JWT токен для авторизации WS"),
):
    """
    WebSocket endpoint для стриминга ответов GigaChat.

    Клиент отправляет:  { "message": "Привет" }
    Сервер отвечает:    { "type": "chunk", "text": "..." }
                        { "type": "done",  "tokens": 42 }
    """
    # Validate token
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = int(payload["sub"])
        user = get_user_by_id(user_id)
        if not user:
            await websocket.close(code=4001)
            return
    except (JWTError, KeyError, ValueError):
        await websocket.close(code=4001)
        return

    await websocket.accept()
    if user_id not in _chat_sessions:
        _chat_sessions[user_id] = []

    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "").strip()
            if not message:
                continue

            # Save user message
            _chat_sessions[user_id].append({"role": "user", "content": message})

            # TODO: реальный вызов GigaChat streaming API
            # async for chunk in gigachat_stream(message, history):
            #     await websocket.send_json({"type": "chunk", "text": chunk})
            mock_reply = f"[GigaChat mock] Вы написали: «{message}». Ответ будет здесь после подключения GigaChat API."
            await websocket.send_json({"type": "chunk", "text": mock_reply})
            await websocket.send_json({"type": "done", "tokens": len(mock_reply.split())})

            _chat_sessions[user_id].append({"role": "assistant", "content": mock_reply})

    except WebSocketDisconnect:
        pass


@router.get("/history", summary="История чата")
async def chat_history(token: str = Query(...)):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Недействительный токен")
    return {"messages": _chat_sessions.get(user_id, [])}
