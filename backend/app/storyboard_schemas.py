from typing import Literal
from pydantic import BaseModel, Field, model_validator

ShotSize = Literal["ecu", "cu", "mcu", "ms", "mws", "ws", "ews", "ots", "pov", "aerial", "two_shot"]
CameraAngle = Literal["eye_level", "high", "low", "birds_eye", "worms_eye", "dutch", "overhead"]
CameraMovement = Literal["static", "pan", "tilt", "dolly_in", "dolly_out", "truck", "crane", "handheld", "steadicam", "zoom", "tracking", "orbit"]

class StoryboardShotCreate(BaseModel):
    scene_id: str = Field(min_length=36, max_length=36)
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=12000)
    shot_size: ShotSize = "ms"
    camera_angle: CameraAngle = "eye_level"
    camera_movement: CameraMovement = "static"
    lens: str | None = Field(default=None, max_length=120)
    composition: str | None = Field(default=None, max_length=2000)
    action: str | None = Field(default=None, max_length=4000)
    dialogue: str | None = Field(default=None, max_length=4000)
    duration_seconds: float = Field(default=4, gt=0, le=600)
    transition: str | None = Field(default=None, max_length=120)
    prompt: str | None = Field(default=None, max_length=12000)
    source_excerpt: str = Field(min_length=1, max_length=4000)
    source_start: int | None = Field(default=None, ge=0)
    source_end: int | None = Field(default=None, ge=0)
    continuity_notes: str | None = Field(default=None, max_length=4000)
    entity_refs: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def valid_source_range(self):
        if (self.source_start is None) != (self.source_end is None):
            raise ValueError("source_start and source_end must be supplied together")
        if self.source_start is not None and self.source_end is not None and self.source_end < self.source_start:
            raise ValueError("source_end must be greater than or equal to source_start")
        return self

class StoryboardShotUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=12000)
    shot_size: ShotSize | None = None
    camera_angle: CameraAngle | None = None
    camera_movement: CameraMovement | None = None
    lens: str | None = Field(default=None, max_length=120)
    composition: str | None = Field(default=None, max_length=2000)
    action: str | None = Field(default=None, max_length=4000)
    dialogue: str | None = Field(default=None, max_length=4000)
    duration_seconds: float | None = Field(default=None, gt=0, le=600)
    transition: str | None = Field(default=None, max_length=120)
    prompt: str | None = Field(default=None, max_length=12000)
    source_excerpt: str | None = Field(default=None, min_length=1, max_length=4000)
    source_start: int | None = Field(default=None, ge=0)
    source_end: int | None = Field(default=None, ge=0)
    continuity_notes: str | None = Field(default=None, max_length=4000)
    entity_refs: list[str] | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def non_empty_update(self):
        if not (self.model_fields_set - {"expected_version"}):
            raise ValueError("At least one shot field must be updated")
        if (self.source_start is None) != (self.source_end is None):
            raise ValueError("source_start and source_end must be supplied together")
        if self.source_start is not None and self.source_end is not None and self.source_end < self.source_start:
            raise ValueError("source_end must be greater than or equal to source_start")
        return self

class StoryboardReorder(BaseModel):
    expected_story_version: int = Field(ge=1)
    shot_ids: list[str] = Field(min_length=1, max_length=500)

class StoryboardTakeCreate(BaseModel):
    asset_id: str = Field(min_length=36, max_length=36)
    prompt_snapshot: str | None = Field(default=None, max_length=12000)
    engine_key: str = Field(default="manual", min_length=1, max_length=100)
    engine_job_id: str | None = Field(default=None, max_length=200)
    generation_metadata: dict = Field(default_factory=dict)

class StoryboardTakeReview(BaseModel):
    status: Literal["selected", "approved", "rejected"]
    review_note: str | None = Field(default=None, max_length=2000)

class StoryboardPromptTaskCreate(BaseModel):
    model: str = Field(min_length=1, max_length=160)
    provider_id: str | None = Field(default=None, min_length=1, max_length=120)
    creative_direction: str = Field(default="", max_length=6000)
    temperature: float = Field(default=0.5, ge=0, le=2)
    max_tokens: int = Field(default=1600, ge=128, le=6000)


class StoryboardPromptApply(BaseModel):
    expected_version: int = Field(ge=1)


class StoryboardImageTaskCreate(BaseModel):
    workflow_id: str = Field(default="checkpoint-basic-v1", min_length=1, max_length=80)
    negative_prompt: str = Field(default="", max_length=6000)
    width: int = Field(default=1024, ge=256, le=2048)
    height: int = Field(default=1024, ge=256, le=2048)
    steps: int = Field(default=24, ge=1, le=80)
    cfg: float = Field(default=7.0, ge=1, le=30)
    seed: int | None = Field(default=None, ge=0, le=18446744073709551615)

    @field_validator("width", "height")
    @classmethod
    def dimensions_multiple_of_eight(cls, value):
        if value % 8:
            raise ValueError("Image dimensions must be divisible by 8")
        return value
