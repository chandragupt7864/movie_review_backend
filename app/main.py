import logging
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.agent_routes import router as agent_router
from app.routes.bgm_routes import router as bgm_router
from app.routes.movie_routes import router as movie_router
from app.routes.pipeline_control_routes import router as pipeline_control_router
from app.agent_factory import build_pipeline_watchdog_agent
from app.services.manual_pipeline_controller import manual_pipeline_controller
from app.services.pipeline_orchestrator import PipelineOrchestrator


app = FastAPI(title="Movie Review Agent System")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        # Capacitor WebView origins (Android and iOS defaults).
        "https://localhost",
        "capacitor://localhost",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):30\d{2}",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent_router, prefix="/agents", tags=["agents"])
app.include_router(bgm_router, tags=["bgm"])
app.include_router(movie_router, tags=["movies"])
app.include_router(pipeline_control_router, prefix="/pipeline-control", tags=["pipeline-control"])


def _run_startup_watchdog() -> None:
    try:
        result = build_pipeline_watchdog_agent().run(limit=50)
        logging.getLogger(__name__).info(
            "Watchdog startup scan complete: processed=%s fixed=%s requeued=%s",
            result.get("processed", 0),
            result.get("fixed", 0),
            result.get("requeued", 0),
        )
    except Exception:
        logging.getLogger(__name__).exception("Watchdog startup scan failed (non-critical).")


@app.on_event("startup")
def start_pipeline_orchestrator() -> None:
    # Pipeline orchestrator start karo (har N seconds mein cycle chalta hai)
    orchestrator = PipelineOrchestrator()
    orchestrator.start()
    app.state.pipeline_orchestrator = orchestrator

    # Keep API startup responsive while the watchdog performs DB/file checks.
    watchdog_thread = threading.Thread(
        target=_run_startup_watchdog,
        name="pipeline-watchdog-startup",
        daemon=True,
    )
    watchdog_thread.start()
    app.state.pipeline_watchdog_thread = watchdog_thread


@app.on_event("shutdown")
def stop_pipeline_orchestrator() -> None:
    orchestrator = getattr(app.state, "pipeline_orchestrator", None)
    if orchestrator:
        orchestrator.stop()
    manual_pipeline_controller.stop()


@app.get("/")
def health_check():
    return {"status": "ok", "service": "movie-review-agent-system"}
