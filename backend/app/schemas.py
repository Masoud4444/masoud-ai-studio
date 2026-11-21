from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    slug: str | None = Field(default=None, min_length=1, max_length=170)
    description: str | None = Field(default=None, max_length=10000)
    project_type: str = Field(default="custom", min_length=1, max_length=50)
    settings: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

class ProjectUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=10000)
    project_type: str | None = Field(default=None, min_length=1, max_length=50)
    settings: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    slug: str
    name: str
    description: str | None
    project_type: str
    status: str
    settings: dict[str, Any]
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    version: int

class ProjectPage(BaseModel):
    items: list[ProjectRead]
    total: int
    limit: int
    offset: int
