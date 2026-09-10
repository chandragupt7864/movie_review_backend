from pathlib import Path

from app.agents.shorts_composer_agent.schema import ShortsComposerResult, ShortsComposerRunResponse
from app.config import settings
from app.core.agent_status import (
    CURRENT_AGENT_SHORTS_COMPOSER,
    NEXT_AGENT_DONE,
    NEXT_AGENT_SHORTS_COMPOSER,
    OVERALL_BGM_READY,
    OVERALL_FINAL_VIDEO_READY,
    OVERALL_MASTER_VIDEO_READY,
    OVERALL_SHORTS_COMPOSER_FAILED,
    RENDER_COMPLETED,
    SHORTS_COMPLETED,
    SHORTS_FAILED,
    SHORTS_PENDING,
    VOICE_COMPLETED,
)
from app.core.pipeline_utils import build_timeline_event


class ShortsComposerAgent:
    agent_name = CURRENT_AGENT_SHORTS_COMPOSER

    def __init__(self, repository, shorts_composer_service, cloudinary_video_storage_service=None) -> None:
        self.repository = repository
        self.shorts_composer_service = shorts_composer_service
        self.cloudinary_video_storage_service = cloudinary_video_storage_service

    def run(self, limit: int = 1) -> dict:
        jobs = self.repository.get_pending_shorts_composer_jobs(limit=limit)
        return self._run_jobs(jobs=jobs, force=False)

    def run_for_movie(self, movie_id: int, force: bool = False, appearance: dict | None = None) -> dict:
        movie = self.repository.get_movie_by_id(movie_id=movie_id)
        if not movie:
            result = ShortsComposerResult(movie_id=movie_id, status=SHORTS_FAILED, error="Movie not found.")
            return ShortsComposerRunResponse(processed=0, completed=0, failed=1, results=[result]).model_dump()
        return self._run_jobs(jobs=[movie], force=force, appearance=appearance)

    def _run_jobs(self, jobs: list[dict], force: bool, appearance: dict | None = None) -> dict:
        results: list[ShortsComposerResult] = []
        completed = 0
        failed = 0

        for movie in jobs:
            result = self._process_movie(movie=movie, force=force, appearance=appearance)
            results.append(result)
            if result.status == SHORTS_COMPLETED:
                completed += 1
            else:
                failed += 1

        return ShortsComposerRunResponse(
            processed=len(jobs),
            completed=completed,
            failed=failed,
            results=results,
        ).model_dump()

    def _process_movie(self, movie: dict, force: bool, appearance: dict | None = None) -> ShortsComposerResult:
        movie_id = int(movie["id"])
        tmdb_id = movie.get("tmdb_id")
        title = movie.get("movie_title")

        eligibility_error = self._eligibility_error(movie=movie, force=force)
        if eligibility_error:
            return ShortsComposerResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=SHORTS_FAILED,
                error=eligibility_error,
            )

        locked_movie = self.repository.lock_movie_for_agent(movie_id=movie_id, agent_name=self.agent_name)
        if not locked_movie:
            return ShortsComposerResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=SHORTS_FAILED,
                error="Movie is already locked or inactive.",
            )

        try:
            output_path = self.shorts_composer_service.build_output_path(movie_id=movie_id)
            bgm_data = locked_movie.get("bgm_data_json") or {}
            thumbnail_data = locked_movie.get("thumbnail_data_json") or {}
            bgm_path = (
                (locked_movie.get("bgm_audio_path") or settings.bgm_default_path)
                if settings.bgm_enabled
                else None
            )
            bgm_path = self._restore_cloudinary_asset(
                movie_id=movie_id,
                local_path=bgm_path,
                cloudinary_url=bgm_data.get("cloudinary_bgm_url") if isinstance(bgm_data, dict) else None,
                filename="background_music.mp3",
            )
            thumbnail_path = (thumbnail_data.get("local_output_path") if isinstance(thumbnail_data, dict) else None) or locked_movie.get("thumbnail_path")
            thumbnail_path = self._restore_cloudinary_asset(
                movie_id=movie_id,
                local_path=thumbnail_path,
                cloudinary_url=thumbnail_data.get("cloudinary_thumbnail_url") if isinstance(thumbnail_data, dict) else None,
                filename="thumbnail.jpg",
            )
            compose_result = self.shorts_composer_service.compose_shorts_draft(
                movie_id=movie_id,
                master_video_path=str(locked_movie.get("master_video_path") or ""),
                voice_audio_path=str(locked_movie.get("voice_audio_path") or ""),
                output_path=output_path,
                bgm_path=bgm_path,
                appearance=appearance if appearance is not None else (locked_movie.get("shorts_data_json") or {}).get("appearance"),
                thumbnail_path=thumbnail_path,
            )
            upload_warnings = list(compose_result.get("warnings") or [])
            if self.cloudinary_video_storage_service is not None:
                try:
                    cloudinary_result = self.cloudinary_video_storage_service.upload_final_video(
                        movie_id=movie_id,
                        local_file_path=compose_result.get("final_video_path") or compose_result["draft_video_path"],
                    )
                    compose_result["cloudinary_video_url"] = cloudinary_result["secure_url"]
                    compose_result["cloudinary_public_id"] = cloudinary_result["public_id"]
                    compose_result["cloudinary"] = cloudinary_result
                except Exception as upload_exc:
                    if settings.cloudinary_video_upload_required:
                        raise RuntimeError(f"Cloudinary final video upload failed: {upload_exc}") from upload_exc
                    upload_warnings.append(f"Cloudinary upload failed; local video remains available: {upload_exc}")
            compose_result["warnings"] = upload_warnings
            self.repository.update_shorts_composer_success(
                movie_id=movie_id,
                shorts_payload={
                    **compose_result,
                    "next_agent": NEXT_AGENT_DONE,
                    "overall_status": OVERALL_FINAL_VIDEO_READY,
                    "timeline_event": build_timeline_event(
                        agent=self.agent_name,
                        status=SHORTS_COMPLETED,
                        message="9:16 final Shorts video composed successfully",
                        data={
                            "tmdb_id": tmdb_id,
                            "draft_video_path": compose_result["draft_video_path"],
                            "final_video_path": compose_result.get("final_video_path") or compose_result["draft_video_path"],
                            "duration_seconds": compose_result.get("duration_seconds"),
                            "cloudinary_video_url": compose_result.get("cloudinary_video_url"),
                            "thumbnail_mode": settings.thumbnail_mode,
                        },
                    ),
                },
            )

            return ShortsComposerResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=SHORTS_COMPLETED,
                draft_video_path=compose_result["draft_video_path"],
                final_video_path=compose_result.get("final_video_path"),
                duration_seconds=compose_result.get("duration_seconds"),
                cloudinary_video_url=compose_result.get("cloudinary_video_url"),
                warnings=list(compose_result.get("warnings") or []),
            )
        except Exception as exc:
            self.repository.update_shorts_composer_failed(
                movie_id=movie_id,
                error_payload={
                    "error_message": str(exc),
                    "error_data": {
                        "tmdb_id": tmdb_id,
                        "title": title,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    },
                    "timeline_event": build_timeline_event(
                        agent=self.agent_name,
                        status=SHORTS_FAILED,
                        message=str(exc),
                        data={"tmdb_id": tmdb_id},
                    ),
                },
            )
            return ShortsComposerResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=SHORTS_FAILED,
                error=str(exc),
            )

    def _restore_cloudinary_asset(
        self,
        movie_id: int,
        local_path: str | None,
        cloudinary_url: str | None,
        filename: str,
    ) -> str | None:
        if local_path:
            candidate = Path(local_path)
            if not candidate.is_absolute():
                from app.config import PROJECT_ROOT

                candidate = PROJECT_ROOT / candidate
            if candidate.is_file():
                return local_path
        if not cloudinary_url or self.cloudinary_video_storage_service is None:
            return local_path
        restored_path = Path(settings.shorts_temp_dir) / f"movie_{movie_id}" / filename
        self.cloudinary_video_storage_service.download_asset(
            secure_url=cloudinary_url,
            local_file_path=str(restored_path),
        )
        return str(restored_path).replace("\\", "/")

    @staticmethod
    def _eligibility_error(movie: dict, force: bool) -> str | None:
        if not movie.get("is_active", True):
            return "Movie is inactive."
        if movie.get("is_locked"):
            return "Movie is already locked."
        if not force and movie.get("next_agent") != NEXT_AGENT_SHORTS_COMPOSER:
            return "Movie is not queued for shorts composer."
        if str(movie.get("render_status") or "") != RENDER_COMPLETED:
            return "16:9 master video is not ready yet."
        if not movie.get("master_video_path"):
            return "Master video path is missing."
        if str(movie.get("voice_status") or "") != VOICE_COMPLETED:
            return "Voice audio is not ready yet."
        if not movie.get("thumbnail_path") or movie.get("thumbnail_status") != "COMPLETED":
            return "Upload a thumbnail before composing Shorts."
        if not movie.get("voice_audio_path"):
            return "Voice audio path is missing."
        if not force and str(movie.get("shorts_status") or SHORTS_PENDING) != SHORTS_PENDING:
            return "Shorts composer is not pending."
        if str(movie.get("overall_status") or "") not in {
            "",
            OVERALL_MASTER_VIDEO_READY,
            OVERALL_BGM_READY,
            OVERALL_FINAL_VIDEO_READY,
        } and not force:
            return "Movie is not in a valid state for shorts composer."
        return None
