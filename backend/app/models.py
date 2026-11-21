from datetime import date, datetime, timezone
from uuid import uuid4
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Boolean, Numeric, Date
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    slug: Mapped[str] = mapped_column(String(170), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_type: Mapped[str] = mapped_column(String(50), default="custom", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True, nullable=False)
    settings_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(160), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

class ProjectAsset(Base):
    __tablename__ = "project_assets"
    __table_args__ = (UniqueConstraint("project_id", "asset_id", name="uq_project_asset"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), index=True, nullable=False)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"), index=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

class TaskArtifact(Base):
    __tablename__ = "task_artifacts"
    __table_args__ = (UniqueConstraint("task_id", "asset_id", name="uq_task_artifact"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id: Mapped[str] = mapped_column(ForeignKey("studio_tasks.id", ondelete="RESTRICT"), index=True, nullable=False)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"), index=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class AIProvider(Base):
    __tablename__ = "ai_providers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    provider_type: Mapped[str] = mapped_column(String(40), default="openai_compatible", nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    models_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

class AIRequest(Base):
    __tablename__ = "ai_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    idempotency_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_id: Mapped[str] = mapped_column(ForeignKey("ai_providers.id", ondelete="RESTRICT"), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True, nullable=False)
    encrypted_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_key_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    lease_expires_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

class AIUsage(Base):
    __tablename__ = "ai_usage"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    request_id: Mapped[str] = mapped_column(ForeignKey("ai_requests.id", ondelete="RESTRICT"), unique=True, nullable=False)
    provider_id: Mapped[str] = mapped_column(ForeignKey("ai_providers.id", ondelete="RESTRICT"), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    pricing_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

class AIModelCapability(Base):
    __tablename__ = "ai_model_capabilities"
    __table_args__ = (UniqueConstraint("provider_id", "model_id", name="uq_provider_model"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    provider_id: Mapped[str] = mapped_column(ForeignKey("ai_providers.id", ondelete="RESTRICT"), index=True, nullable=False)
    model_id: Mapped[str] = mapped_column(String(160), nullable=False)
    capabilities_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    verification_status: Mapped[str] = mapped_column(String(20), default="declared", nullable=False)
    context_window: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    supports_streaming: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_tools: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_vision: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

class AIModelPricing(Base):
    __tablename__ = "ai_model_pricing"
    __table_args__ = (UniqueConstraint("provider_id", "model_id", name="uq_provider_model_pricing"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    provider_id: Mapped[str] = mapped_column(ForeignKey("ai_providers.id", ondelete="RESTRICT"), index=True, nullable=False)
    model_id: Mapped[str] = mapped_column(String(160), nullable=False)
    input_usd_per_million: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    output_usd_per_million: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    source_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

class AIModelPricingHistory(Base):
    __tablename__ = "ai_model_pricing_history"
    __table_args__ = (UniqueConstraint("provider_id", "model_id", "version", name="uq_provider_model_price_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    provider_id: Mapped[str] = mapped_column(ForeignKey("ai_providers.id", ondelete="RESTRICT"), index=True, nullable=False)
    model_id: Mapped[str] = mapped_column(String(160), nullable=False)
    input_usd_per_million: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    output_usd_per_million: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class StudioTask(Base):
    __tablename__ = "studio_tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), index=True, nullable=True)
    task_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, index=True, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True, nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_from_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TaskDependency(Base):
    __tablename__ = "task_dependencies"
    __table_args__ = (UniqueConstraint("task_id", "depends_on_task_id", name="uq_task_dependency"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id: Mapped[str] = mapped_column(ForeignKey("studio_tasks.id", ondelete="RESTRICT"), index=True, nullable=False)
    depends_on_task_id: Mapped[str] = mapped_column(ForeignKey("studio_tasks.id", ondelete="RESTRICT"), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class TaskEvent(Base):
    __tablename__ = "task_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    task_id: Mapped[str] = mapped_column(ForeignKey("studio_tasks.id", ondelete="RESTRICT"), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    detail_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ProductionRun(Base):
    __tablename__ = "production_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), index=True, nullable=True)
    workflow_key: Mapped[str] = mapped_column(String(120), nullable=False)
    workflow_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True, nullable=False)
    input_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    idempotency_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class ProductionStep(Base):
    __tablename__ = "production_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "step_key", name="uq_production_run_step"),
        UniqueConstraint("task_id", name="uq_production_step_task"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("production_runs.id", ondelete="RESTRICT"), index=True, nullable=False)
    step_key: Mapped[str] = mapped_column(String(100), nullable=False)
    task_id: Mapped[str] = mapped_column(ForeignKey("studio_tasks.id", ondelete="RESTRICT"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class StudioAgent(Base):
    __tablename__ = "studio_agents"
    __table_args__ = (UniqueConstraint("slug", name="uq_studio_agent_slug"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True, nullable=False)
    provider_id: Mapped[str | None] = mapped_column(ForeignKey("ai_providers.id", ondelete="RESTRICT"), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    temperature: Mapped[float] = mapped_column(Numeric(4, 3), default=0.2, nullable=False)
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=4096, nullable=False)
    max_cost_per_run_usd: Mapped[float] = mapped_column(Numeric(18, 8), default=0.25, nullable=False)
    monthly_budget_usd: Mapped[float] = mapped_column(Numeric(18, 8), default=10, nullable=False)
    permissions_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class AgentToolGrant(Base):
    __tablename__ = "agent_tool_grants"
    __table_args__ = (UniqueConstraint("agent_id", "tool_name", name="uq_agent_tool_grant"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    agent_id: Mapped[str] = mapped_column(ForeignKey("studio_agents.id", ondelete="RESTRICT"), index=True, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    permission: Mapped[str] = mapped_column(String(20), nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class AgentEvent(Base):
    __tablename__ = "agent_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    agent_id: Mapped[str] = mapped_column(ForeignKey("studio_agents.id", ondelete="RESTRICT"), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    detail_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)



class AgentBudgetReservation(Base):
    __tablename__ = "agent_budget_reservations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    agent_id: Mapped[str] = mapped_column(ForeignKey("studio_agents.id", ondelete="RESTRICT"), index=True, nullable=False)
    idempotency_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    reserved_usd: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    actual_cost_usd: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="reserved", index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)



class ResearchSource(Base):
    __tablename__ = "research_sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_type: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    author: Mapped[str | None] = mapped_column(String(300), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(300), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    language: Mapped[str | None] = mapped_column(String(24), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("assets.id", ondelete="RESTRICT"), index=True, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class ProjectResearchSource(Base):
    __tablename__ = "project_research_sources"
    __table_args__ = (UniqueConstraint("project_id", "source_id", name="uq_project_research_source"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), index=True, nullable=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("research_sources.id", ondelete="RESTRICT"), index=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ResearchEvidence(Base):
    __tablename__ = "research_evidence"
    __table_args__ = (UniqueConstraint("source_id", "content_hash", name="uq_research_evidence_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_id: Mapped[str] = mapped_column(ForeignKey("research_sources.id", ondelete="RESTRICT"), index=True, nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(20), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    locator: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ResearchClaim(Base):
    __tablename__ = "research_claims"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), index=True, nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class ResearchClaimEvidence(Base):
    __tablename__ = "research_claim_evidence"
    __table_args__ = (UniqueConstraint("claim_id", "evidence_id", name="uq_research_claim_evidence"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    claim_id: Mapped[str] = mapped_column(ForeignKey("research_claims.id", ondelete="RESTRICT"), index=True, nullable=False)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("research_evidence.id", ondelete="RESTRICT"), index=True, nullable=False)
    relationship: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ResearchEvent(Base):
    __tablename__ = "research_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    entity_type: Mapped[str] = mapped_column(String(24), index=True, nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    detail_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True, nullable=False)


class Story(Base):
    __tablename__ = "stories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    format: Mapped[str] = mapped_column(String(40), default="short_film", nullable=False)
    genre: Mapped[str | None] = mapped_column(String(120), nullable=True)
    target_audience: Mapped[str | None] = mapped_column(String(500), nullable=True)
    premise: Mapped[str | None] = mapped_column(Text, nullable=True)
    logline: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    synopsis: Mapped[str | None] = mapped_column(Text, nullable=True)
    creative_intent: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="development", index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class StoryRevision(Base):
    __tablename__ = "story_revisions"
    __table_args__ = (UniqueConstraint("story_id", "version", name="uq_story_revision_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id", ondelete="RESTRICT"), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    change_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class StoryScene(Base):
    __tablename__ = "story_scenes"
    __table_args__ = (UniqueConstraint("story_id", "position", name="uq_story_scene_position"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id", ondelete="RESTRICT"), index=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    slugline: Mapped[str | None] = mapped_column(String(300), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    dramatic_purpose: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    location: Mapped[str | None] = mapped_column(String(240), nullable=True)
    time_of_day: Mapped[str | None] = mapped_column(String(80), nullable=True)
    beats_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
