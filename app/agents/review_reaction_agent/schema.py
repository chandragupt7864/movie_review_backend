from pydantic import BaseModel, Field


class ReviewScriptResult(BaseModel):
    movie_id: int
    tmdb_id: int | None = None
    title: str | None = None
    status: str
    final_script: str | None = None
    error: str | None = None


class ReviewScriptRunResponse(BaseModel):
    success: bool = True
    agent: str = "REVIEW_REACTION_AGENT"
    processed: int
    completed: int
    failed: int
    results: list[ReviewScriptResult] = Field(default_factory=list)
