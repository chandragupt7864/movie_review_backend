try:
    from psycopg2.extras import Json
except ModuleNotFoundError:
    class Json:  # type: ignore[no-redef]
        def __init__(self, adapted):
            self.adapted = adapted

from app.agents.movie_discovery_agent.schema import DiscoveryRunResponse
from app.config import settings
from app.constants import (
    ALLOWED_GENRE_IDS,
    HOLLYWOOD_REGION,
    TMDB_IMAGE_BASE_URL,
)
from app.core.agent_status import (
    CURRENT_AGENT_DISCOVERY,
    DISCOVERY_COMPLETED,
    NEXT_AGENT_TRAILER,
    OVERALL_DISCOVERED,
)
from app.core.pipeline_utils import build_timeline_event


class MovieDiscoveryAgent:
    def __init__(self, tmdb_service, repository) -> None:
        self.tmdb_service = tmdb_service
        self.repository = repository

    def run(self, category: str, pages: int) -> dict:
        inserted = 0
        updated = 0
        skipped = 0
        errors = 0
        fetched = 0
        error_items: list[dict] = []

        for page in range(1, pages + 1):
            movies = self.tmdb_service.fetch_movies(category=category, page=page)
            fetched += len(movies)

            for movie in movies:
                try:
                    matched_genres = self._match_genres(movie)
                    if (
                        not matched_genres
                        or movie.get("original_language") != "en"
                        or not self._passes_quality_filter(movie=movie, category=category)
                    ):
                        skipped += 1
                        continue

                    payload = self._build_pipeline_payload(
                        movie=movie,
                        category=category,
                        matched_genres=matched_genres,
                    )
                    result = self.repository.upsert_movie(payload)
                    if result == "inserted":
                        inserted += 1
                    else:
                        updated += 1
                except Exception as exc:
                    errors += 1
                    error_items.append(
                        {
                            "tmdb_id": movie.get("id"),
                            "title": movie.get("title"),
                            "error": str(exc),
                        }
                    )

        response = DiscoveryRunResponse(
            category=category,
            pages_requested=pages,
            fetched=fetched,
            inserted=inserted,
            updated=updated,
            skipped=skipped,
            errors=errors,
            error_items=error_items,
        )
        return response.model_dump()

    def queue_selected_movie(self, movie: dict, category: str = "selected") -> dict:
        matched_genres = self._match_genres(movie)
        payload = self._build_pipeline_payload(
            movie=movie,
            category=category,
            matched_genres=matched_genres,
        )
        result = self.repository.upsert_movie(payload)
        return {
            "success": True,
            "tmdb_id": movie["id"],
            "movie_title": movie.get("title") or movie.get("original_title"),
            "discovery_category": category,
            "matched_genres": matched_genres,
            "result": result,
            "queued_next_agent": NEXT_AGENT_TRAILER,
        }

    def _match_genres(self, movie: dict) -> list[str]:
        genre_ids = set(self._extract_genre_ids(movie))
        return [genre_name for genre_id, genre_name in ALLOWED_GENRE_IDS.items() if genre_id in genre_ids]

    def _passes_quality_filter(self, movie: dict, category: str) -> bool:
        vote_average = float(movie.get("vote_average") or 0)
        vote_count = int(movie.get("vote_count") or 0)
        popularity = float(movie.get("popularity") or 0)

        if category == "released":
            return vote_average >= settings.tmdb_min_vote_average and vote_count >= settings.tmdb_min_vote_count

        if category == "upcoming":
            return popularity >= settings.tmdb_min_upcoming_popularity

        return True

    def _build_pipeline_payload(self, movie: dict, category: str, matched_genres: list[str]) -> dict:
        tmdb_id = movie["id"]
        title = movie.get("title") or movie.get("original_title") or f"tmdb-{tmdb_id}"
        timeline_event = build_timeline_event(
            agent=CURRENT_AGENT_DISCOVERY,
            status=DISCOVERY_COMPLETED,
            message="Movie discovered from TMDB.",
            data={"category": category, "tmdb_id": tmdb_id, "matched_genres": matched_genres},
        )

        return {
            "job_code": f"TMDB-{tmdb_id}",
            "overall_status": OVERALL_DISCOVERED,
            "current_agent": CURRENT_AGENT_DISCOVERY,
            "next_agent": NEXT_AGENT_TRAILER,
            "progress_percent": 10,
            "tmdb_id": tmdb_id,
            "imdb_id": None,
            "movie_title": title,
            "release_date": movie.get("release_date") or None,
            "language_code": movie.get("original_language") or "en",
            "region_code": HOLLYWOOD_REGION,
            "poster_url": self._build_image_url(movie.get("poster_path")),
            "backdrop_url": self._build_image_url(movie.get("backdrop_path")),
            "discovery_category": category,
            "target_genres_json": Json(matched_genres),
            "discovery_status": DISCOVERY_COMPLETED,
            "movie_data_json": Json(movie),
            "process_timeline_json": Json([timeline_event]),
        }

    def _build_image_url(self, path: str | None) -> str | None:
        if not path:
            return None
        return f"{TMDB_IMAGE_BASE_URL}{path}"

    @staticmethod
    def _extract_genre_ids(movie: dict) -> list[int]:
        genre_ids = movie.get("genre_ids")
        if isinstance(genre_ids, list):
            return [int(item) for item in genre_ids if isinstance(item, int)]
        genres = movie.get("genres") or []
        extracted: list[int] = []
        if isinstance(genres, list):
            for item in genres:
                if not isinstance(item, dict):
                    continue
                genre_id = item.get("id")
                if isinstance(genre_id, int):
                    extracted.append(genre_id)
        return extracted
