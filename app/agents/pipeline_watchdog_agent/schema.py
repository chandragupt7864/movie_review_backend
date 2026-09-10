from pydantic import BaseModel


class WatchdogResult(BaseModel):
    movie_id: int
    tmdb_id: int | None = None
    title: str | None = None
    action: str = "skipped"  # fixed | skipped | failed | requeued
    details: str | None = None
    fixes_applied: list[str] = []


class WatchdogRunResponse(BaseModel):
    processed: int
    fixed: int
    requeued: int
    skipped: int
    failed: int
    results: list[WatchdogResult]
