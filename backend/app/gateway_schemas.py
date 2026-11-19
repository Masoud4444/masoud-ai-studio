from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from urllib.parse import urlsplit

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
