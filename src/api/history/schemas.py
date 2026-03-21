"""history/schemas.py"""

from pydantic import BaseModel
from typing import Optional


class HistoryItem(BaseModel):
    id:          int
    job_id:      str
    status:      str          # valid | error | retry
    filename:    str
    file_format: str
    tokens:      int
    retries:     int
    records:     int
    time:        str          # ISO timestamp


class HistoryListResponse(BaseModel):
    items: list[HistoryItem]
    total: int
