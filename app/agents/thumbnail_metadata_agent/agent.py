import logging
from datetime import datetime, timezone
from pathlib import Path
from app.agents.thumbnail_metadata_agent.schema import ThumbnailGeneratorResult, ThumbnailGeneratorRunResponse
from app.config import settings
from app.core.agent_status import (
    CURRENT_AGENT_THUMBNAIL_METADATA,
    NEXT_AGENT_THUMBNAIL_METADATA,
    THUMBNAIL_COMPLETED,
    THUMBNAIL_FAILED,
    THUMBNAIL_PENDING,
    SHORTS_COMPLETED,
    OVERALL_THUMBNAIL_READY
)
from app.core.pipeline_utils import build_timeline_event

logger = logging.getLogger(__name__)

class ThumbnailMetadataAgent:
    agent_name = CURRENT_AGENT_THUMBNAIL_METADATA

    def __init__(self, repository, asset_service, generator_service, storage_service, cloudinary_storage_service=None) -> None:
        self.repository = repository
        self.asset_service = asset_service
        self.generator_service = generator_service
        self.storage_service = storage_service
        self.cloudinary_storage_service = cloudinary_storage_service

    def run(self, limit: int = 1) -> dict:
        jobs = self.repository.get_pending_thumbnail_jobs(limit=limit)
        return self._run_jobs(jobs=jobs, force=False)

    def run_for_movie(self, movie_id: int, force: bool = False) -> dict:
        movie = self.repository.get_movie_by_id(movie_id=movie_id)
        if not movie:
            result = ThumbnailGeneratorResult(
                movie_id=movie_id,
                status=THUMBNAIL_FAILED,
                error="Movie not found."
            )
            return ThumbnailGeneratorRunResponse(processed=0, completed=0, failed=1, results=[result]).model_dump()
        return self._run_jobs(jobs=[movie], force=force)

    def _run_jobs(self, jobs: list[dict], force: bool) -> dict:
        results: list[ThumbnailGeneratorResult] = []
        completed = 0
        failed = 0

        for movie in jobs:
            result = self._process_movie(movie=movie, force=force)
            results.append(result)
            if result.status == THUMBNAIL_COMPLETED:
                completed += 1
            else:
                failed += 1

        return ThumbnailGeneratorRunResponse(
            processed=len(jobs),
            completed=completed,
            failed=failed,
            results=results
        ).model_dump()

    def _process_movie(self, movie: dict, force: bool) -> ThumbnailGeneratorResult:
        movie_id = int(movie["id"])
        tmdb_id = movie.get("tmdb_id")
        title = movie.get("movie_title")

        eligibility_error = self._eligibility_error(movie=movie, force=force)
        if eligibility_error:
            return ThumbnailGeneratorResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=THUMBNAIL_FAILED,
                error=eligibility_error
            )

        locked_movie = self.repository.lock_movie_for_agent(movie_id=movie_id, agent_name=self.agent_name)
        if not locked_movie:
            return ThumbnailGeneratorResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=THUMBNAIL_FAILED,
                error="Movie is already locked or inactive."
            )

        try:
            # 1. Collect reference assets locally
            ref_data = self.asset_service.collect_thumbnail_references(locked_movie)
            references = ref_data["references"]
            warnings = list(ref_data["warnings"])

            if not references:
                raise ValueError("No reference images (poster, backdrop, or video frames) could be collected.")

            # 2. Setup output path locally
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            output_filename = f"thumbnail_{movie_id}_{timestamp}.jpg"
            output_dir = Path(settings.thumbnail_output_dir) / f"movie_{movie_id}"
            output_dir.mkdir(parents=True, exist_ok=True)
            local_output_path = str(output_dir / output_filename)

            # 3. Generate Thumbnail
            gen_result = self.generator_service.generate_thumbnail(
                movie_row=locked_movie,
                references=references,
                output_path=local_output_path
            )

            # 4. Keep the local file for FFmpeg and persist a cloud copy.
            uploaded_to_supabase = False
            uploaded_to_cloudinary = False
            supabase_path = None
            final_thumbnail_path = gen_result["output_path"]
            cloudinary_result = None

            if settings.cloudinary_thumbnail_upload_enabled and self.cloudinary_storage_service:
                try:
                    cloudinary_result = self.cloudinary_storage_service.upload_thumbnail(
                        movie_id=movie_id,
                        local_file_path=local_output_path,
                    )
                    uploaded_to_cloudinary = True
                except Exception as e:
                    if settings.cloudinary_thumbnail_upload_required:
                        raise
                    warnings.append(f"Failed to upload thumbnail to Cloudinary: {e}")
                    logger.warning("Failed to upload thumbnail to Cloudinary: %s", e, exc_info=True)
            elif settings.thumbnail_upload_to_supabase and self.storage_service:
                try:
                    storage_path = f"thumbnails/movie_{movie_id}/thumbnail_{timestamp}.jpg"
                    upload_res = self.storage_service.upload_file(
                        local_file_path=local_output_path,
                        bucket=settings.supabase_thumbnail_bucket,
                        storage_path=storage_path,
                        content_type="image/jpeg"
                    )
                    final_thumbnail_path = upload_res["thumbnail_path"]
                    uploaded_to_supabase = True
                    supabase_path = storage_path
                except Exception as e:
                    warnings.append(f"Failed to upload thumbnail to Supabase Storage: {e}")
                    logger.warning(f"Failed to upload thumbnail to Supabase: {e}", exc_info=True)

            # 5. Extract metadata fields from script
            sd = locked_movie.get("script_data_json") or {}
            if not isinstance(sd, dict):
                sd = {}
            
            youtube_title = sd.get("title") or sd.get("youtube_title") or f"{title} Review - Movie Review"
            youtube_description = sd.get("description") or sd.get("youtube_description") or f"Quick movie review of {title}."
            youtube_tags = sd.get("tags") or sd.get("youtube_tags") or [title, "movie review", "shorts"]
            youtube_keywords = sd.get("keywords") or sd.get("youtube_keywords") or [title, "review"]

            # Save payload to DB
            thumbnail_data = {
                "local_output_path": gen_result["output_path"],
                "width": gen_result["width"],
                "height": gen_result["height"],
                "text_used": gen_result["text_used"],
                "references_used": gen_result["references_used"],
                "foreground_used": gen_result.get("foreground_used"),
                "uploaded_to_supabase": uploaded_to_supabase,
                "uploaded_to_cloudinary": uploaded_to_cloudinary,
                "cloudinary_thumbnail_url": cloudinary_result["secure_url"] if cloudinary_result else None,
                "cloudinary_public_id": cloudinary_result["public_id"] if cloudinary_result else None,
                "cloudinary": cloudinary_result or {},
                "supabase_path": supabase_path,
                "warnings": warnings,
                "generated_at": datetime.now(timezone.utc).isoformat()
            }

            thumbnail_payload = {
                "thumbnail_path": final_thumbnail_path,
                "thumbnail_data": thumbnail_data,
                "youtube_title": youtube_title,
                "youtube_description": youtube_description,
                "youtube_tags": youtube_tags,
                "youtube_keywords": youtube_keywords,
                "timeline_event": build_timeline_event(
                    agent=self.agent_name,
                    status=THUMBNAIL_COMPLETED,
                    message=(
                        "Thumbnail generated using Python and uploaded to Cloudinary"
                        if uploaded_to_cloudinary
                        else "Thumbnail generated using Python and uploaded to Supabase Storage"
                        if uploaded_to_supabase
                        else "Thumbnail generated locally (cloud upload failed/skipped)"
                    ),
                    data={
                        "tmdb_id": tmdb_id,
                        "thumbnail_path": final_thumbnail_path,
                        "text_used": gen_result["text_used"]
                    }
                )
            }

            self.repository.update_thumbnail_success(movie_id=movie_id, thumbnail_payload=thumbnail_payload)

            return ThumbnailGeneratorResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=THUMBNAIL_COMPLETED,
                thumbnail_path=final_thumbnail_path,
                uploaded_to_supabase=uploaded_to_supabase,
                text_used=gen_result["text_used"],
                warnings=warnings
            )

        except Exception as exc:
            logger.error(f"Thumbnail generation failed for movie {movie_id}: {exc}", exc_info=True)
            self.repository.update_thumbnail_failed(
                movie_id=movie_id,
                error_payload={
                    "error_message": str(exc),
                    "error_data": {
                        "tmdb_id": tmdb_id,
                        "title": title,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc)
                    },
                    "timeline_event": build_timeline_event(
                        agent=self.agent_name,
                        status=THUMBNAIL_FAILED,
                        message=str(exc),
                        data={"tmdb_id": tmdb_id}
                    )
                }
            )
            return ThumbnailGeneratorResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=THUMBNAIL_FAILED,
                error=str(exc)
            )

    @staticmethod
    def _eligibility_error(movie: dict, force: bool) -> str | None:
        if not movie.get("is_active", True):
            return "Movie is inactive."
        if movie.get("is_locked"):
            return "Movie is already locked."
        if not force and movie.get("next_agent") != NEXT_AGENT_THUMBNAIL_METADATA:
            return "Movie is not queued for thumbnail metadata agent."
        if not force and str(movie.get("shorts_status") or "") != SHORTS_COMPLETED:
            return "YouTube Shorts draft video is not ready yet."
        if not movie.get("draft_video_path") and not movie.get("final_video_path"):
            return "Draft video path is missing."
        if not force and str(movie.get("thumbnail_status") or THUMBNAIL_PENDING) != THUMBNAIL_PENDING:
            return "Thumbnail metadata agent is not pending."
        return None
