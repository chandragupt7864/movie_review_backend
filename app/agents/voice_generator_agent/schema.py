from pydantic import BaseModel, Field


class VoiceGeneratorResult(BaseModel):
    movie_id: int
    tmdb_id: int | None = None
    title: str | None = None
    status: str
    audio_path: str | None = None
    cached: bool | None = None
    error: str | None = None


class VoiceGeneratorRunResponse(BaseModel):
    success: bool = True
    agent: str = "VOICE_GENERATOR_AGENT"
    processed: int
    completed: int
    failed: int
    results: list[VoiceGeneratorResult] = Field(default_factory=list)
