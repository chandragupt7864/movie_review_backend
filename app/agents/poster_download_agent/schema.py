from pydantic import BaseModel, Field


class PosterDownloadResult(BaseModel):
    movie_id: int
    title: str | None = None
    status: str
    poster_local_path: str | None = None
    backdrop_local_path: str | None = None
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class PosterDownloadRunResponse(BaseModel):
    success: bool = True
    agent: str = "POSTER_DOWNLOAD_AGENT"
    processed: int = 0
    completed: int = 0
    failed: int = 0
    results: list[PosterDownloadResult] = Field(default_factory=list)
