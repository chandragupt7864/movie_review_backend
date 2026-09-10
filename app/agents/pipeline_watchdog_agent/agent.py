"""
Pipeline Watchdog Agent
-----------------------
Monitors pipeline movies and automatically fixes stale source-video/trailer data.
"""

from app.agents.pipeline_watchdog_agent.schema import WatchdogResult, WatchdogRunResponse
from app.config import PROJECT_ROOT
from app.core.agent_status import (
    NEXT_AGENT_VIDEO_DOWNLOADER,
    OVERALL_WAITING_SOURCE_VIDEO,
    SCENE_WAITING_SOURCE_VIDEO,
    VIDEO_DOWNLOAD_PENDING,
)
from app.core.pipeline_utils import build_timeline_event
from app.core.trailer_video_utils import select_preferred_trailer_videos, video_label

_ALLOWED_VIDEO_TYPES = {"trailer", "teaser"}
WATCHDOG_AGENT_NAME = "PIPELINE_WATCHDOG_AGENT"


class PipelineWatchdogAgent:
    """
    Scans pipeline movies and applies auto-fixes:
      - Removes non-trailer/teaser entries from source_videos_json
      - Removes non-trailer/teaser entries from trailer discovery data
      - Re-queues video downloader when trailer data is present but videos not downloaded
      - Resets scene_status to PENDING when source video exists but scene is waiting
    """

    agent_name = WATCHDOG_AGENT_NAME

    def __init__(self, repository) -> None:
        self.repository = repository

    def run(self, limit: int = 20) -> dict:
        """Scan and fix pipeline movies that need source/trailer cleanup."""
        movies = self.repository.get_watchdog_candidates(limit=limit)
        return self._run_jobs(jobs=movies)

    def run_for_movie(self, movie_id: int) -> dict:
        """Scan and fix a specific movie."""
        movie = self.repository.get_movie_by_id(movie_id=movie_id)
        if not movie:
            result = WatchdogResult(movie_id=movie_id, action="failed", details="Movie not found.")
            return self._response(results=[result]).model_dump()
        return self._run_jobs(jobs=[movie])

    def _run_jobs(self, jobs: list[dict]) -> dict:
        results: list[WatchdogResult] = []
        for movie in jobs:
            results.append(self._process_movie(movie))
        return self._response(results=results).model_dump()

    def _process_movie(self, movie: dict) -> WatchdogResult:
        movie_id = int(movie["id"])
        tmdb_id = movie.get("tmdb_id")
        title = movie.get("movie_title")
        fixes_applied: list[str] = []

        if movie.get("is_locked") or movie.get("current_agent"):
            return WatchdogResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                action="skipped",
                details="Movie is locked or being processed by another agent.",
            )

        try:
            cleaned_trailer_data = self._clean_trailer_discovery_data(movie_id=movie_id, movie=movie)
            if cleaned_trailer_data["removed"]:
                fixes_applied.append(
                    f"Removed {len(cleaned_trailer_data['removed'])} invalid trailer discovery entry(ies): "
                    + ", ".join(cleaned_trailer_data["removed"])
                )

            movie = self.repository.get_movie_by_id(movie_id=movie_id) or movie

            cleaned_sources = self._clean_source_videos(movie_id=movie_id, movie=movie)
            if cleaned_sources["removed"]:
                fixes_applied.append(
                    f"Removed {len(cleaned_sources['removed'])} non-trailer/teaser entry(ies) from source_videos_json: "
                    + ", ".join(cleaned_sources["removed"])
                )

            movie = self.repository.get_movie_by_id(movie_id=movie_id) or movie
            valid_source_paths = self._get_valid_source_paths(movie)

            if valid_source_paths:
                if self._maybe_reset_scene_selection(movie_id=movie_id, movie=movie):
                    fixes_applied.append("Reset scene_status to PENDING because valid source video found.")

                if fixes_applied:
                    return WatchdogResult(
                        movie_id=movie_id,
                        tmdb_id=tmdb_id,
                        title=title,
                        action="fixed",
                        details=f"Applied {len(fixes_applied)} fix(es).",
                        fixes_applied=fixes_applied,
                    )
                return WatchdogResult(
                    movie_id=movie_id,
                    tmdb_id=tmdb_id,
                    title=title,
                    action="skipped",
                    details="Source video already valid, no action needed.",
                )

            if self._maybe_requeue_video_downloader(movie_id=movie_id, movie=movie):
                fixes_applied.append(
                    "Re-queued Video Downloader Agent: trailer data available, resetting download state."
                )
                return WatchdogResult(
                    movie_id=movie_id,
                    tmdb_id=tmdb_id,
                    title=title,
                    action="requeued",
                    details=f"Applied {len(fixes_applied)} fix(es).",
                    fixes_applied=fixes_applied,
                )

            detail = "No valid source video and no downloadable trailer found. Manual intervention required."
            if fixes_applied:
                detail = (
                    f"Partial fix applied ({len(fixes_applied)}), but still no valid source video. "
                    "Manual intervention required."
                )
            return WatchdogResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                action="fixed" if fixes_applied else "skipped",
                details=detail,
                fixes_applied=fixes_applied,
            )
        except Exception as exc:
            return WatchdogResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                action="failed",
                details=f"Watchdog error: {exc}",
                fixes_applied=fixes_applied,
            )

    def _clean_trailer_discovery_data(self, movie_id: int, movie: dict) -> dict:
        """
        Curate trailer_data_json so downstream logic only sees a few genuine
        trailer/teaser uploads instead of TMDB's full promotional video list.
        """
        trailer_data = movie.get("trailer_data_json") or {}
        if not isinstance(trailer_data, dict) or not trailer_data:
            return {"removed": [], "trailer_data": trailer_data}

        cleaned_data = dict(trailer_data)
        tmdb_videos_response = cleaned_data.get("tmdb_videos_response")
        tmdb_results = tmdb_videos_response.get("results") if isinstance(tmdb_videos_response, dict) else []
        selected_videos = cleaned_data.get("selected_videos")
        selected_video = cleaned_data.get("selected_video")

        discovery_videos: list[object] = []
        if isinstance(tmdb_results, list):
            discovery_videos.extend(tmdb_results)
        if isinstance(selected_videos, list):
            discovery_videos.extend(selected_videos)
        if isinstance(selected_video, dict):
            discovery_videos.append(selected_video)

        cleaned_selected = select_preferred_trailer_videos(discovery_videos)
        cleaned_data["selected_videos"] = cleaned_selected
        cleaned_data["selected_video"] = cleaned_selected[0] if cleaned_selected else None
        if isinstance(tmdb_videos_response, dict):
            cleaned_data["tmdb_videos_response"] = {
                **tmdb_videos_response,
                "results": cleaned_selected,
            }

        old_selected = selected_videos if isinstance(selected_videos, list) else []
        old_results = tmdb_results if isinstance(tmdb_results, list) else []
        primary_video = cleaned_selected[0] if cleaned_selected else {}
        scalar_matches = (
            str(movie.get("trailer_youtube_id") or "").strip() == str(primary_video.get("key") or "").strip()
            and str(movie.get("trailer_title") or "").strip() == str(primary_video.get("name") or "").strip()
        )
        if old_selected == cleaned_selected and old_results == cleaned_selected and scalar_matches:
            return {"removed": [], "trailer_data": cleaned_data}

        kept_keys = {str(item.get("key") or "").strip() for item in cleaned_selected}
        removed: list[str] = []
        removed_keys: set[str] = set()
        for item in discovery_videos:
            key = str(item.get("key") or "").strip() if isinstance(item, dict) else ""
            identity = key or video_label(item)
            if key in kept_keys or identity in removed_keys:
                continue
            removed_keys.add(identity)
            removed.append(video_label(item))

        if not removed:
            removed.append("stale scalar trailer metadata")

        self.repository.update_trailer_data_json(
            movie_id=movie_id,
            trailer_data=cleaned_data,
            removed_labels=removed,
            timeline_event=build_timeline_event(
                agent=self.agent_name,
                status="WATCHDOG_TRAILER_DATA_CLEANED",
                message=(
                    f"Removed {len(removed)} noisy trailer discovery entry(ies). "
                    "Only curated trailer/teaser videos are kept."
                ),
                data={"tmdb_id": movie.get("tmdb_id"), "removed": removed},
            ),
        )
        return {"removed": removed, "trailer_data": cleaned_data}

    def _clean_source_videos(self, movie_id: int, movie: dict) -> dict:
        """
        Remove non-trailer/teaser entries from source_videos_json and keep only
        existing files.
        """
        source_videos_json = movie.get("source_videos_json") or []
        if not isinstance(source_videos_json, list) or not source_videos_json:
            return {"kept": [], "removed": []}

        kept: list[dict] = []
        removed: list[str] = []
        seen_paths: set[str] = set()

        for item in source_videos_json:
            if not isinstance(item, dict):
                continue
            video_type = str(item.get("type") or "").strip().lower()
            label = str(item.get("label") or item.get("source_video_path") or "unknown")

            if video_type not in _ALLOWED_VIDEO_TYPES:
                removed.append(f"{label} (type={video_type or 'unknown'})")
                continue

            path_str = str(item.get("source_video_path") or "").strip()
            if not path_str:
                removed.append(f"{label} (no path)")
                continue

            normalized_path = path_str.replace("\\", "/").lower()
            if normalized_path in seen_paths:
                removed.append(f"{label} (duplicate path: {path_str})")
                continue

            full_path = PROJECT_ROOT / path_str
            if not full_path.exists():
                removed.append(f"{label} (file missing: {path_str})")
                continue

            seen_paths.add(normalized_path)
            kept.append(item)

        if not removed:
            return {"kept": kept, "removed": []}

        self.repository.update_source_videos_json(
            movie_id=movie_id,
            kept_videos=kept,
            removed_labels=removed,
            timeline_event=build_timeline_event(
                agent=self.agent_name,
                status="WATCHDOG_CLEANED",
                message=(
                    f"Removed {len(removed)} non-trailer/teaser entry(ies). "
                    f"Kept {len(kept)} valid trailer/teaser(s)."
                ),
                data={
                    "tmdb_id": movie.get("tmdb_id"),
                    "removed": removed,
                    "kept_count": len(kept),
                },
            ),
        )
        return {"kept": kept, "removed": removed}

    def _maybe_reset_scene_selection(self, movie_id: int, movie: dict) -> bool:
        scene_status = str(movie.get("scene_status") or "")
        if scene_status != SCENE_WAITING_SOURCE_VIDEO:
            return False

        self.repository.reset_scene_to_pending(
            movie_id=movie_id,
            timeline_event=build_timeline_event(
                agent=self.agent_name,
                status="WATCHDOG_SCENE_RESET",
                message="Scene status reset to PENDING because a valid source video was found.",
                data={"tmdb_id": movie.get("tmdb_id")},
            ),
        )
        return True

    def _maybe_requeue_video_downloader(self, movie_id: int, movie: dict) -> bool:
        if str(movie.get("next_agent") or "") != NEXT_AGENT_VIDEO_DOWNLOADER:
            return False

        trailer_data = movie.get("trailer_data_json") or {}
        if not isinstance(trailer_data, dict):
            return False

        error_data = movie.get("error_data_json") or {}
        if isinstance(error_data, dict) and error_data.get("automatic_retry_blocked"):
            return False
        manual_required = isinstance(error_data, dict) and bool(error_data.get("manual_source_url_required"))
        already_queued = (
            str(movie.get("video_download_status") or "") == VIDEO_DOWNLOAD_PENDING
            and str(movie.get("overall_status") or "") == OVERALL_WAITING_SOURCE_VIDEO
        )
        if already_queued and not manual_required:
            return False

        if not self._has_downloadable_trailer_candidates(movie=movie, trailer_data=trailer_data):
            return False

        self.repository.requeue_for_video_downloader(
            movie_id=movie_id,
            timeline_event=build_timeline_event(
                agent=self.agent_name,
                status="WATCHDOG_REQUEUED",
                message="Re-queued for Video Downloader because trailer data is available.",
                data={"tmdb_id": movie.get("tmdb_id")},
            ),
        )
        return True

    @staticmethod
    def _get_valid_source_paths(movie: dict) -> list[str]:
        valid: list[str] = []

        primary = str(movie.get("source_video_path") or "").strip()
        if primary and (PROJECT_ROOT / primary).exists():
            valid.append(primary)

        for item in (movie.get("source_videos_json") or []):
            if not isinstance(item, dict):
                continue
            video_type = str(item.get("type") or "").strip().lower()
            if video_type not in _ALLOWED_VIDEO_TYPES:
                continue
            path_str = str(item.get("source_video_path") or "").strip()
            if path_str and (PROJECT_ROOT / path_str).exists() and path_str not in valid:
                valid.append(path_str)

        return valid

    @staticmethod
    def _has_downloadable_trailer_candidates(movie: dict, trailer_data: dict) -> bool:
        error_data = movie.get("error_data_json") or {}
        failed_keys: set[str] = set()
        if isinstance(error_data, dict):
            failed_keys_list = (
                error_data.get("failed_candidate_keys")
                or error_data.get("failed_candidate_youtube_ids")
                or []
            )
            if isinstance(failed_keys_list, list):
                failed_keys = {str(key).strip() for key in failed_keys_list if str(key).strip()}

        selected_videos = trailer_data.get("selected_videos")
        if isinstance(selected_videos, list):
            for video in selected_videos:
                if not isinstance(video, dict):
                    continue
                key = str(video.get("key") or "").strip()
                video_type = str(video.get("type") or "").strip().lower()
                if key and video_type in _ALLOWED_VIDEO_TYPES and key not in failed_keys:
                    return True

        selected_video = trailer_data.get("selected_video")
        if isinstance(selected_video, dict):
            key = str(selected_video.get("key") or "").strip()
            video_type = str(selected_video.get("type") or "").strip().lower()
            if key and video_type in _ALLOWED_VIDEO_TYPES and key not in failed_keys:
                return True

        youtube_id = str(movie.get("trailer_youtube_id") or "").strip()
        return bool(youtube_id and youtube_id not in failed_keys)

    @staticmethod
    def _response(results: list[WatchdogResult]) -> WatchdogRunResponse:
        return WatchdogRunResponse(
            processed=len(results),
            fixed=sum(1 for result in results if result.action == "fixed"),
            requeued=sum(1 for result in results if result.action == "requeued"),
            skipped=sum(1 for result in results if result.action == "skipped"),
            failed=sum(1 for result in results if result.action == "failed"),
            results=results,
        )
