from pydantic import BaseModel, Field


class TrailerFinderResult(BaseModel):
    movie_id: int
    tmdb_id: int | None = None
    title: str | None = None
    status: str
    trailer_url: str | None = None
    trailer_youtube_id: str | None = None
    error: str | None = None


class TrailerFinderRunResponse(BaseModel):
    success: bool = True
    agent: str = "TRAILER_FINDER_AGENT"
    processed: int
    completed: int
    failed: int
    results: list[TrailerFinderResult] = Field(default_factory=list)
