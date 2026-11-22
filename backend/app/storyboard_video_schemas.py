from pydantic import BaseModel, Field, field_validator


class StoryboardVideoTaskCreate(BaseModel):
    workflow_id: str = Field(default="wan2.1-i2v-basic-v1", min_length=1, max_length=80)
    negative_prompt: str = Field(default="", max_length=6000)
    frames: int = Field(default=33, ge=17, le=73)
    fps: int = Field(default=16, ge=8, le=30)
    seed: int | None = Field(default=None, ge=0, le=18446744073709551615)

    @field_validator("frames")
    @classmethod
    def valid_wan_frame_count(cls, value):
        if value not in {33, 49, 73}:
            raise ValueError("Wan video frame count must be 33, 49 or 73")
        return value

    @field_validator("fps")
    @classmethod
    def valid_video_fps(cls, value):
        if value not in {16, 24}:
            raise ValueError("Video frame rate must be 16 or 24 fps")
        return value
