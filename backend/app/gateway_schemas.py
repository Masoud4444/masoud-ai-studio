from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

class ProviderCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9 _.-]*$")
    base_url: str = Field(min_length=10, max_length=500)
    api_key: SecretStr | None = None
    models: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("models")
    @classmethod
    def validate_models(cls, values):
        clean = []
        for value in values:
            item = value.strip()
            if not item or len(item) > 160:
                raise ValueError("Each model identifier must contain 1-160 characters")
            if item not in clean:
                clean.append(item)
        return clean

class ProviderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    provider_type: str
    base_url: str
    models: list[str]
    is_enabled: bool
    created_at: datetime
    updated_at: datetime

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=100000)

class ChatCompletionRequest(BaseModel):
    model: str = Field(min_length=1, max_length=160)
    messages: list[ChatMessage] = Field(min_length=1, max_length=200)
    provider_id: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=32768)

    @field_validator("model")
    @classmethod
    def clean_model(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Model is required")
        return value

class ChatCompletionRead(BaseModel):
    id: str
    model: str
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    replayed: bool = False
