from typing import Optional
from pydantic import BaseModel, Field


class VideoDownloaderResult(BaseModel):
    movie_id: int
    tmdb_id: Optional[int] = None
    title: Optional[str] = None
    status: str
    local_dir: Optional[str] = None
    downloaded_path: Optional[str] = None
    error: Optional[str] = None


class VideoDownloaderRunResponse(BaseModel):
    processed: int
    completed: int
    failed: int
    results: list[VideoDownloaderResult] = Field(default_factory=list)
