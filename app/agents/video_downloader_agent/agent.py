import hashlib
from datetime import datetime, timezone
from pathlib import Path

from app.agents.video_downloader_agent.schema import VideoDownloaderResult, VideoDownloaderRunResponse
from app.config import PROJECT_ROOT, settings
from app.core.agent_status import (
    CURRENT_AGENT_VIDEO_DOWNLOADER,
    NEXT_AGENT_VIDEO_DOWNLOADER,
    OVERALL_WAITING_SOURCE_VIDEO,
    VIDEO_DOWNLOAD_COMPLETED,
    VIDEO_DOWNLOAD_FAILED,
    VOICE_COMPLETED,
)
from app.core.pipeline_utils import build_timeline_event


class VideoDownloaderAgent:
    agent_name = CURRENT_AGENT_VIDEO_DOWNLOADER

    def __init__(self, repository, youtube_downloader_service, video_metadata_service) -> None:
        self.repository = repository
        self.youtube_downloader_service = youtube_downloader_service
        self.video_metadata_service = video_metadata_service

    def run(self, limit: int = 1) -> dict:
        jobs = self.repository.get_pending_video_downloader_jobs(limit=limit)
        return self._run_jobs(jobs=jobs)

    def run_for_movie(self, movie_id: int) -> dict:
        movie = self.repository.get_movie_by_id(movie_id=movie_id)
        if not movie:
            result = VideoDownloaderResult(movie_id=movie_id, status=VIDEO_DOWNLOAD_FAILED, error="Movie not found.")
            return VideoDownloaderRunResponse(processed=0, completed=0, failed=1, results=[result]).model_dump()
        return self._run_jobs(jobs=[movie], allow_unqueued=True)

    def _run_jobs(self, jobs: list[dict], allow_unqueued: bool = False) -> dict:
        results: list[VideoDownloaderResult] = []
        completed = 0
        failed = 0

        for movie in jobs:
            result = self._process_movie(movie=movie, allow_unqueued=allow_unqueued)
            results.append(result)
            if result.status == VIDEO_DOWNLOAD_COMPLETED:
                completed += 1
            else:
                failed += 1

        response = VideoDownloaderRunResponse(
            processed=len(jobs),
            completed=completed,
            failed=failed,
            results=results,
        )
        return response.model_dump()

    def _process_movie(self, movie: dict, allow_unqueued: bool = False) -> VideoDownloaderResult:
        movie_id = int(movie["id"])
        tmdb_id = movie.get("tmdb_id")
        title = movie.get("movie_title")

        eligibility_error = self._eligibility_error(movie=movie, allow_unqueued=allow_unqueued)
        if eligibility_error:
            return VideoDownloaderResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=VIDEO_DOWNLOAD_FAILED,
                error=eligibility_error,
            )

        locked_movie = self.repository.lock_movie_for_agent(movie_id=movie_id, agent_name=self.agent_name)
        if not locked_movie:
            return VideoDownloaderResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=VIDEO_DOWNLOAD_FAILED,
                error="Movie is already locked or inactive.",
            )

        try:
            # Create movie-specific folder inside the master source videos folder
            # storage/source_videos/movie_{movie_id}/
            video_dir = Path(settings.video_source_dir) / f"movie_{movie_id}"
            local_dir_path = PROJECT_ROOT / video_dir
            local_dir_path.mkdir(parents=True, exist_ok=True)
            video_candidates = self._video_candidates(
                locked_movie,
                ignore_failed_candidates=allow_unqueued,
            )
            if not video_candidates:
                raise ValueError("No trailer/teaser candidates found in database.")

            existing_paths = self._existing_source_video_paths(locked_movie)

            downloaded_paths: list[str] = []
            source_video_payloads: list[dict] = []
            candidate_errors: list[str] = []
            failed_candidate_keys = set() if allow_unqueued else self._failed_candidate_keys(locked_movie)

            for candidate in video_candidates:
                candidate_key = str(candidate["candidate_key"])
                youtube_id = candidate.get("youtube_id")
                video_type = candidate["type"]
                file_token = youtube_id or hashlib.md5(candidate_key.encode("utf-8")).hexdigest()[:12]
                output_file_name = f"{video_type}_{file_token}.mp4"
                local_output_path = str(video_dir / output_file_name).replace("\\", "/")
                if local_output_path in existing_paths:
                    continue

                try:
                    downloaded_relative_path = self.youtube_downloader_service.download_video(
                        youtube_url=candidate["url"],
                        output_path=local_output_path,
                    )

                    validation = self.video_metadata_service.validate_16x9_source_video(downloaded_relative_path)
                    if not validation["valid"]:
                        full_path = PROJECT_ROOT / downloaded_relative_path
                        if full_path.exists():
                            full_path.unlink()
                        raise ValueError(
                            f"Video validation failed for {candidate['label']}: "
                            f"{validation.get('message', 'Invalid aspect ratio or format.')}"
                        )

                    metadata = validation["metadata"] or {}
                    uploaded_at = datetime.now(timezone.utc).isoformat()
                    source_video_payloads.append(
                        {
                            "label": candidate["label"],
                            "source_video_path": downloaded_relative_path,
                            "type": video_type,
                            "youtube_id": youtube_id,
                            "aspect_ratio": metadata.get("aspect_ratio", "16:9"),
                            "aspect_ratio_value": metadata.get("aspect_ratio_value"),
                            "width": metadata.get("width"),
                            "height": metadata.get("height"),
                            "duration_seconds": metadata.get("duration_seconds"),
                            "uploaded_at": uploaded_at,
                        }
                    )
                    downloaded_paths.append(downloaded_relative_path)
                    existing_paths.add(downloaded_relative_path)
                except Exception as exc:
                    if not self.youtube_downloader_service.is_transient_error(exc):
                        failed_candidate_keys.add(candidate_key)
                    candidate_errors.append(f"{candidate['label']}: {exc}")
                    continue

            if not downloaded_paths:
                if candidate_errors:
                    raise ValueError(
                        "No valid trailer/teaser video could be downloaded. "
                        + " | ".join(candidate_errors)
                    )
                raise ValueError("Requested trailer/teaser videos are already downloaded for this movie.")

            timeline_event = build_timeline_event(
                agent=self.agent_name,
                status=VIDEO_DOWNLOAD_COMPLETED,
                message=f"Downloaded {len(downloaded_paths)} trailer/teaser video(s) in organized directory.",
                data={
                    "tmdb_id": tmdb_id,
                    "downloaded_paths": downloaded_paths,
                    "warnings": candidate_errors,
                },
            )

            self.repository.update_video_downloader_success(
                movie_id=movie_id,
                download_payload={
                    "primary_source_video_path": downloaded_paths[0],
                    "source_video_payloads": source_video_payloads,
                    "timeline_event": timeline_event,
                },
            )

            return VideoDownloaderResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=VIDEO_DOWNLOAD_COMPLETED,
                local_dir=str(video_dir).replace("\\", "/"),
                downloaded_path=downloaded_paths[0],
            )

        except Exception as exc:
            failure_status = self._mark_waiting_for_manual_source(
                movie_id=movie_id,
                movie=locked_movie,
                exc=exc,
                failed_candidate_keys=failed_candidate_keys,
            )
            return VideoDownloaderResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=failure_status,
                error=str(exc),
            )

    def _eligibility_error(self, movie: dict, allow_unqueued: bool = False) -> str | None:
        if not movie.get("is_active", True):
            return "Movie is inactive."
        if movie.get("is_locked"):
            return "Movie is already locked."
        if movie.get("voice_status") != VOICE_COMPLETED or not movie.get("voice_audio_path"):
            return "Movie voice audio is not ready."
        existing_count = len(self._existing_source_video_paths(movie))
        if existing_count >= max(1, int(settings.video_downloader_max_videos)):
            return "Requested source videos are already available for this movie."
        if movie.get("next_agent") != NEXT_AGENT_VIDEO_DOWNLOADER and not allow_unqueued:
            return "Movie is not queued for video downloader."
        return None

    @staticmethod
    def _existing_source_video_paths(movie: dict) -> set[str]:
        paths: set[str] = set()
        source_videos_json = movie.get("source_videos_json") or []
        if isinstance(source_videos_json, list):
            for item in source_videos_json:
                if not isinstance(item, dict):
                    continue
                path = str(item.get("source_video_path") or "").strip()
                if path and (PROJECT_ROOT / path).exists():
                    paths.add(path)
        source_video_path = str(movie.get("source_video_path") or "").strip()
        if source_video_path and (PROJECT_ROOT / source_video_path).exists():
            paths.add(source_video_path)
        return paths

    def _video_candidates(self, movie: dict, ignore_failed_candidates: bool = False) -> list[dict]:
        trailer_data = movie.get("trailer_data_json") or {}
        blocked_keys = set() if ignore_failed_candidates else self._failed_candidate_keys(movie)
        manual_candidates = self._manual_source_candidates(movie)
        selected_videos = trailer_data.get("selected_videos") if isinstance(trailer_data, dict) else None
        if not isinstance(selected_videos, list) or not selected_videos:
            selected_video = trailer_data.get("selected_video") if isinstance(trailer_data, dict) else None
            selected_videos = [selected_video] if isinstance(selected_video, dict) else []

        candidates: list[dict] = []
        seen_keys: set[str] = set()

        for manual_candidate in manual_candidates:
            candidate_key = str(manual_candidate["url"]).strip()
            if not candidate_key or candidate_key in blocked_keys or candidate_key in seen_keys:
                continue
            seen_keys.add(candidate_key)
            candidates.append(
                {
                    "candidate_key": candidate_key,
                    "youtube_id": None,
                    "url": candidate_key,
                    "type": str(manual_candidate.get("type") or "trailer"),
                    "label": str(manual_candidate.get("label") or f"manual_url_{len(candidates) + 1}"),
                }
            )
            if len(candidates) >= max(1, int(settings.video_downloader_max_videos)):
                return candidates

        for video in selected_videos:
            if not isinstance(video, dict):
                continue
            youtube_id = str(video.get("key") or "").strip()
            video_type = str(video.get("type") or "Trailer").strip().lower()
            if not youtube_id or video_type not in {"trailer", "teaser"}:
                continue
            if youtube_id in blocked_keys:
                continue
            if youtube_id in seen_keys:
                continue
            seen_keys.add(youtube_id)
            label = "official_trailer" if video_type == "trailer" and not candidates else f"{video_type}_{len(candidates) + 1}"
            candidates.append(
                {
                    "candidate_key": youtube_id,
                    "youtube_id": youtube_id,
                    "url": f"https://www.youtube.com/watch?v={youtube_id}",
                    "type": video_type,
                    "label": label,
                }
            )
            if len(candidates) >= max(1, int(settings.video_downloader_max_videos)):
                break

        if not candidates:
            youtube_id = str(movie.get("trailer_youtube_id") or "").strip()
            youtube_url = str(movie.get("trailer_url") or "").strip()
            candidate_key = youtube_id or youtube_url
            if candidate_key and candidate_key not in blocked_keys:
                candidates.append(
                    {
                        "candidate_key": candidate_key,
                        "youtube_id": youtube_id or "downloaded",
                        "url": youtube_url or f"https://www.youtube.com/watch?v={youtube_id}",
                        "type": "trailer",
                        "label": "official_trailer",
                    }
                )

        return candidates

    @staticmethod
    def _failed_candidate_keys(movie: dict) -> set[str]:
        error_data = movie.get("error_data_json") or {}
        if not isinstance(error_data, dict):
            return set()
        failed_ids = error_data.get("failed_candidate_keys")
        if not isinstance(failed_ids, list):
            failed_ids = error_data.get("failed_candidate_youtube_ids")
        if not isinstance(failed_ids, list):
            return set()
        return {
            str(item).strip()
            for item in failed_ids
            if str(item).strip()
        }

    @staticmethod
    def _manual_source_candidates(movie: dict) -> list[dict]:
        error_data = movie.get("error_data_json") or {}
        candidates = error_data.get("manual_source_candidates") if isinstance(error_data, dict) else None
        if not isinstance(candidates, list):
            return []
        return [item for item in candidates if isinstance(item, dict) and str(item.get("url") or "").strip()]

    def _mark_waiting_for_manual_source(
        self,
        movie_id: int,
        movie: dict,
        exc: Exception,
        failed_candidate_keys: set[str] | None = None,
    ) -> str:
        failed_candidate_keys = sorted(failed_candidate_keys or self._failed_candidate_keys(movie))
        error_data = movie.get("error_data_json") or {}
        if not isinstance(error_data, dict):
            error_data = {}
        manual_source_candidates = self._manual_source_candidates(movie)
        transient_failure = self.youtube_downloader_service.is_transient_error(exc)
        attempt_count = int(error_data.get("video_download_attempt_count") or 0) + 1
        max_attempts = max(1, int(settings.video_downloader_max_attempts))
        retry_exhausted = attempt_count >= max_attempts
        updater = self.repository.update_video_downloader_failed if retry_exhausted else self.repository.update_video_downloader_waiting_source
        failure_status = VIDEO_DOWNLOAD_FAILED if retry_exhausted else OVERALL_WAITING_SOURCE_VIDEO
        updater(
            movie_id=movie_id,
            error_payload={
                "error_message": str(exc),
                "error_data": {
                    **error_data,
                    "tmdb_id": movie.get("tmdb_id"),
                    "title": movie.get("movie_title"),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    # Once automatic retries are exhausted, keep the movie in a
                    # recoverable state and explicitly ask for either a retry or
                    # a manually supplied source.  Without this flag the manual
                    # controller can immediately run the same failed job again.
                    "manual_source_url_required": retry_exhausted,
                    "automatic_retry_blocked": retry_exhausted,
                    "youtube_auth_required": transient_failure,
                    "video_download_attempt_count": attempt_count,
                    "video_download_max_attempts": max_attempts,
                    "retry_exhausted": retry_exhausted,
                    "manual_source_candidates": manual_source_candidates,
                    "failed_candidate_keys": failed_candidate_keys if retry_exhausted else [],
                },
                "timeline_event": build_timeline_event(
                    agent=self.agent_name,
                    status=failure_status,
                    message=(
                        f"Video download attempt {attempt_count}/{max_attempts} failed. {exc}"
                        + (
                            " Automatic retries exhausted; retry the download or provide a source video."
                            if retry_exhausted
                            else " Automatic retry queued."
                        )
                    ),
                    data={
                        "tmdb_id": movie.get("tmdb_id"),
                        "attempt_count": attempt_count,
                        "max_attempts": max_attempts,
                        "retry_exhausted": retry_exhausted,
                    },
                ),
            },
        )
        return failure_status
