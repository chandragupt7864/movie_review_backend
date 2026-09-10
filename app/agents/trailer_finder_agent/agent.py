from app.agents.trailer_finder_agent.schema import TrailerFinderResult, TrailerFinderRunResponse
from app.core.agent_status import CURRENT_AGENT_TRAILER, TRAILER_COMPLETED, TRAILER_FAILED
from app.core.pipeline_utils import build_timeline_event
from app.core.trailer_video_utils import (
    is_supported_trailer_video,
    select_preferred_trailer_videos,
)


class TrailerFinderAgent:
    def __init__(self, tmdb_service, repository) -> None:
        self.tmdb_service = tmdb_service
        self.repository = repository

    def run(self, limit: int) -> dict:
        jobs = self.repository.get_pending_trailer_jobs(limit=limit)
        return self._run_jobs(jobs)

    def run_for_movie(self, movie_id: int) -> dict:
        movie = self.repository.get_movie_by_id(movie_id=movie_id)
        if not movie:
            result = TrailerFinderResult(movie_id=movie_id, status=TRAILER_FAILED, error="Movie not found.")
            return TrailerFinderRunResponse(processed=0, completed=0, failed=1, results=[result]).model_dump()
        return self._run_jobs([movie])

    def _run_jobs(self, jobs: list[dict]) -> dict:
        results: list[TrailerFinderResult] = []
        completed = 0
        failed = 0

        for job in jobs:
            result = self._process_movie(job)
            results.append(result)
            if result.status == TRAILER_COMPLETED:
                completed += 1
            else:
                failed += 1

        response = TrailerFinderRunResponse(
            processed=len(jobs),
            completed=completed,
            failed=failed,
            results=results,
        )
        return response.model_dump()

    def _process_movie(self, movie: dict) -> TrailerFinderResult:
        movie_id = int(movie["id"])
        tmdb_id = movie.get("tmdb_id")
        title = movie.get("movie_title")

        locked_movie = self.repository.lock_movie_for_agent(movie_id=movie_id, agent_name=CURRENT_AGENT_TRAILER)
        if not locked_movie:
            return TrailerFinderResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=TRAILER_FAILED,
                error="Movie is already locked or inactive.",
            )

        try:
            if not tmdb_id:
                raise ValueError("Movie does not have tmdb_id.")

            videos_response = self.tmdb_service.fetch_movie_videos(tmdb_id=int(tmdb_id))
            supported_videos = self._filter_supported_videos(videos_response.get("results", []))
            selected_videos = self._select_best_videos(supported_videos)
            selected_video = selected_videos[0] if selected_videos else None
            if not selected_video:
                raise TrailerNotFoundError("No YouTube trailer or teaser found.")

            youtube_id = selected_video["key"]
            trailer_url = f"https://www.youtube.com/watch?v={youtube_id}"
            self.repository.update_trailer_success(
                movie_id=movie_id,
                trailer_payload={
                    "youtube_id": youtube_id,
                    "url": trailer_url,
                    "title": selected_video.get("name"),
                    "type": selected_video.get("type"),
                    "official": bool(selected_video.get("official")),
                    "trailer_data": {
                        "selected_video": selected_video,
                        "selected_videos": selected_videos,
                        "tmdb_videos_response": {
                            **(videos_response if isinstance(videos_response, dict) else {}),
                            "results": selected_videos,
                        },
                    },
                    "timeline_event": build_timeline_event(
                        agent=CURRENT_AGENT_TRAILER,
                        status=TRAILER_COMPLETED,
                        message="Trailer found and saved",
                        data={"tmdb_id": tmdb_id, "youtube_id": youtube_id},
                    ),
                },
            )
            return TrailerFinderResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=TRAILER_COMPLETED,
                trailer_url=trailer_url,
                trailer_youtube_id=youtube_id,
            )
        except Exception as exc:
            not_found = isinstance(exc, TrailerNotFoundError)
            error_message = str(exc)
            self.repository.update_trailer_failed(
                movie_id=movie_id,
                error_payload={
                    "not_found": not_found,
                    "error_message": error_message,
                    "error_data": {
                        "tmdb_id": tmdb_id,
                        "title": title,
                        "error_type": type(exc).__name__,
                        "error_message": error_message,
                    },
                    "timeline_event": build_timeline_event(
                        agent=CURRENT_AGENT_TRAILER,
                        status=TRAILER_FAILED,
                        message=error_message,
                        data={"tmdb_id": tmdb_id},
                    ),
                },
            )
            return TrailerFinderResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=TRAILER_FAILED,
                error=error_message,
            )

    def _select_best_video(self, videos: list[dict]) -> dict | None:
        selected_videos = self._select_best_videos(videos)
        return selected_videos[0] if selected_videos else None

    def _select_best_videos(self, videos: list[dict]) -> list[dict]:
        return select_preferred_trailer_videos(videos)

    @staticmethod
    def _is_youtube(video: dict) -> bool:
        return str(video.get("site") or "").lower() == "youtube"

    def _filter_supported_videos(self, videos: list[dict]) -> list[dict]:
        return [video for video in videos if is_supported_trailer_video(video)]


class TrailerNotFoundError(Exception):
    pass
