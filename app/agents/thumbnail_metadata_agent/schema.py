from pydantic import BaseModel, Field


class ThumbnailGeneratorResult(BaseModel):
    movie_id: int
    tmdb_id: int | None = None
    title: str | None = None
    status: str
    thumbnail_path: str | None = None
    uploaded_to_supabase: bool = False
    text_used: str | None = None
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class ThumbnailGeneratorRunResponse(BaseModel):
    success: bool = True
    agent: str = "THUMBNAIL_METADATA_AGENT"
    processed: int = 0
    completed: int = 0
    failed: int = 0
    results: list[ThumbnailGeneratorResult] = Field(default_factory=list)
