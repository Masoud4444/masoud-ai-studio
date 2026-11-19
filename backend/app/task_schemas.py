from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    task_type: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)
    project_id: str | None = Field(default=None, min_length=36, max_length=36)
    priority: int = Field(default=100, ge=0, le=10000)
    depends_on: list[str] = Field(default_factory=list, max_length=100)
    max_attempts: int = Field(default=3, ge=1, le=20)


class TaskRead(BaseModel):
    id: str
    project_id: str | None
    task_type: str
    status: str
    priority: int
    attempt_count: int
    max_attempts: int
    available_at: datetime
    lease_expires_at: datetime | None
    locked_by: str | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    payload: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
