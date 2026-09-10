from pydantic import BaseModel, Field


class ShortsComposerResult(BaseModel):
    movie_id: int
    tmdb_id: int | None = None
    title: str | None = None
    status: str
    draft_video_path: str | None = None
    final_video_path: str | None = None
    duration_seconds: float | None = None
    cloudinary_video_url: str | None = None
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class ShortsComposerRunResponse(BaseModel):
    success: bool = True
    agent: str = "SHORTS_COMPOSER_AGENT"
    processed: int = 0
    completed: int = 0
    failed: int = 0
    results: list[ShortsComposerResult] = Field(default_factory=list)
