from typing import Literal

from pydantic import BaseModel, Field


class DiscoveryRunResponse(BaseModel):
    category: Literal["upcoming", "released", "trending"]
    pages_requested: int
    fetched: int
    inserted: int
    updated: int
    skipped: int
    errors: int
    error_items: list[dict] = Field(default_factory=list)

