from typing import Any
from pydantic import BaseModel, Field


class ProductionRunCreate(BaseModel):
    workflow_key: str = Field(min_length=1, max_length=120)
    project_id: str | None = Field(default=None, min_length=36, max_length=36)
    inputs: dict[str, Any] = Field(default_factory=dict)
