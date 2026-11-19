from typing import Literal
from pydantic import BaseModel, Field, model_validator

StoryFormat = Literal["short_film", "feature_film", "series", "documentary", "animation", "novel", "short_story", "advertisement", "other"]
StoryStatus = Literal["development", "outlined", "drafting", "review", "locked", "archived"]

class StoryCreate(BaseModel):
    project_id: str = Field(min_length=36, max_length=36)
    title: str = Field(min_length=1, max_length=240)
    format: StoryFormat = "short_film"
    genre: str | None = Field(default=None, max_length=120)
    target_audience: str | None = Field(default=None, max_length=500)
    premise: str | None = Field(default=None, max_length=12000)
    logline: str | None = Field(default=None, max_length=1000)
    synopsis: str | None = Field(default=None, max_length=30000)
    creative_intent: str | None = Field(default=None, max_length=12000)

class StoryUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    change_note: str | None = Field(default=None, max_length=500)
    title: str | None = Field(default=None, min_length=1, max_length=240)
    format: StoryFormat | None = None
    genre: str | None = Field(default=None, max_length=120)
    target_audience: str | None = Field(default=None, max_length=500)
    premise: str | None = Field(default=None, max_length=12000)
    logline: str | None = Field(default=None, max_length=1000)
    synopsis: str | None = Field(default=None, max_length=30000)
    creative_intent: str | None = Field(default=None, max_length=12000)
    status: StoryStatus | None = None
    @model_validator(mode="after")
    def non_empty_update(self):
        if not (self.model_fields_set - {"expected_version", "change_note"}):
            raise ValueError("At least one story field must be updated")
        for field_name in self.model_fields_set - {"expected_version", "change_note", "genre", "target_audience", "premise", "logline", "synopsis", "creative_intent"}:
            if getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self

class StorySceneCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    slugline: str | None = Field(default=None, max_length=300)
    summary: str | None = Field(default=None, max_length=12000)
    dramatic_purpose: str | None = Field(default=None, max_length=1000)
    location: str | None = Field(default=None, max_length=240)
    time_of_day: str | None = Field(default=None, max_length=80)
    beats: list[str] = Field(default_factory=list, max_length=40)
    body: str | None = Field(default=None, max_length=50000)

class StorySceneUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    change_note: str | None = Field(default=None, max_length=500)
    title: str | None = Field(default=None, min_length=1, max_length=240)
    slugline: str | None = Field(default=None, max_length=300)
    summary: str | None = Field(default=None, max_length=12000)
    dramatic_purpose: str | None = Field(default=None, max_length=1000)
    location: str | None = Field(default=None, max_length=240)
    time_of_day: str | None = Field(default=None, max_length=80)
    beats: list[str] | None = Field(default=None, max_length=40)
    body: str | None = Field(default=None, max_length=50000)
    @model_validator(mode="after")
    def non_empty_update(self):
        if not (self.model_fields_set - {"expected_version", "change_note"}):
            raise ValueError("At least one scene field must be updated")
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title cannot be null")
        return self


class StorySceneReorder(BaseModel):
    expected_story_version: int = Field(ge=1)
    scene_ids: list[str] = Field(min_length=1, max_length=500)
