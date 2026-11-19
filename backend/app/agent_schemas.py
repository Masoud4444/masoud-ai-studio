from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentCreate(BaseModel):
    slug: str = Field(min_length=2, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    purpose: str = Field(min_length=5, max_length=500)
    system_prompt: str = Field(default="", max_length=50000)
    provider_id: str | None = Field(default=None, min_length=36, max_length=36)
    model_id: str | None = Field(default=None, min_length=1, max_length=160)
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_output_tokens: int = Field(default=4096, ge=1, le=32768)
    max_cost_per_run_usd: float = Field(default=0.25, gt=0, le=1000)
    monthly_budget_usd: float = Field(default=10, gt=0, le=100000)
    permissions: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("permissions")
    @classmethod
    def clean_permissions(cls, values):
        allowed = {"research.read", "project.read", "asset.read", "content.create",
                   "content.edit", "asset.create", "task.create", "ai.generate"}
        result = []
        for value in values:
            item = value.strip()
            if item not in allowed:
                raise ValueError("Unsupported agent permission")
            if item not in result:
                result.append(item)
        return result


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    purpose: str | None = Field(default=None, min_length=5, max_length=500)
    system_prompt: str | None = Field(default=None, max_length=50000)
    provider_id: str | None = Field(default=None, min_length=36, max_length=36)
    model_id: str | None = Field(default=None, min_length=1, max_length=160)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_output_tokens: int | None = Field(default=None, ge=1, le=32768)
    max_cost_per_run_usd: float | None = Field(default=None, gt=0, le=1000)
    monthly_budget_usd: float | None = Field(default=None, gt=0, le=100000)
    permissions: list[str] | None = Field(default=None, max_length=50)


class AgentToolGrantInput(BaseModel):
    tool_name: str = Field(min_length=2, max_length=120, pattern=r"^[a-z][a-z0-9_.-]*$")
    permission: Literal["read", "write", "execute"]
    approval_required: bool = True
    is_enabled: bool = True

    @field_validator("approval_required")
    @classmethod
    def require_approval_for_mutations(cls, value, info):
        if info.data.get("permission") in {"write", "execute"} and not value:
            raise ValueError("Write and execute tools must require human approval")
        return value


class AgentToolsUpdate(BaseModel):
    grants: list[AgentToolGrantInput] = Field(default_factory=list, max_length=100)


class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    slug: str
    name: str
    description: str | None
    purpose: str
    system_prompt: str
    status: str
    provider_id: str | None
    model_id: str | None
    temperature: float
    max_output_tokens: int
    max_cost_per_run_usd: float
    monthly_budget_usd: float
    permissions: list[str]
    version: int
    tools: list[dict]
    created_at: datetime
    updated_at: datetime
