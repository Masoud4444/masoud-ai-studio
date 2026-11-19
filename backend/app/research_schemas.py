from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, Field, field_validator, model_validator

SourceType = Literal["url", "document", "note", "transcript", "dataset", "other"]
EvidenceType = Literal["quote", "data", "observation", "transcript", "other"]
ClaimType = Literal["factual", "interpretive", "forecast", "creative", "other"]
ClaimStatus = Literal["draft", "reviewed", "accepted", "rejected"]
EvidenceRelation = Literal["supports", "contradicts", "contextualizes"]

class ResearchSourceCreate(BaseModel):
    source_type: SourceType
    title: str = Field(min_length=1, max_length=300)
    canonical_url: str | None = Field(default=None, max_length=2048)
    author: str | None = Field(default=None, max_length=300)
    publisher: str | None = Field(default=None, max_length=300)
    published_at: datetime | None = None
    language: str | None = Field(default=None, max_length=24)
    summary: str | None = Field(default=None, max_length=10000)
    asset_id: str | None = Field(default=None, min_length=36, max_length=36)
    project_id: str | None = Field(default=None, min_length=36, max_length=36)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("canonical_url")
    @classmethod
    def validate_canonical_url(cls, value):
        if value is None:
            return value
        parsed = urlsplit(value.strip())
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Source URL must use http or https")
        if parsed.username or parsed.password:
            raise ValueError("Source URL must not contain embedded credentials")
        try:
            parsed.port
        except ValueError:
            raise ValueError("Source URL contains an invalid port")
        return value.strip()

    @model_validator(mode="after")
    def url_source_requires_url(self):
        if self.source_type == "url" and not self.canonical_url:
            raise ValueError("URL sources require canonical_url")
        return self

class ResearchEvidenceCreate(BaseModel):
    evidence_type: EvidenceType = "quote"
    excerpt: str = Field(min_length=1, max_length=20000)
    locator: str | None = Field(default=None, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)

class ResearchClaimCreate(BaseModel):
    project_id: str = Field(min_length=36, max_length=36)
    statement: str = Field(min_length=1, max_length=5000)
    claim_type: ClaimType = "factual"
    rationale: str | None = Field(default=None, max_length=5000)

class ResearchClaimUpdate(BaseModel):
    statement: str | None = Field(default=None, min_length=1, max_length=5000)
    claim_type: ClaimType | None = None
    rationale: str | None = Field(default=None, max_length=5000)
    status: ClaimStatus | None = None

    @model_validator(mode="after")
    def reject_null_required_fields(self):
        for field_name in self.model_fields_set - {"rationale"}:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self

class ResearchClaimEvidenceCreate(BaseModel):
    relationship: EvidenceRelation
    note: str | None = Field(default=None, max_length=2000)
