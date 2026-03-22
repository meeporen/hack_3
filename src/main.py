"""
main.py — FastAPI application entry point

Запуск:
    uvicorn src.main:app --reload --port 8000

Swagger UI: http://localhost:8000/docs
Frontend:   http://localhost:8000/
"""

# Загружаем .env в os.environ ДО всех других импортов,
# чтобы langchain_gigachat мог читать GIGACHAT_CREDENTIALS и пр.
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from src.config   import settings
from src.database import get_user_by_email, create_user
from src.api.auth.routers    import router as auth_router, _hash_password
from src.api.v1.routers      import router as v1_router
from src.api.history.routers import router as history_router
from src.api.chat.routers    import router as chat_router

app = FastAPI(
    title="Sberbank Converter Agent",
    description="API для конвертации файлов в JSON через LLM (GigaChat)",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # TODO: в prod заменить на конкретный домен
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────
app.include_router(auth_router,    prefix="/api/v1/auth",       tags=["Auth"])
app.include_router(v1_router,      prefix="/api/v1/prediction", tags=["Conversion"])
app.include_router(history_router, prefix="/api/v1/history",    tags=["History"])
app.include_router(chat_router,    prefix="/api/v1/chat",       tags=["Chat"])

# ── Seed admin user from .env ─────────────────────────────────────
@app.on_event("startup")
async def seed_admin():
    """Создаёт admin-пользователя из .env, если его ещё нет."""
    from datetime import datetime, timezone
    admin_email = f"{settings.LOGIN}@localhost"
    if not get_user_by_email(admin_email):
        create_user({
            "name":      settings.LOGIN,
            "email":     admin_email,
            "password":  _hash_password(settings.PASSWORD),
            "role":      "admin",
            "photo":     None,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        })


# ── Static files (Frontend) ───────────────────────────────────────────
app.mount("/assets", StaticFiles(directory="frontend/assets"), name="assets")

@app.get("/", include_in_schema=False)
async def serve_index():
    return FileResponse("frontend/index.html")

@app.get("/{page}.html", include_in_schema=False)
async def serve_page(page: str):
    return FileResponse(f"frontend/{page}.html")

# ── Health check ──────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "service": "converter-agent"}
