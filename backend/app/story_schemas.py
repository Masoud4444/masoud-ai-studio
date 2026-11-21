from typing import Literal
from pydantic import BaseModel, Field, model_validator

StoryFormat = Literal["short_film", "feature_film", "series", "documentary", "animation", "novel", "short_story", "advertisement", "other"]
StoryStatus = Literal["development", "outlined", "drafting", "review", "locked", "archived"]

class StoryAct(BaseModel):
    act: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=2000)
    turning_point: str = Field(min_length=1, max_length=2000)

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
    central_question: str | None = Field(default=None, max_length=2000)
    human_value: str | None = Field(default=None, max_length=3000)
    act_structure: list[StoryAct] = Field(default_factory=list, max_length=8)

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
    central_question: str | None = Field(default=None, max_length=2000)
    human_value: str | None = Field(default=None, max_length=3000)
    act_structure: list[StoryAct] | None = Field(default=None, max_length=8)
    status: StoryStatus | None = None
    @model_validator(mode="after")
    def non_empty_update(self):
        if not (self.model_fields_set - {"expected_version", "change_note"}):
            raise ValueError("At least one story field must be updated")
        for field_name in self.model_fields_set - {"expected_version", "change_note", "genre", "target_audience", "premise", "logline", "synopsis", "creative_intent", "central_question", "human_value"}:
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


class StoryOutlineTaskCreate(BaseModel):
    model: str = Field(min_length=1, max_length=160)
    provider_id: str | None = Field(default=None, min_length=1, max_length=120)
    brief: str = Field(min_length=1, max_length=12000)
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=4000, ge=256, le=12000)


class StoryOutlineSceneProposal(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    slugline: str | None = Field(default=None, max_length=300)
    summary: str = Field(min_length=1, max_length=12000)
    dramatic_purpose: str | None = Field(default=None, max_length=1000)
    beats: list[str] = Field(default_factory=list, max_length=40)


class StoryOutlineActProposal(BaseModel):
    act: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=2000)
    turning_point: str = Field(min_length=1, max_length=2000)


class StoryOutlineProposal(BaseModel):
    logline: str = Field(min_length=1, max_length=1000)
    synopsis: str = Field(min_length=1, max_length=30000)
    central_question: str = Field(min_length=1, max_length=2000)
    human_value: str = Field(min_length=1, max_length=3000)
    act_structure: list[StoryOutlineActProposal] = Field(min_length=1, max_length=8)
    scenes: list[StoryOutlineSceneProposal] = Field(min_length=1, max_length=100)


class StoryOutlineApply(BaseModel):
    expected_version: int = Field(ge=1)


class StorySceneGenerationTaskCreate(BaseModel):
    model: str = Field(min_length=1, max_length=160)
    provider_id: str | None = Field(default=None, min_length=1, max_length=120)
    brief: str = Field(min_length=1, max_length=12000)
    scene_count: int = Field(default=6, ge=1, le=30)
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=5000, ge=512, le=12000)


class StoryGeneratedScene(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    slugline: str | None = Field(default=None, max_length=300)
    summary: str = Field(min_length=1, max_length=12000)
    dramatic_purpose: str = Field(min_length=1, max_length=1000)
    location_id: str | None = Field(default=None, min_length=36, max_length=36)
    time_of_day: str | None = Field(default=None, max_length=80)
    character_ids: list[str] = Field(default_factory=list, max_length=30)
    conflict: str = Field(min_length=1, max_length=2000)
    emotional_turn: str = Field(min_length=1, max_length=2000)
    beats: list[str] = Field(min_length=1, max_length=40)
    continuity_notes: str = Field(default="", max_length=2000)


class StorySceneGenerationProposal(BaseModel):
    scenes: list[StoryGeneratedScene] = Field(min_length=1, max_length=30)


class StorySceneGenerationApply(BaseModel):
    expected_version: int = Field(ge=1)
