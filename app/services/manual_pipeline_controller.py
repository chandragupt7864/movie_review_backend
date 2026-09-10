import threading
from datetime import datetime, timezone

from app.agent_factory import (
    build_cut_merge_agent,
    build_pipeline_watchdog_agent,
    build_review_script_agent,
    build_scene_selection_agent,
    build_shorts_composer_agent,
    build_trailer_finder_agent,
    build_video_downloader_agent,
)
from app.config import settings
from app.core.agent_status import (
    NEXT_AGENT_CUT_MERGE,
    NEXT_AGENT_DONE,
    NEXT_AGENT_REVIEW_REACTION,
    NEXT_AGENT_SCENE_SELECTION,
    NEXT_AGENT_SHORTS_COMPOSER,
    NEXT_AGENT_TRAILER,
    NEXT_AGENT_VIDEO_DOWNLOADER,
    NEXT_AGENT_VOICE_GENERATOR,
    OVERALL_WAITING_SOURCE_VIDEO,
    VIDEO_DOWNLOAD_FAILED,
)
from app.repositories.movie_pipeline_repository import MoviePipelineRepository


class ManualPipelineController:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._state_lock = threading.Lock()
        self._mode: str | None = None
        self._movie_id: int | None = None
        self._movie_title: str | None = None
        self._started_at: str | None = None
        self._stop_requested = False

    def start_global(self) -> dict:
        repository = MoviePipelineRepository()
        repository.release_stale_locks()
        with self._state_lock:
            if self._is_active_locked():
                raise RuntimeError("A pipeline process is already running. Stop it first.")
            self._set_running_state(mode="global", movie_id=None, movie_title=None)
            self._thread = threading.Thread(target=self._run_global, name="manual-pipeline-global", daemon=True)
            self._thread.start()
        return self.status()

    def start_movie(self, movie_id: int) -> dict:
        repository = MoviePipelineRepository()
        repository.release_stale_locks()
        movie = repository.get_movie_by_id(movie_id=movie_id)
        if not movie:
            raise ValueError("Movie not found.")

        with self._state_lock:
            if self._is_active_locked():
                raise RuntimeError("A pipeline process is already running. Stop it first.")
            self._set_running_state(mode="movie", movie_id=movie_id, movie_title=movie.get("movie_title"))
            self._thread = threading.Thread(
                target=self._run_single_movie,
                args=(movie_id,),
                name=f"manual-pipeline-movie-{movie_id}",
                daemon=True,
            )
            self._thread.start()
        return self.status()

    def stop(self) -> dict:
        thread: threading.Thread | None = None
        with self._state_lock:
            self._stop_requested = True
            self._stop_event.set()
            thread = self._thread

        if thread and thread.is_alive():
            thread.join(timeout=2)

        if not thread or not thread.is_alive():
            with self._state_lock:
                self._clear_state_locked()

        return self.status()

    def status(self) -> dict:
        with self._state_lock:
            active = self._is_active_locked()
            return {
                "active": active,
                "mode": self._mode,
                "movie_id": self._movie_id,
                "movie_title": self._movie_title,
                "started_at": self._started_at,
                "stop_requested": self._stop_requested if active else False,
            }

    def _run_global(self) -> None:
        try:
            while not self._stop_event.is_set():
                movie = self._next_global_movie()
                if not movie:
                    break
                self._process_movie_until_pause(int(movie["id"]))
        finally:
            with self._state_lock:
                self._clear_state_locked()

    def _run_single_movie(self, movie_id: int) -> None:
        try:
            self._process_movie_until_pause(movie_id)
        finally:
            with self._state_lock:
                self._clear_state_locked()

    def _process_movie_until_pause(self, movie_id: int) -> None:
        previous_signature: tuple | None = None
        repository = MoviePipelineRepository()

        while not self._stop_event.is_set():
            movie = repository.get_movie_by_id(movie_id=movie_id)
            if not movie or not movie.get("is_active", True):
                return

            with self._state_lock:
                self._movie_title = movie.get("movie_title")

            if self._should_pause_for_manual_step(movie):
                return
            if self._is_terminal(movie):
                return
            if movie.get("current_agent") or movie.get("is_locked"):
                return

            signature = self._movie_signature(movie)
            if previous_signature == signature:
                return

            if not self._run_next_step(movie):
                return

            previous_signature = signature

    def _next_global_movie(self) -> dict | None:
        repository = MoviePipelineRepository()
        for movie in repository.get_manual_controller_candidates(limit=200):
            if self._is_terminal(movie):
                continue
            if self._should_skip_global_retry(movie):
                continue
            if self._should_pause_for_manual_step(movie):
                continue
            if movie.get("current_agent") or movie.get("is_locked"):
                continue
            return movie
        return None

    @staticmethod
    def _should_skip_global_retry(movie: dict) -> bool:
        return (
            str(movie.get("next_agent") or "") == NEXT_AGENT_VIDEO_DOWNLOADER
            and str(movie.get("video_download_status") or "") == VIDEO_DOWNLOAD_FAILED
        )

    @staticmethod
    def _movie_signature(movie: dict) -> tuple:
        return (
            movie.get("next_agent"),
            movie.get("trailer_status"),
            movie.get("review_status"),
            movie.get("script_status"),
            movie.get("voice_status"),
            movie.get("video_download_status"),
            movie.get("scene_status"),
            movie.get("render_status"),
            movie.get("shorts_status"),
            movie.get("thumbnail_status"),
            movie.get("updated_at"),
        )

    @staticmethod
    def _is_terminal(movie: dict) -> bool:
        return str(movie.get("next_agent") or "") == NEXT_AGENT_DONE

    @staticmethod
    def _has_source_video(movie: dict) -> bool:
        if movie.get("source_video_path"):
            return True
        return bool(list(movie.get("source_videos_json") or []))

    def _should_pause_for_manual_step(self, movie: dict) -> bool:
        next_agent = str(movie.get("next_agent") or "")
        error_data = movie.get("error_data_json") or {}
        manual_source_url_required = isinstance(error_data, dict) and bool(error_data.get("manual_source_url_required"))

        if next_agent == NEXT_AGENT_SHORTS_COMPOSER and (not movie.get("thumbnail_path") or movie.get("thumbnail_status") != "COMPLETED"):
            return True
        if next_agent == NEXT_AGENT_VOICE_GENERATOR and not movie.get("voice_audio_path"):
            return True
        if next_agent == NEXT_AGENT_VIDEO_DOWNLOADER and manual_source_url_required:
            return True
        if settings.source_video_mode == "manual" and next_agent == NEXT_AGENT_SCENE_SELECTION and not self._has_source_video(movie):
            return True
        return False

    def _run_next_step(self, movie: dict) -> bool:
        movie_id = int(movie["id"])
        next_agent = str(movie.get("next_agent") or "")
        overall_status = str(movie.get("overall_status") or "")

        # A queued downloader must run; otherwise WAITING_SOURCE_VIDEO loops on the watchdog.
        if overall_status == OVERALL_WAITING_SOURCE_VIDEO and next_agent != NEXT_AGENT_VIDEO_DOWNLOADER:
            build_pipeline_watchdog_agent().run_for_movie(movie_id=movie_id)
            return True

        if next_agent == NEXT_AGENT_TRAILER:
            build_trailer_finder_agent().run_for_movie(movie_id=movie_id)
            return True
        if next_agent == NEXT_AGENT_REVIEW_REACTION:
            build_review_script_agent().run_for_movie(movie_id=movie_id)
            return True
        if next_agent == NEXT_AGENT_VIDEO_DOWNLOADER:
            build_video_downloader_agent().run_for_movie(movie_id=movie_id)
            return True
        if next_agent == NEXT_AGENT_SCENE_SELECTION:
            build_scene_selection_agent().run_for_movie(movie_id=movie_id, force=False)
            return True
        if next_agent == NEXT_AGENT_CUT_MERGE:
            build_cut_merge_agent().run_for_movie(movie_id=movie_id, force=False)
            return True
        if next_agent == NEXT_AGENT_SHORTS_COMPOSER:
            build_shorts_composer_agent().run_for_movie(movie_id=movie_id, force=False)
            return True
        # Thumbnail aur Poster abhi ke liye disabled hain — Shorts ke baad DONE
        return False

    def _set_running_state(self, mode: str, movie_id: int | None, movie_title: str | None) -> None:
        self._stop_event = threading.Event()
        self._mode = mode
        self._movie_id = movie_id
        self._movie_title = movie_title
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._stop_requested = False

    def _clear_state_locked(self) -> None:
        self._thread = None
        self._mode = None
        self._movie_id = None
        self._movie_title = None
        self._started_at = None
        self._stop_requested = False
        self._stop_event = threading.Event()

    def _is_active_locked(self) -> bool:
        return bool(self._thread and self._thread.is_alive())


manual_pipeline_controller = ManualPipelineController()
