"""v1/schemas.py — Conversion request / response schemas"""

from pydantic import BaseModel, Field
from typing import Any, Optional
from enum import Enum


class JobStatus(str, Enum):
    pending    = "pending"
    processing = "processing"
    done       = "done"
    error      = "error"


class ConvertRequest(BaseModel):
    """Тело запроса при конвертации (JSON-часть multipart формы)"""
    target_schema: dict[str, Any] = Field(
        ...,
        description="Целевая JSON-схема, в которую конвертируем данные",
        example={"dealId": "string", "amount": "number", "stage": "string"},
    )


class PipelineStep(BaseModel):
    name:    str
    status:  str           # wait | active | done | error
    message: str = ""
    tokens:  int = 0


class ConvertResponse(BaseModel):
    """Ответ после запуска конвертации (job создан)"""
    job_id:  str
    status:  JobStatus = JobStatus.pending
    message: str = "Задача принята в обработку"


class JobResult(BaseModel):
    """Результат завершённого job"""
    job_id:      str
    status:      JobStatus
    filename:    str
    file_format: str
    records:     int = 0
    tokens_used: int = 0
    retries:     int = 0
    ts_code:        Optional[str] = None
    console_output: Optional[str] = None
    json_output:    Optional[list[dict]] = None
    pipeline:    list[PipelineStep] = []
    error:       Optional[str] = None
    created_at:  str
    finished_at: Optional[str] = None
