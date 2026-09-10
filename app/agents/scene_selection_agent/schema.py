from pydantic import BaseModel, Field


class SceneSelectionResult(BaseModel):
    movie_id: int
    tmdb_id: int | None = None
    title: str | None = None
    status: str
    target_duration_seconds: float | None = None
    estimated_total_duration_seconds: float | None = None
    scenes_selected: int | None = None
    error: str | None = None


class SceneSelectionRunResponse(BaseModel):
    success: bool = True
    agent: str = "SCENE_SELECTION_AGENT"
    processed: int
    completed: int
    failed: int
    waiting_source_video: int
    waiting_voice_audio: int
    results: list[SceneSelectionResult] = Field(default_factory=list)
