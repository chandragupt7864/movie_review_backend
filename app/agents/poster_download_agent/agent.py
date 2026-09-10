import logging
from datetime import datetime, timezone
from pathlib import Path
from app.agents.poster_download_agent.schema import PosterDownloadResult, PosterDownloadRunResponse
from app.config import settings, PROJECT_ROOT
from app.core.agent_status import (
    CURRENT_AGENT_POSTER_DOWNLOAD,
    POSTER_PENDING,
    POSTER_RUNNING,
    POSTER_COMPLETED,
    POSTER_COMPLETED_PARTIAL,
    POSTER_FAILED,
    POSTER_WAITING_IMAGE_URL
)
from app.core.pipeline_utils import build_timeline_event

logger = logging.getLogger(__name__)

class PosterDownloadAgent:
    agent_name = CURRENT_AGENT_POSTER_DOWNLOAD

    def __init__(self, repository, download_service) -> None:
        self.repository = repository
        self.download_service = download_service

    def run(self, limit: int = 10) -> dict:
        jobs = self.repository.get_pending_poster_jobs(limit=limit)
        return self._run_jobs(jobs=jobs, force=False)

    def run_for_movie(self, movie_id: int, force: bool = False) -> dict:
        movie = self.repository.get_movie_by_id(movie_id=movie_id)
        if not movie:
            result = PosterDownloadResult(
                movie_id=movie_id,
                status=POSTER_FAILED,
                error="Movie not found."
            )
            return PosterDownloadRunResponse(processed=0, completed=0, failed=1, results=[result]).model_dump()
        return self._run_jobs(jobs=[movie], force=force)

    def _run_jobs(self, jobs: list[dict], force: bool) -> dict:
        results: list[PosterDownloadResult] = []
        completed = 0
        failed = 0

        for movie in jobs:
            result = self._process_movie(movie=movie, force=force)
            results.append(result)
            if result.status in [POSTER_COMPLETED, POSTER_COMPLETED_PARTIAL]:
                completed += 1
            else:
                failed += 1

        return PosterDownloadRunResponse(
            processed=len(jobs),
            completed=completed,
            failed=failed,
            results=results
        ).model_dump()

    def _process_movie(self, movie: dict, force: bool) -> PosterDownloadResult:
        movie_id = int(movie["id"])
        title = movie.get("movie_title")

        eligibility_error = self._eligibility_error(movie=movie, force=force)
        if eligibility_error:
            # Check if both urls are missing
            if not movie.get("poster_url") and not movie.get("backdrop_url"):
                # update status to WAITING_IMAGE_URL
                self.repository.update_poster_status(movie_id, POSTER_WAITING_IMAGE_URL)
                return PosterDownloadResult(
                    movie_id=movie_id,
                    title=title,
                    status=POSTER_WAITING_IMAGE_URL,
                    error="Waiting for poster or backdrop URLs."
                )
            return PosterDownloadResult(
                movie_id=movie_id,
                title=title,
                status=POSTER_FAILED,
                error=eligibility_error
            )

        locked_movie = self.repository.lock_movie_for_agent(movie_id=movie_id, agent_name=self.agent_name)
        if not locked_movie:
            return PosterDownloadResult(
                movie_id=movie_id,
                title=title,
                status=POSTER_FAILED,
                error="Movie is already locked or inactive."
            )

        try:
            movie_dir = Path(settings.poster_output_dir) / f"movie_{movie_id}"
            # Ensure folder exists
            resolved_dir = PROJECT_ROOT / movie_dir if not movie_dir.is_absolute() else movie_dir
            resolved_dir.mkdir(parents=True, exist_ok=True)

            poster_url = locked_movie.get("poster_url")
            backdrop_url = locked_movie.get("backdrop_url")

            poster_local_path = None
            backdrop_local_path = None
            warnings = []
            metadata = {}

            # Download poster
            poster_success = False
            if poster_url:
                try:
                    out_base = str(resolved_dir / "poster")
                    res = self.download_service.download_image(poster_url, out_base)
                    poster_local_path = res["local_path"]
                    metadata["poster"] = res
                    poster_success = True
                except Exception as e:
                    warnings.append(f"Poster download failed: {e}")

            # Download backdrop
            backdrop_success = False
            if backdrop_url:
                try:
                    out_base = str(resolved_dir / "backdrop")
                    res = self.download_service.download_image(backdrop_url, out_base)
                    backdrop_local_path = res["local_path"]
                    metadata["backdrop"] = res
                    backdrop_success = True
                except Exception as e:
                    warnings.append(f"Backdrop download failed: {e}")

            # Determine final status
            if not poster_url and not backdrop_url:
                # This case is already filtered, but safety first
                status = POSTER_WAITING_IMAGE_URL
            elif (poster_url and not poster_success) and (backdrop_url and not backdrop_success):
                # Both failed
                raise ValueError("Failed to download both poster and backdrop. Warnings: " + ", ".join(warnings))
            elif (poster_url and not poster_success) or (backdrop_url and not backdrop_success):
                # One succeeded, one failed
                status = POSTER_COMPLETED_PARTIAL
            else:
                # All present succeeded
                status = POSTER_COMPLETED

            poster_payload = {
                "poster_status": status,
                "poster_local_path": poster_local_path,
                "backdrop_local_path": backdrop_local_path,
                "poster_data": {
                    "downloaded_at": datetime.now(timezone.utc).isoformat(),
                    "metadata": metadata,
                    "warnings": warnings
                },
                "timeline_event": build_timeline_event(
                    agent=self.agent_name,
                    status=status,
                    message=f"Movie poster/backdrop downloaded locally. Warnings: {warnings}" if warnings else "Movie poster/backdrop downloaded locally",
                    data={"poster_local_path": poster_local_path, "backdrop_local_path": backdrop_local_path}
                )
            }

            self.repository.update_poster_success(movie_id=movie_id, poster_payload=poster_payload)

            return PosterDownloadResult(
                movie_id=movie_id,
                title=title,
                status=status,
                poster_local_path=poster_local_path,
                backdrop_local_path=backdrop_local_path,
                warnings=warnings
            )

        except Exception as exc:
            logger.error(f"Poster download agent failed for movie {movie_id}: {exc}", exc_info=True)
            self.repository.update_poster_failed(
                movie_id=movie_id,
                error_payload={
                    "error_message": str(exc),
                    "error_data": {
                        "title": title,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc)
                    },
                    "timeline_event": build_timeline_event(
                        agent=self.agent_name,
                        status=POSTER_FAILED,
                        message=str(exc)
                    )
                }
            )
            return PosterDownloadResult(
                movie_id=movie_id,
                title=title,
                status=POSTER_FAILED,
                error=str(exc)
            )

    @staticmethod
    def _eligibility_error(movie: dict, force: bool) -> str | None:
        if not movie.get("is_active", True):
            return "Movie is inactive."
        if movie.get("is_locked"):
            return "Movie is already locked."
        if not force and str(movie.get("poster_status") or POSTER_PENDING) != POSTER_PENDING:
            return "Poster download agent is not pending."
        if not movie.get("poster_url") and not movie.get("backdrop_url"):
            return "Both poster_url and backdrop_url are missing."
        return None
