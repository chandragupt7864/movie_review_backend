import logging
import threading
import time

from app.agent_factory import (
    build_cut_merge_agent,
    build_pipeline_watchdog_agent,
    build_review_script_agent,
    build_scene_selection_agent,
    build_shorts_composer_agent,
    build_trailer_finder_agent,
    build_video_downloader_agent,
    build_voice_generator_agent,
)
from app.config import settings


logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._watchdog_thread: threading.Thread | None = None

    def start(self) -> None:
        if not settings.pipeline_auto_run:
            logger.info("Pipeline orchestrator is disabled because PIPELINE_AUTO_RUN=false.")
            return
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, name="pipeline-orchestrator", daemon=True)
        self._thread.start()
        self._watchdog_thread = threading.Thread(
            target=self._run_watchdog_loop,
            name="pipeline-watchdog-scheduler",
            daemon=True,
        )
        self._watchdog_thread.start()
        logger.info(
            "Pipeline orchestrator started with voice_mode=%s source_video_mode=%s thumbnail_mode=%s.",
            settings.voice_mode,
            settings.source_video_mode,
            settings.thumbnail_mode,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            self._watchdog_thread.join(timeout=5)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_cycle()
            except Exception:
                logger.exception("Pipeline orchestrator cycle failed.")
            self._stop_event.wait(timeout=max(1.0, float(settings.worker_poll_interval_seconds)))

    def _run_watchdog_loop(self) -> None:
        interval = max(30.0, float(settings.watchdog_interval_seconds))
        while not self._stop_event.wait(timeout=interval):
            self._safe_run("pipeline_watchdog", lambda: build_pipeline_watchdog_agent().run(limit=50))

    def run_cycle(self) -> None:
        # Keep the pipeline strictly serial so each poll advances only one
        # queued movie by one agent step. This avoids multiple movies being
        # processed by different agents in the same cycle.
        batch_size = 1

        # Yeh early return nahi karta — pipeline ke baad bhi chalta hai.
        if self._safe_run("trailer_finder", lambda: build_trailer_finder_agent().run(limit=batch_size)):
            return
        if self._safe_run("review_script", lambda: build_review_script_agent().run(limit=batch_size)):
            return

        if settings.voice_mode == "auto":
            if self._safe_run("voice_generator", lambda: build_voice_generator_agent().run(limit=batch_size)):
                return

        if settings.source_video_mode in {"auto", "hybrid"}:
            if self._safe_run("video_downloader", lambda: build_video_downloader_agent().run(limit=batch_size)):
                return

        if self._safe_run("scene_selection", lambda: build_scene_selection_agent().run(limit=batch_size)):
            return
        if self._safe_run("cut_merge", lambda: build_cut_merge_agent().run(limit=batch_size)):
            return
        self._safe_run("shorts_composer", lambda: build_shorts_composer_agent().run(limit=batch_size))

    @staticmethod
    def _safe_run(agent_name: str, runner) -> bool:
        started_at = time.monotonic()
        try:
            result = runner()
            duration_ms = int((time.monotonic() - started_at) * 1000)
            processed = int(result.get("processed") or 0) if isinstance(result, dict) else 0
            completed = int(result.get("completed") or 0) if isinstance(result, dict) else 0
            failed = int(result.get("failed") or 0) if isinstance(result, dict) else 0
            did_work = processed > 0 or failed > 0
            if did_work:
                logger.info(
                    "Worker %s processed=%s completed=%s failed=%s duration_ms=%s",
                    agent_name,
                    processed,
                    completed,
                    failed,
                    duration_ms,
                )
            return did_work
        except Exception:
            duration_ms = int((time.monotonic() - started_at) * 1000)
            logger.exception("Worker %s failed after %sms", agent_name, duration_ms)
            return True
