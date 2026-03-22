"""
v1/routers.py — Conversion / Prediction endpoints

POST /api/v1/prediction/upload      — загрузить файл + схему → создать job
GET  /api/v1/prediction/{job_id}    — статус / результат job
GET  /api/v1/prediction             — список job-ов текущего пользователя
"""

import os
import uuid
import json
import base64
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException, BackgroundTasks

from src.config   import settings
from src.database import add_history
from src.api.deps import get_current_user
from src.api.v1.schemas import ConvertRequest, ConvertResponse, JobResult, JobStatus, PipelineStep

router = APIRouter()

# In-memory job store (заменить на Redis/DB в проде)
_jobs: dict[str, dict] = {}


# ── POST /upload ──────────────────────────────────────────────────────
@router.post("/upload", response_model=ConvertResponse, status_code=202, summary="Загрузить файл и запустить конвертацию")
async def upload_and_convert(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="CSV / XLS / XLSX / PDF / DOCX / PNG / JPG"),
    target_schema: str = Form(..., description="JSON-строка с целевой схемой"),
    user=Depends(get_current_user),
):
    # Validate schema JSON
    try:
        schema_dict = json.loads(target_schema)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="target_schema: невалидный JSON")

    # Save uploaded file
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    file_ext = os.path.splitext(file.filename or "file")[1]
    saved_name = f"{uuid.uuid4().hex}{file_ext}"
    saved_path = os.path.join(settings.UPLOAD_DIR, saved_name)

    contents = await file.read()
    with open(saved_path, "wb") as f:
        f.write(contents)

    # Create job
    job_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    _jobs[job_id] = {
        "job_id":      job_id,
        "user_id":     user["id"],
        "status":      JobStatus.pending,
        "filename":    file.filename,
        "file_path":   saved_path,
        "file_format": file_ext.lstrip(".").upper() or "FILE",
        "target_schema": schema_dict,
        "records":     0,
        "tokens_used": 0,
        "retries":     0,
        "ts_code":           None,
        "console_output":    None,
        "prompt_tokens":     0,
        "completion_tokens": 0,
        "json_output":       None,
        "pipeline":    [],
        "error":       None,
        "created_at":  now,
        "finished_at": None,
    }

    # Run pipeline in background
    background_tasks.add_task(_run_pipeline, job_id, user["id"])

    return ConvertResponse(job_id=job_id)


# ── GET /{job_id} ─────────────────────────────────────────────────────
@router.get("/{job_id}", response_model=JobResult, summary="Статус и результат job")
async def get_job(job_id: str, user=Depends(get_current_user)):
    job = _jobs.get(job_id)
    if not job or job["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Job не найден")
    return JobResult(**{k: v for k, v in job.items() if k != "user_id" and k != "file_path" and k != "target_schema"})


# ── GET / — list jobs ─────────────────────────────────────────────────
@router.get("", response_model=list[JobResult], summary="Список задач пользователя")
async def list_jobs(user=Depends(get_current_user)):
    user_jobs = [j for j in _jobs.values() if j["user_id"] == user["id"]]
    return [
        JobResult(**{k: v for k, v in j.items() if k not in ("user_id", "file_path", "target_schema")})
        for j in sorted(user_jobs, key=lambda x: x["created_at"], reverse=True)
    ]


# ── Background pipeline (реальный LangGraph агент) ────────────────────
async def _run_pipeline(job_id: str, user_id: int):
    from agent.graph import get_graph_agent

    job = _jobs[job_id]
    job["status"] = JobStatus.processing

    try:
        with open(job["file_path"], "rb") as f:
            raw_bytes = f.read()

        state = await get_graph_agent().ainvoke({
            "file_b64":    base64.b64encode(raw_bytes).decode(),
            "file_type":   job["file_format"].lower(),
            "target_json": job["target_schema"],
            "schema_hint": {},
            "ts_code":     "",
            "tokens_used": 0,
            "is_valid":    False,
            "errors":      [],
            "retry_count":     0,
            "result_json":     [],
            "console_output":  "",
            "prompt_tokens":   0,
            "completion_tokens": 0,
            "job_id":          job_id,
        })

        errors = state.get("errors") or []
        schema = job["target_schema"]
        first  = schema[0] if isinstance(schema, list) else schema
        allowed_keys = set(first.keys())
        raw_output = state.get("result_json") or []
        job["json_output"] = [
            {k: v for k, v in row.items() if k in allowed_keys}
            for row in raw_output
        ]
        job["records"]     = len(job["json_output"])
        job["tokens_used"] = state.get("tokens_used", 0)
        job["retries"]     = state.get("retry_count", 0)
        job["ts_code"]          = state.get("ts_code") or None
        job["console_output"]   = state.get("console_output") or None
        job["prompt_tokens"]    = state.get("prompt_tokens", 0)
        job["completion_tokens"] = state.get("completion_tokens", 0)
        job["status"]      = JobStatus.done if state.get("is_valid") else JobStatus.error
        job["error"]       = "; ".join(errors) if errors and not state.get("is_valid") else None
        job["finished_at"] = datetime.now(timezone.utc).isoformat()

    except Exception as exc:
        import traceback
        traceback.print_exc()
        job["status"]      = JobStatus.error
        job["error"]       = str(exc)
        job["finished_at"] = datetime.now(timezone.utc).isoformat()

    finally:
        try:
            os.remove(job["file_path"])
        except OSError:
            pass

    if job["status"] == JobStatus.done:
        add_history({
            "user_id":     user_id,
            "job_id":      job_id,
            "status":      "valid",
            "filename":    job["filename"],
            "file_format": job["file_format"],
            "tokens":      job["tokens_used"],
            "retries":     job["retries"],
            "records":     job["records"],
            "time":        job["finished_at"],
        })
