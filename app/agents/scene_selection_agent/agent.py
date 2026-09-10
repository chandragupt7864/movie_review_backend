import json
from pathlib import Path

from app.agents.scene_selection_agent.schema import SceneSelectionResult, SceneSelectionRunResponse
from app.config import PROJECT_ROOT, settings
from app.core.agent_status import (
    CURRENT_AGENT_SCENE_SELECTION,
    NEXT_AGENT_SCENE_SELECTION,
    SCENE_COMPLETED,
    SCENE_FAILED,
    SCENE_WAITING_SOURCE_VIDEO,
    SCENE_WAITING_VOICE_AUDIO,
    VOICE_COMPLETED,
)
from app.core.pipeline_utils import build_timeline_event


class SceneSelectionAgent:
    agent_name = CURRENT_AGENT_SCENE_SELECTION

    def __init__(
        self,
        repository,
        audio_metadata_service,
        video_metadata_service,
        gemini_video_service,
        visual_scene_selection_service=None,
    ) -> None:
        self.repository = repository
        self.audio_metadata_service = audio_metadata_service
        self.video_metadata_service = video_metadata_service
        self.gemini_video_service = gemini_video_service
        self.visual_scene_selection_service = visual_scene_selection_service

    def run(self, limit: int = 1) -> dict:
        jobs = self.repository.get_pending_scene_jobs(limit=limit)
        return self._run_jobs(jobs=jobs, force=False)

    def run_for_movie(self, movie_id: int, force: bool = False) -> dict:
        movie = self.repository.get_movie_by_id(movie_id=movie_id)
        if not movie:
            result = SceneSelectionResult(movie_id=movie_id, status=SCENE_FAILED, error="Movie not found.")
            return self._response(results=[result]).model_dump()
        return self._run_jobs(jobs=[movie], force=force)

    def _run_jobs(self, jobs: list[dict], force: bool) -> dict:
        results: list[SceneSelectionResult] = []

        for movie in jobs:
            results.append(self._process_movie(movie=movie, force=force))

        return self._response(results=results).model_dump()

    def _response(self, results: list[SceneSelectionResult]) -> SceneSelectionRunResponse:
        completed = sum(1 for result in results if result.status == SCENE_COMPLETED)
        failed = sum(1 for result in results if result.status == SCENE_FAILED)
        waiting_source_video = sum(1 for result in results if result.status == SCENE_WAITING_SOURCE_VIDEO)
        waiting_voice_audio = sum(1 for result in results if result.status == SCENE_WAITING_VOICE_AUDIO)
        return SceneSelectionRunResponse(
            processed=len(results),
            completed=completed,
            failed=failed,
            waiting_source_video=waiting_source_video,
            waiting_voice_audio=waiting_voice_audio,
            results=results,
        )

    def _process_movie(self, movie: dict, force: bool) -> SceneSelectionResult:
        movie_id = int(movie["id"])
        tmdb_id = movie.get("tmdb_id")
        title = movie.get("movie_title")

        eligibility_error = self._eligibility_error(movie=movie, force=force)
        if eligibility_error:
            return SceneSelectionResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=SCENE_FAILED,
                error=eligibility_error,
            )

        if movie.get("voice_status") != VOICE_COMPLETED or not movie.get("voice_audio_path"):
            self._mark_waiting_voice(movie_id=movie_id, movie=movie)
            return SceneSelectionResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=SCENE_WAITING_VOICE_AUDIO,
                error="Voice audio is missing. Upload MP3 audio before scene selection.",
            )

        source_videos = self._build_source_videos(movie=movie)
        valid_source_videos, source_errors = self._validate_source_videos(source_videos)
        if not valid_source_videos:
            self._mark_waiting_source(movie_id=movie_id, movie=movie, source_errors=source_errors)
            return SceneSelectionResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=SCENE_WAITING_SOURCE_VIDEO,
                error="Source video is missing. Upload 16:9 trailer/teaser video before scene selection.",
            )

        locked_movie = self.repository.lock_movie_for_agent(movie_id=movie_id, agent_name=self.agent_name)
        if not locked_movie:
            return SceneSelectionResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=SCENE_FAILED,
                error="Movie is already locked or inactive.",
            )

        try:
            voice_duration_seconds = self.audio_metadata_service.get_audio_duration_seconds(str(locked_movie["voice_audio_path"]))
            extra_visual_seconds = self._extra_visual_seconds_after_voice()
            target_duration_seconds = round(float(voice_duration_seconds) + extra_visual_seconds, 3)
            movie_context = self._movie_context(movie=locked_movie, source_videos=valid_source_videos)
            selection_method = "visual_fallback"
            cached_scene_plan = self._load_cached_scene_plan(
                movie_id=movie_id,
                source_videos=valid_source_videos,
                voice_duration_seconds=voice_duration_seconds,
                target_duration_seconds=target_duration_seconds,
                movie_context=movie_context,
            )
            if cached_scene_plan:
                scene_plan = cached_scene_plan
                selection_method = "gemini_semantic_cache"
            elif settings.scene_selection_prefer_visual_fallback and self.visual_scene_selection_service:
                scene_plan = self.visual_scene_selection_service.build_scene_plan(
                    source_videos=valid_source_videos,
                    movie_context=movie_context,
                    voice_duration_seconds=voice_duration_seconds,
                    target_duration_seconds=target_duration_seconds,
                    extra_visual_seconds_after_voice=extra_visual_seconds,
                )
                warnings = list(scene_plan.get("warnings") or [])
                warnings.append("Visual fallback was preferred by configuration.")
                scene_plan["warnings"] = warnings
            else:
                try:
                    scene_plan = self.gemini_video_service.analyze_video_for_scenes(
                        source_videos=valid_source_videos,
                        movie_context=movie_context,
                        voice_duration_seconds=voice_duration_seconds,
                        target_duration_seconds=target_duration_seconds,
                        extra_visual_seconds_after_voice=extra_visual_seconds,
                    )
                    selection_method = "gemini_semantic"
                except Exception as gemini_exc:
                    if not self.visual_scene_selection_service:
                        raise
                    semantic_guard = getattr(
                        self.gemini_video_service,
                        "requires_semantic_selection",
                        lambda _context: False,
                    )
                    if semantic_guard(movie_context):
                        raise RuntimeError(
                            "Semantic scene selection is required for this movie's named visual subjects; "
                            f"Gemini analysis failed and motion-only fallback was blocked: {gemini_exc}"
                        ) from gemini_exc
                    scene_plan = self.visual_scene_selection_service.build_scene_plan(
                        source_videos=valid_source_videos,
                        movie_context=movie_context,
                        voice_duration_seconds=voice_duration_seconds,
                        target_duration_seconds=target_duration_seconds,
                        extra_visual_seconds_after_voice=extra_visual_seconds,
                    )
                    warnings = list(scene_plan.get("warnings") or [])
                    warnings.append(f"Gemini fallback reason: {gemini_exc}")
                    scene_plan["warnings"] = warnings
            if source_errors:
                warnings = list(scene_plan.get("warnings") or [])
                warnings.extend(source_errors)
                scene_plan["warnings"] = warnings

            if selection_method == "gemini_semantic":
                self._save_scene_plan_cache(
                    movie_id=movie_id,
                    source_videos=valid_source_videos,
                    voice_duration_seconds=voice_duration_seconds,
                    target_duration_seconds=target_duration_seconds,
                    scene_plan=scene_plan,
                )

            self.repository.update_scene_success(
                movie_id=movie_id,
                scene_payload={
                    "scene_data": scene_plan,
                    "timeline_event": build_timeline_event(
                        agent=self.agent_name,
                        status=SCENE_COMPLETED,
                        message=f"Scene selection completed using {selection_method}",
                        data={
                            "tmdb_id": tmdb_id,
                            "voice_duration_seconds": round(voice_duration_seconds, 3),
                            "target_duration_seconds": target_duration_seconds,
                            "source_videos_used": len(scene_plan.get("source_videos_used") or []),
                            "selection_method": selection_method,
                        },
                    ),
                },
            )
            self._clear_scene_plan_cache(movie_id)
            return SceneSelectionResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=SCENE_COMPLETED,
                target_duration_seconds=scene_plan.get("target_duration_seconds"),
                estimated_total_duration_seconds=scene_plan.get("estimated_total_duration_seconds"),
                scenes_selected=len(scene_plan.get("scenes") or []),
            )
        except Exception as exc:
            self._mark_failed(movie_id=movie_id, movie=locked_movie, exc=exc)
            return SceneSelectionResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=SCENE_FAILED,
                error=str(exc),
            )

    def _eligibility_error(self, movie: dict, force: bool) -> str | None:
        if not movie.get("is_active", True):
            return "Movie is inactive."
        if movie.get("is_locked"):
            return "Movie is already locked."
        if not force and movie.get("next_agent") != NEXT_AGENT_SCENE_SELECTION:
            return "Movie is not queued for scene selection."
        if not force and str(movie.get("scene_status") or "") not in {"PENDING", "WAITING_SOURCE_VIDEO", "WAITING_VOICE_AUDIO"}:
            return "Movie scene selection is not pending."
        return None

    def _build_source_videos(self, movie: dict) -> list[dict]:
        candidates: list[dict] = []
        seen_paths: set[str] = set()

        source_video_path = movie.get("source_video_path")
        if source_video_path:
            normalized = self._normalize_source_video(
                {
                    "label": "primary_source_video",
                    "source_video_path": str(source_video_path),
                    "type": "trailer",
                }
            )
            seen_paths.add(normalized["source_video_path"])
            candidates.append(normalized)

        source_videos_json = movie.get("source_videos_json") or []
        if isinstance(source_videos_json, list):
            for item in source_videos_json:
                if not isinstance(item, dict):
                    continue
                normalized = self._normalize_source_video(item)
                if normalized["source_video_path"] in seen_paths:
                    continue
                seen_paths.add(normalized["source_video_path"])
                candidates.append(normalized)

        return candidates

    def _validate_source_videos(self, source_videos: list[dict]) -> tuple[list[dict], list[str]]:
        valid_source_videos: list[dict] = []
        errors: list[str] = []

        for source_video in source_videos:
            result = self.video_metadata_service.validate_16x9_source_video(source_video["source_video_path"])
            if not result["valid"]:
                errors.append(f"{source_video['source_video_path']}: {result['message']}")
                continue
            metadata = result["metadata"] or {}
            valid_source_videos.append({**source_video, **metadata})

        return valid_source_videos, errors

    def _movie_context(self, movie: dict, source_videos: list[dict]) -> dict:
        script_data = movie.get("script_data_json") or {}
        movie_data = movie.get("movie_data_json") or {}
        genres = movie.get("target_genres_json") if isinstance(movie.get("target_genres_json"), list) else []
        return {
            "movie_id": movie.get("id"),
            "tmdb_id": movie.get("tmdb_id"),
            "movie_title": movie.get("movie_title"),
            "release_date": str(movie.get("release_date") or ""),
            "genres": genres,
            "overview": movie_data.get("overview") if isinstance(movie_data, dict) else None,
            "final_script": movie.get("final_script"),
            "elevenlabs_script": script_data.get("elevenlabs_script") if isinstance(script_data, dict) else None,
            "script_title": script_data.get("title") if isinstance(script_data, dict) else None,
            "script_description": script_data.get("description") if isinstance(script_data, dict) else None,
            "source_videos_count": len(source_videos),
            "trailer_url": movie.get("trailer_url"),
            "trailer_title": movie.get("trailer_title"),
        }

    @staticmethod
    def _normalize_source_video(source_video: dict) -> dict:
        return {
            "label": str(source_video.get("label") or "official_trailer"),
            "source_video_path": str(source_video.get("source_video_path") or ""),
            "type": str(source_video.get("type") or "trailer"),
            "aspect_ratio": str(source_video.get("aspect_ratio") or "16:9"),
        }

    @staticmethod
    def _extra_visual_seconds_after_voice() -> float:
        configured = float(settings.scene_extra_seconds_after_voice)
        return round(
            max(settings.scene_extra_seconds_min, min(configured, settings.scene_extra_seconds_max)),
            3,
        )

    @staticmethod
    def _scene_plan_cache_path(movie_id: int) -> Path:
        return PROJECT_ROOT / "storage" / "scene_plans" / f"movie_{movie_id}.json"

    @staticmethod
    def _source_fingerprint(source_videos: list[dict]) -> list[dict]:
        fingerprints = []
        for source in source_videos:
            path = Path(str(source["source_video_path"]))
            resolved = path if path.is_absolute() else PROJECT_ROOT / path
            stat = resolved.stat() if resolved.exists() else None
            fingerprints.append(
                {
                    "path": str(source["source_video_path"]),
                    "size": stat.st_size if stat else 0,
                    "mtime_ns": stat.st_mtime_ns if stat else 0,
                }
            )
        return fingerprints

    def _save_scene_plan_cache(
        self,
        movie_id: int,
        source_videos: list[dict],
        voice_duration_seconds: float,
        target_duration_seconds: float,
        scene_plan: dict,
    ) -> None:
        cache_path = self._scene_plan_cache_path(movie_id)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {
                    "voice_duration_seconds": round(float(voice_duration_seconds), 3),
                    "target_duration_seconds": round(float(target_duration_seconds), 3),
                    "source_fingerprint": self._source_fingerprint(source_videos),
                    "scene_plan": scene_plan,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def _load_cached_scene_plan(
        self,
        movie_id: int,
        source_videos: list[dict],
        voice_duration_seconds: float,
        target_duration_seconds: float,
        movie_context: dict,
    ) -> dict | None:
        cache_path = self._scene_plan_cache_path(movie_id)
        if not cache_path.exists():
            return None
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if payload.get("source_fingerprint") != self._source_fingerprint(source_videos):
                return None
            if abs(float(payload.get("voice_duration_seconds")) - float(voice_duration_seconds)) > 0.01:
                return None
            if abs(float(payload.get("target_duration_seconds")) - float(target_duration_seconds)) > 0.01:
                return None
            validation = self.gemini_video_service.validate_scene_plan(
                scene_plan=payload.get("scene_plan"),
                source_videos=source_videos,
                voice_duration_seconds=voice_duration_seconds,
                target_duration_seconds=target_duration_seconds,
                movie_context=movie_context,
            )
            return validation.get("scene_plan") if validation.get("valid") else None
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _clear_scene_plan_cache(self, movie_id: int) -> None:
        self._scene_plan_cache_path(movie_id).unlink(missing_ok=True)

    def _mark_waiting_source(self, movie_id: int, movie: dict, source_errors: list[str]) -> None:
        self.repository.update_scene_waiting_source_video(
            movie_id=movie_id,
            error_payload={
                "error_message": "Source video is missing. Upload 16:9 trailer/teaser video before scene selection.",
                "error_data": {
                    "tmdb_id": movie.get("tmdb_id"),
                    "title": movie.get("movie_title"),
                    "source_errors": source_errors,
                },
                "timeline_event": build_timeline_event(
                    agent=self.agent_name,
                    status=SCENE_WAITING_SOURCE_VIDEO,
                    message="Source video is missing. Upload 16:9 trailer/teaser video before scene selection.",
                    data={"tmdb_id": movie.get("tmdb_id"), "source_errors": source_errors},
                ),
            },
        )

    def _mark_waiting_voice(self, movie_id: int, movie: dict) -> None:
        self.repository.update_scene_waiting_voice_audio(
            movie_id=movie_id,
            error_payload={
                "error_message": "Voice audio is missing. Upload MP3 audio before scene selection.",
                "error_data": {
                    "tmdb_id": movie.get("tmdb_id"),
                    "title": movie.get("movie_title"),
                },
                "timeline_event": build_timeline_event(
                    agent=self.agent_name,
                    status=SCENE_WAITING_VOICE_AUDIO,
                    message="Voice audio is missing. Upload MP3 audio before scene selection.",
                    data={"tmdb_id": movie.get("tmdb_id")},
                ),
            },
        )

    def _mark_failed(self, movie_id: int, movie: dict, exc: Exception) -> None:
        self.repository.update_scene_failed(
            movie_id=movie_id,
            error_payload={
                "error_message": str(exc),
                "error_data": {
                    "tmdb_id": movie.get("tmdb_id"),
                    "title": movie.get("movie_title"),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
                "timeline_event": build_timeline_event(
                    agent=self.agent_name,
                    status=SCENE_FAILED,
                    message=str(exc),
                    data={"tmdb_id": movie.get("tmdb_id")},
                ),
            },
        )
