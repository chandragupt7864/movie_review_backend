from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class ShortsAppearance(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    theme: Literal["original", "cinematic", "vivid", "soft", "noir", "custom"] = "original"
    brightness: float = Field(default=0, ge=-0.3, le=0.3)
    contrast: float = Field(default=1, ge=0.5, le=1.8)
    saturation: float = Field(default=1, ge=0, le=2)
    gamma: float = Field(default=1, ge=0.5, le=1.8)
    sharpness: float = Field(default=0, ge=0, le=1.5)

    def video_filter(self) -> str:
        return (f"eq=brightness={self.brightness}:contrast={self.contrast}:"
                f"saturation={self.saturation}:gamma={self.gamma},"
                f"unsharp=5:5:{self.sharpness}:5:5:0")
