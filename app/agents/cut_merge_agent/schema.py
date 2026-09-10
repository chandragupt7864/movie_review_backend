from pydantic import BaseModel, Field


class CutMergeResult(BaseModel):
    movie_id: int
    tmdb_id: int | None = None
    title: str | None = None
    status: str
    master_video_path: str | None = None
    clip_count: int | None = None
    transitions_used: list[str] = Field(default_factory=list)
    error: str | None = None


class CutMergeRunResponse(BaseModel):
    success: bool = True
    agent: str = "CUT_MERGE_AGENT"
    processed: int = 0
    completed: int = 0
    failed: int = 0
    results: list[CutMergeResult] = Field(default_factory=list)
