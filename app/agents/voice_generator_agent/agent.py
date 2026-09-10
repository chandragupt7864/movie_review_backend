from pathlib import Path

from app.agents.voice_generator_agent.schema import VoiceGeneratorResult, VoiceGeneratorRunResponse
from app.config import PROJECT_ROOT, settings
from app.core.agent_status import (
    CURRENT_AGENT_VOICE_GENERATOR,
    NEXT_AGENT_SCENE_SELECTION,
    NEXT_AGENT_VOICE_GENERATOR,
    NEXT_AGENT_VIDEO_DOWNLOADER,
    OVERALL_VOICE_READY,
    OVERALL_WAITING_SOURCE_VIDEO,
    SCRIPT_COMPLETED,
    VOICE_COMPLETED,
    VOICE_FAILED,
    VOICE_PENDING,
)
from app.core.pipeline_utils import build_timeline_event


class VoiceGeneratorAgent:
    agent_name = CURRENT_AGENT_VOICE_GENERATOR

    def __init__(self, tts_service, repository, storage_service=None) -> None:
        self.tts_service = tts_service
        self.repository = repository
        self.storage_service = storage_service

    def run(self, limit: int, force: bool = False) -> dict:
        jobs = self.repository.get_pending_voice_jobs(
            limit=limit,
            require_approval=settings.voice_require_approval and not force,
        )
        return self._run_jobs(jobs=jobs, force=force)

    def run_for_movie(self, movie_id: int, force: bool = False) -> dict:
        movie = self.repository.get_movie_by_id(movie_id=movie_id)
        if not movie:
            result = VoiceGeneratorResult(movie_id=movie_id, status=VOICE_FAILED, error="Movie not found.")
            return VoiceGeneratorRunResponse(processed=0, completed=0, failed=1, results=[result]).model_dump()

        eligibility_error = self._eligibility_error(movie=movie, force=force)
        if eligibility_error:
            result = VoiceGeneratorResult(
                movie_id=movie_id,
                tmdb_id=movie.get("tmdb_id"),
                title=movie.get("movie_title"),
                status=VOICE_FAILED,
                error=eligibility_error,
            )
            return VoiceGeneratorRunResponse(processed=0, completed=0, failed=1, results=[result]).model_dump()

        return self._run_jobs(jobs=[movie], force=force)

    def _run_jobs(self, jobs: list[dict], force: bool) -> dict:
        results: list[VoiceGeneratorResult] = []
        completed = 0
        failed = 0

        for job in jobs:
            result = self._process_movie(movie=job, force=force)
            results.append(result)
            if result.status == VOICE_COMPLETED:
                completed += 1
            else:
                failed += 1

        response = VoiceGeneratorRunResponse(
            processed=len(jobs),
            completed=completed,
            failed=failed,
            results=results,
        )
        return response.model_dump()

    def _process_movie(self, movie: dict, force: bool) -> VoiceGeneratorResult:
        movie_id = int(movie["id"])
        tmdb_id = movie.get("tmdb_id")
        title = movie.get("movie_title")

        eligibility_error = self._eligibility_error(movie=movie, force=force)
        if eligibility_error:
            return VoiceGeneratorResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=VOICE_FAILED,
                error=eligibility_error,
            )

        locked_movie = self.repository.lock_movie_for_agent(movie_id=movie_id, agent_name=self.agent_name)
        if not locked_movie:
            return VoiceGeneratorResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=VOICE_FAILED,
                error="Movie is already locked or inactive.",
            )

        try:
            raw_text = self._select_voice_script(locked_movie)
            cleaned_text = self.tts_service.clean_voice_text(raw_text)
            if not cleaned_text:
                raise ValueError("Voice script is empty.")

            script_hash = self.tts_service.get_script_hash(
                text=cleaned_text,
                voice_id=self.tts_service.voice_id,
                model_id=self.tts_service.model_id,
            )
            audio_path = self._audio_path(movie_id=movie_id, script_hash=script_hash)
            storage_path = self._storage_path(movie_id=movie_id, script_hash=script_hash)
            voice_data = self._generate_or_reuse_audio(
                text=cleaned_text,
                local_audio_path=audio_path,
                storage_path=storage_path,
                script_hash=script_hash,
            )

            self.repository.update_voice_success(
                movie_id=movie_id,
                voice_payload={
                    "audio_path": voice_data["voice_audio_path"],
                    "voice_data": voice_data,
                    "next_agent": self._next_agent_after_voice(),
                    "overall_status": self._overall_status_after_voice(),
                    "timeline_event": build_timeline_event(
                        agent=self.agent_name,
                        status=VOICE_COMPLETED,
                        message="Voice audio generated successfully using ElevenLabs",
                        data={
                            "tmdb_id": tmdb_id,
                            "voice_id": voice_data["voice_id"],
                            "script_hash": voice_data["script_hash"],
                            "cached": voice_data["cached"],
                            "source_video_mode": settings.source_video_mode,
                        },
                    ),
                },
            )
            return VoiceGeneratorResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=VOICE_COMPLETED,
                audio_path=voice_data["voice_audio_path"],
                cached=voice_data["cached"],
            )
        except Exception as exc:
            self._mark_failed(movie_id=movie_id, movie=locked_movie, exc=exc)
            return VoiceGeneratorResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=VOICE_FAILED,
                error=str(exc),
            )

    def _eligibility_error(self, movie: dict, force: bool) -> str | None:
        if not movie.get("is_active", True):
            return "Movie is inactive."
        if movie.get("script_status") != SCRIPT_COMPLETED:
            return "Movie script is not completed."
        if movie.get("voice_status") != VOICE_PENDING:
            return "Movie voice generation is not pending."
        if movie.get("next_agent") != NEXT_AGENT_VOICE_GENERATOR:
            return "Movie is not queued for voice generation."
        if not movie.get("final_script"):
            return "Movie final script is empty."
        if settings.voice_require_approval and not force and not movie.get("is_approved_for_processing"):
            return "Movie is not approved for voice generation."
        return None

    @staticmethod
    def _select_voice_script(movie: dict) -> str:
        script_data = movie.get("script_data_json") or {}
        if isinstance(script_data, dict) and script_data.get("elevenlabs_script"):
            return str(script_data["elevenlabs_script"])
        return str(movie.get("final_script") or "")

    @staticmethod
    def _audio_path(movie_id: int, script_hash: str) -> str:
        output_dir = Path(settings.audio_output_dir)
        if output_dir.is_absolute():
            path = output_dir / f"movie_{movie_id}_{script_hash}.mp3"
            try:
                return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
            except ValueError:
                return str(path)
        return str(output_dir / f"movie_{movie_id}_{script_hash}.mp3").replace("\\", "/")

    @staticmethod
    def _storage_path(movie_id: int, script_hash: str) -> str:
        return f"audio/movie_{movie_id}_{script_hash}.mp3"

    def _generate_or_reuse_audio(self, text: str, local_audio_path: str, storage_path: str, script_hash: str) -> dict:
        if settings.upload_audio_to_supabase and self.storage_service:
            voice_audio_path = self._voice_audio_path(storage_path=storage_path)
            if self.storage_service.file_exists(storage_path=storage_path):
                return self._voice_metadata(
                    local_audio_path=local_audio_path,
                    storage_path=storage_path,
                    script_hash=script_hash,
                    cached=True,
                    uploaded_to_supabase=True,
                    voice_audio_path=voice_audio_path,
                )

        voice_data = self.tts_service.generate_audio(text=text, output_path=local_audio_path)
        voice_data = self._voice_metadata(
            local_audio_path=local_audio_path,
            storage_path=None,
            script_hash=voice_data["script_hash"],
            cached=voice_data["cached"],
            uploaded_to_supabase=False,
            voice_audio_path=local_audio_path,
            cleaned_text_length=voice_data.get("cleaned_text_length"),
            output_format=voice_data.get("output_format"),
        )

        if settings.upload_audio_to_supabase and self.storage_service:
            upload_result = self.storage_service.upload_audio(
                local_file_path=local_audio_path,
                storage_path=storage_path,
            )
            voice_audio_path = self._voice_audio_path(storage_path=storage_path)
            voice_data.update(
                {
                    **upload_result,
                    "storage_path": storage_path,
                    "voice_audio_path": voice_audio_path,
                    "uploaded_to_supabase": True,
                }
            )
            if settings.delete_local_audio_after_upload:
                self._delete_local_audio(local_audio_path)

        return voice_data

    def _voice_metadata(
        self,
        local_audio_path: str,
        storage_path: str | None,
        script_hash: str,
        cached: bool,
        uploaded_to_supabase: bool,
        voice_audio_path: str,
        cleaned_text_length: int | None = None,
        output_format: str | None = None,
    ) -> dict:
        metadata = {
            "provider": "elevenlabs",
            "voice_name": self.tts_service.voice_name,
            "voice_id": self.tts_service.voice_id,
            "model_id": self.tts_service.model_id,
            "script_hash": script_hash,
            "local_audio_path": local_audio_path,
            "voice_audio_path": voice_audio_path,
            "cached": cached,
            "uploaded_to_supabase": uploaded_to_supabase,
        }
        if output_format:
            metadata["output_format"] = output_format
        if cleaned_text_length is not None:
            metadata["cleaned_text_length"] = cleaned_text_length
        if storage_path:
            metadata.update(
                {
                    "storage_provider": "supabase",
                    "bucket": settings.supabase_audio_bucket,
                    "storage_path": storage_path,
                }
            )
        return metadata

    @staticmethod
    def _voice_audio_path(storage_path: str) -> str:
        return f"{settings.supabase_audio_bucket}/{storage_path}"

    @staticmethod
    def _delete_local_audio(local_audio_path: str) -> None:
        path = Path(local_audio_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if path.exists():
            path.unlink()

    def _mark_failed(self, movie_id: int, movie: dict, exc: Exception) -> None:
        self.repository.update_voice_failed(
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
                    status=VOICE_FAILED,
                    message=str(exc),
                    data={"tmdb_id": movie.get("tmdb_id")},
                ),
            },
        )

    @staticmethod
    def _next_agent_after_voice() -> str:
        if settings.source_video_mode == "manual":
            return NEXT_AGENT_SCENE_SELECTION
        return NEXT_AGENT_VIDEO_DOWNLOADER

    @staticmethod
    def _overall_status_after_voice() -> str:
        if settings.source_video_mode == "manual":
            return OVERALL_WAITING_SOURCE_VIDEO
        return OVERALL_VOICE_READY
