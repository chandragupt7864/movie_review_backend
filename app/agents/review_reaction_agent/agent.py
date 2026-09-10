from app.config import settings
from app.agents.review_reaction_agent.schema import ReviewScriptResult, ReviewScriptRunResponse
from app.core.agent_status import (
    CURRENT_AGENT_REVIEW_REACTION,
    NEXT_AGENT_VOICE_GENERATOR,
    OVERALL_SCRIPT_READY,
    OVERALL_WAITING_VOICE_UPLOAD,
    SCRIPT_COMPLETED,
    SCRIPT_FAILED,
)
from app.core.pipeline_utils import build_timeline_event


class ReviewReactionAgent:
    def __init__(self, tmdb_service, wikipedia_service, openai_script_service, repository) -> None:
        self.tmdb_service = tmdb_service
        self.wikipedia_service = wikipedia_service
        self.openai_script_service = openai_script_service
        self.repository = repository

    def run(self, limit: int) -> dict:
        jobs = self.repository.get_pending_review_script_jobs(limit=limit)
        return self._run_jobs(jobs)

    def run_for_movie(self, movie_id: int) -> dict:
        movie = self.repository.get_movie_by_id(movie_id=movie_id)
        if not movie:
            result = ReviewScriptResult(movie_id=movie_id, status=SCRIPT_FAILED, error="Movie not found.")
            return ReviewScriptRunResponse(processed=0, completed=0, failed=1, results=[result]).model_dump()
        return self._run_jobs([movie])

    def _run_jobs(self, jobs: list[dict]) -> dict:
        results: list[ReviewScriptResult] = []
        completed = 0
        failed = 0

        for job in jobs:
            result = self._process_movie(job)
            results.append(result)
            if result.status == SCRIPT_COMPLETED:
                completed += 1
            else:
                failed += 1

        response = ReviewScriptRunResponse(
            processed=len(jobs),
            completed=completed,
            failed=failed,
            results=results,
        )
        return response.model_dump()

    def _process_movie(self, movie: dict) -> ReviewScriptResult:
        movie_id = int(movie["id"])
        tmdb_id = movie.get("tmdb_id")
        title = movie.get("movie_title")

        locked_movie = self.repository.lock_movie_for_agent(movie_id=movie_id, agent_name=CURRENT_AGENT_REVIEW_REACTION)
        if not locked_movie:
            return ReviewScriptResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=SCRIPT_FAILED,
                error="Movie is already locked or inactive.",
            )

        try:
            review_data, movie_details = self._collect_research(movie=locked_movie)
        except Exception as exc:
            self._mark_failed(movie_id=movie_id, movie=locked_movie, exc=exc, stage="research")
            return ReviewScriptResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=SCRIPT_FAILED,
                error=str(exc),
            )

        try:
            script_data = self.openai_script_service.generate_script(movie_details=movie_details)
            waiting_for_manual_voice = settings.voice_mode == "manual"
            self.repository.update_review_script_success(
                movie_id=movie_id,
                review_payload={"review_data": review_data},
                script_payload={
                    "script_data": script_data,
                    "next_agent": NEXT_AGENT_VOICE_GENERATOR,
                    "overall_status": OVERALL_WAITING_VOICE_UPLOAD if waiting_for_manual_voice else OVERALL_SCRIPT_READY,
                    "timeline_event": build_timeline_event(
                        agent=CURRENT_AGENT_REVIEW_REACTION,
                        status=SCRIPT_COMPLETED,
                        message=(
                            "Review research completed and Shorts script generated. Waiting for manual voice upload."
                            if waiting_for_manual_voice
                            else "Review research completed and Shorts script generated"
                        ),
                        data={"tmdb_id": tmdb_id, "voice_mode": settings.voice_mode},
                    ),
                },
            )
            return ReviewScriptResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=SCRIPT_COMPLETED,
                final_script=script_data["script"],
            )
        except Exception as exc:
            self._mark_failed(movie_id=movie_id, movie=locked_movie, exc=exc, stage="script", review_data=review_data)
            return ReviewScriptResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=SCRIPT_FAILED,
                error=str(exc),
            )

    def _collect_research(self, movie: dict) -> tuple[dict, dict]:
        tmdb_id = movie.get("tmdb_id")
        if not tmdb_id:
            raise ValueError("Movie does not have tmdb_id.")

        tmdb_warning = None
        try:
            details = self.tmdb_service.get_movie_details(tmdb_id=int(tmdb_id))
            reviews = self.tmdb_service.get_movie_reviews(tmdb_id=int(tmdb_id))
        except Exception as exc:
            details = self._fallback_movie_details(movie=movie)
            reviews = {"results": []}
            tmdb_warning = str(exc)
        wikipedia_summary = self._safe_wikipedia(movie_title=movie.get("movie_title") or details.get("title") or "")
        review_summaries = self._summarize_reviews(reviews=reviews)
        source_urls = self._build_source_urls(tmdb_id=int(tmdb_id), details=details, reviews=review_summaries, wikipedia=wikipedia_summary)

        movie_details = {
            "movie_title": movie.get("movie_title") or details.get("title"),
            # Fresh TMDB metadata wins because announced dates can change after discovery.
            "release_date": str(details.get("release_date") or movie.get("release_date") or ""),
            "genres": self._extract_genres(movie=movie, details=details),
            "overview": details.get("overview") or self._movie_data_value(movie, "overview"),
            "runtime": details.get("runtime"),
            "tagline": details.get("tagline"),
            "status": details.get("status"),
            "vote_average": details.get("vote_average") or self._movie_data_value(movie, "vote_average"),
            "vote_count": details.get("vote_count") or self._movie_data_value(movie, "vote_count"),
            "popularity": details.get("popularity") or self._movie_data_value(movie, "popularity"),
            "trailer_url": movie.get("trailer_url"),
            "wikipedia_summary": (wikipedia_summary or {}).get("extract"),
            "tmdb_review_summaries": review_summaries,
            "cast": self._top_cast(details=details),
            "director": self._director(details=details),
            "keywords": self._keywords(details=details),
            "source_urls": source_urls,
        }
        if tmdb_warning:
            movie_details["tmdb_warning"] = tmdb_warning

        review_data = {
            "tmdb_details": self._compact_tmdb_details(details=details),
            "tmdb_review_summaries": review_summaries,
            "wikipedia": wikipedia_summary,
            "movie_details": movie_details,
            "source_urls": source_urls,
        }
        if tmdb_warning:
            review_data["tmdb_warning"] = tmdb_warning
        return review_data, movie_details

    @staticmethod
    def _fallback_movie_details(movie: dict) -> dict:
        movie_data = movie.get("movie_data_json") or {}
        return {
            "id": movie.get("tmdb_id"),
            "title": movie.get("movie_title") or movie_data.get("title"),
            "overview": movie_data.get("overview"),
            "release_date": str(movie.get("release_date") or movie_data.get("release_date") or ""),
            "status": movie_data.get("status"),
            "vote_average": movie_data.get("vote_average"),
            "vote_count": movie_data.get("vote_count"),
            "popularity": movie_data.get("popularity"),
            "genres": [{"name": genre} for genre in (movie.get("target_genres_json") or []) if genre],
            "credits": {"cast": [], "crew": []},
            "keywords": {"keywords": []},
            "external_ids": {},
        }

    def _safe_wikipedia(self, movie_title: str) -> dict | None:
        if not movie_title:
            return None
        try:
            return self.wikipedia_service.fetch_movie_summary(movie_title=movie_title)
        except Exception as exc:
            return {"source": "Wikipedia", "error": str(exc)}

    @staticmethod
    def _summarize_reviews(reviews: dict) -> list[dict]:
        summaries = []
        for review in (reviews.get("results") or [])[:5]:
            author_details = review.get("author_details") or {}
            content = str(review.get("content") or "").replace("\n", " ").strip()
            summaries.append(
                {
                    "author": review.get("author"),
                    "rating": author_details.get("rating"),
                    "created_at": review.get("created_at"),
                    "summary": content[:300],
                    "url": review.get("url"),
                }
            )
        return summaries

    @staticmethod
    def _extract_genres(movie: dict, details: dict) -> list[str]:
        if isinstance(movie.get("target_genres_json"), list):
            return [str(genre) for genre in movie["target_genres_json"]]
        return [genre.get("name") for genre in details.get("genres", []) if genre.get("name")]

    @staticmethod
    def _movie_data_value(movie: dict, key: str):
        movie_data = movie.get("movie_data_json") or {}
        if isinstance(movie_data, dict):
            return movie_data.get(key)
        return None

    @staticmethod
    def _top_cast(details: dict) -> list[str]:
        credits = details.get("credits") or {}
        return [cast.get("name") for cast in (credits.get("cast") or [])[:5] if cast.get("name")]

    @staticmethod
    def _director(details: dict) -> str | None:
        credits = details.get("credits") or {}
        for crew in credits.get("crew") or []:
            if crew.get("job") == "Director":
                return crew.get("name")
        return None

    @staticmethod
    def _keywords(details: dict) -> list[str]:
        keywords = details.get("keywords") or {}
        return [item.get("name") for item in keywords.get("keywords", [])[:10] if item.get("name")]

    @staticmethod
    def _build_source_urls(tmdb_id: int, details: dict, reviews: list[dict], wikipedia: dict | None) -> list[str]:
        urls = [f"https://www.themoviedb.org/movie/{tmdb_id}"]
        imdb_id = (details.get("external_ids") or {}).get("imdb_id")
        if imdb_id:
            urls.append(f"https://www.imdb.com/title/{imdb_id}/")
        if wikipedia and wikipedia.get("url"):
            urls.append(wikipedia["url"])
        urls.extend(review["url"] for review in reviews if review.get("url"))
        return urls

    @staticmethod
    def _compact_tmdb_details(details: dict) -> dict:
        return {
            "id": details.get("id"),
            "title": details.get("title"),
            "overview": details.get("overview"),
            "runtime": details.get("runtime"),
            "tagline": details.get("tagline"),
            "status": details.get("status"),
            "vote_average": details.get("vote_average"),
            "vote_count": details.get("vote_count"),
            "popularity": details.get("popularity"),
            "genres": details.get("genres"),
            "external_ids": details.get("external_ids"),
            "keywords": details.get("keywords"),
        }

    def _mark_failed(self, movie_id: int, movie: dict, exc: Exception, stage: str, review_data: dict | None = None) -> None:
        self.repository.update_review_script_failed(
            movie_id=movie_id,
            error_payload={
                "stage": stage,
                "error_message": str(exc),
                "review_data": review_data,
                "error_data": {
                    "stage": stage,
                    "tmdb_id": movie.get("tmdb_id"),
                    "title": movie.get("movie_title"),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
                "timeline_event": build_timeline_event(
                    agent=CURRENT_AGENT_REVIEW_REACTION,
                    status=SCRIPT_FAILED,
                    message=str(exc),
                    data={"stage": stage, "tmdb_id": movie.get("tmdb_id")},
                ),
            },
        )
