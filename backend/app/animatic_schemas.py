from pydantic import BaseModel, Field, model_validator


class AnimaticTaskCreate(BaseModel):
    width: int = Field(default=1280, ge=640, le=1920)
    height: int = Field(default=720, ge=360, le=1080)
    fps: int = Field(default=24, ge=24, le=30)

    @model_validator(mode="after")
    def validate_render_profile(self):
        if (self.width, self.height) not in {(1280, 720), (1920, 1080)}:
            raise ValueError("Animatic resolution must be 1280x720 or 1920x1080")
        if self.fps not in {24, 25, 30}:
            raise ValueError("Animatic frame rate must be 24, 25 or 30 fps")
        return self
