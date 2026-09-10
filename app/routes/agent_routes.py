from fastapi import APIRouter, HTTPException, Query
from app.services.shorts_appearance import ShortsAppearance

from app.agent_factory import (
    build_cut_merge_agent,
    build_movie_discovery_agent,
    build_pipeline_watchdog_agent,
    build_review_script_agent,
    build_scene_selection_agent,
    build_shorts_composer_agent,
    build_thumbnail_metadata_agent,
    build_trailer_finder_agent,
    build_video_downloader_agent,
    build_voice_generator_agent,
)
from app.constants import ALLOWED_DISCOVERY_CATEGORIES
from app.repositories.movie_pipeline_repository import MoviePipelineRepository
from app.config import settings
from app.core.pipeline_utils import utc_now_iso


router = APIRouter()


@router.post("/movie-discovery/run")
def run_movie_discovery(
    category: str = Query(default="released"),
    pages: int = Query(default=1, ge=1, le=5),
):
    if category not in ALLOWED_DISCOVERY_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Allowed values: {sorted(ALLOWED_DISCOVERY_CATEGORIES)}",
        )

    try:
        agent = build_movie_discovery_agent()
        return agent.run(category=category, pages=pages)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Movie discovery failed: {exc}") from exc


@router.post("/trailer-finder/run")
def run_trailer_finder(limit: int = Query(default=1, ge=1, le=20)):
    try:
        agent = build_trailer_finder_agent()
        return agent.run(limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Trailer finder failed: {exc}") from exc


@router.post("/trailer-finder/run/{movie_id}")
def run_trailer_finder_for_movie(movie_id: int):
    try:
        agent = build_trailer_finder_agent()
        return agent.run_for_movie(movie_id=movie_id)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Trailer finder failed: {exc}") from exc


@router.post("/review-script/run")
def run_review_script(limit: int = Query(default=1, ge=1, le=10)):
    try:
        agent = build_review_script_agent()
        return agent.run(limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Review script agent failed: {exc}") from exc


@router.post("/review-script/run/{movie_id}")
def run_review_script_for_movie(movie_id: int):
    try:
        agent = build_review_script_agent()
        return agent.run_for_movie(movie_id=movie_id)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Review script agent failed: {exc}") from exc


@router.post("/voice-generator/run")
def run_voice_generator(
    limit: int = Query(default=1, ge=1, le=5),
    force: bool = Query(default=False),
):
    try:
        agent = build_voice_generator_agent()
        return agent.run(limit=limit, force=force)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Voice generator agent failed: {exc}") from exc


@router.post("/voice-generator/run/{movie_id}")
def run_voice_generator_for_movie(
    movie_id: int,
    force: bool = Query(default=False),
):
    try:
        agent = build_voice_generator_agent()
        return agent.run_for_movie(movie_id=movie_id, force=force)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Voice generator agent failed: {exc}") from exc


@router.post("/scene-selection/run")
def run_scene_selection(limit: int = Query(default=1, ge=1, le=5)):
    try:
        agent = build_scene_selection_agent()
        return agent.run(limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Scene selection agent failed: {exc}") from exc


@router.post("/scene-selection/run/{movie_id}")
def run_scene_selection_for_movie(
    movie_id: int,
    force: bool = Query(default=False),
):
    try:
        agent = build_scene_selection_agent()
        return agent.run_for_movie(movie_id=movie_id, force=force)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Scene selection agent failed: {exc}") from exc


@router.post("/video-downloader/run")
def run_video_downloader(limit: int = Query(default=1, ge=1, le=5)):
    try:
        agent = build_video_downloader_agent()
        return agent.run(limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Video downloader agent failed: {exc}") from exc


@router.post("/video-downloader/run/{movie_id}")
def run_video_downloader_for_movie(movie_id: int):
    try:
        agent = build_video_downloader_agent()
        return agent.run_for_movie(movie_id=movie_id)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Video downloader agent failed: {exc}") from exc


@router.post("/cut-merge/run")
def run_cut_merge(limit: int = Query(default=1, ge=1, le=5)):
    try:
        agent = build_cut_merge_agent()
        return agent.run(limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Cut merge agent failed: {exc}") from exc


@router.post("/cut-merge/run/{movie_id}")
def run_cut_merge_for_movie(movie_id: int, force: bool = Query(default=False)):
    try:
        agent = build_cut_merge_agent()
        return agent.run_for_movie(movie_id=movie_id, force=force)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Cut merge agent failed: {exc}") from exc


@router.post("/shorts-composer/run")
def run_shorts_composer(limit: int = Query(default=1, ge=1, le=5)):
    try:
        agent = build_shorts_composer_agent()
        return agent.run(limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Shorts composer agent failed: {exc}") from exc


@router.post("/shorts-composer/run/{movie_id}")
def run_shorts_composer_for_movie(movie_id: int, force: bool = Query(default=False), appearance: ShortsAppearance | None = None):
    try:
        agent = build_shorts_composer_agent()
        return agent.run_for_movie(movie_id=movie_id, force=force, appearance=appearance.model_dump() if appearance else None)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Shorts composer agent failed: {exc}") from exc


@router.post("/thumbnail/run")
def run_thumbnail_metadata(limit: int = Query(default=1, ge=1, le=5)):
    if settings.thumbnail_mode == "manual":
        raise HTTPException(
            status_code=400,
            detail="Thumbnail automation is disabled because THUMBNAIL_MODE=manual. Use /movies/{movie_id}/thumbnail-upload instead.",
        )
    try:
        agent = build_thumbnail_metadata_agent()
        return agent.run(limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Thumbnail metadata agent failed: {exc}") from exc


@router.post("/thumbnail/run/{movie_id}")
def run_thumbnail_metadata_for_movie(movie_id: int, force: bool = Query(default=False)):
    if settings.thumbnail_mode == "manual":
        raise HTTPException(
            status_code=400,
            detail="Thumbnail automation is disabled because THUMBNAIL_MODE=manual. Use /movies/{movie_id}/thumbnail-upload instead.",
        )
    try:
        agent = build_thumbnail_metadata_agent()
        return agent.run_for_movie(movie_id=movie_id, force=force)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Thumbnail metadata agent failed: {exc}") from exc


@router.post("/audio-cleanup/run")
def run_audio_cleanup(
    keep_last: int = Query(default=settings.supabase_audio_keep_last, ge=5, le=100),
    safe_only: bool = Query(default=True),
):
    if not settings.audio_cleanup_enabled:
        return {
            "success": True,
            "cleanup_enabled": False,
            "deleted_count": 0,
            "deleted_paths": [],
        }

    try:
        repository = MoviePipelineRepository()
        storage_service = SupabaseStorageService()
        if safe_only:
            return _run_safe_audio_cleanup(
                repository=repository,
                storage_service=storage_service,
                keep_last=keep_last,
            )

        cleanup_result = storage_service.cleanup_old_audio_files(keep_last=keep_last)
        deleted_at = utc_now_iso()
        _mark_deleted_audio_rows(
            repository=repository,
            deleted_paths=cleanup_result["deleted_paths"],
            deleted_at=deleted_at,
            safe_only=False,
        )
        return {"success": True, "safe_only": False, **cleanup_result}
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Audio cleanup failed: {exc}") from exc


def _run_safe_audio_cleanup(repository, storage_service, keep_last: int) -> dict:
    rows = repository.get_voice_audio_cleanup_candidates(safe_only=False)
    rows_by_storage_path = {
        _row_storage_path(row): row
        for row in rows
        if _row_storage_path(row)
    }
    protected_paths = {
        _row_storage_path(row)
        for row in rows[:keep_last]
        if _row_storage_path(row)
    }
    bucket_files = storage_service.list_audio_files()
    deleted_paths = []
    deleted_at = utc_now_iso()

    for file_item in bucket_files:
        storage_path = file_item["storage_path"]
        row = rows_by_storage_path.get(storage_path)
        if not row:
            continue
        if storage_path in protected_paths:
            continue
        if not row.get("final_video_path"):
            continue
        storage_service.delete_file(storage_path=storage_path)
        repository.mark_voice_audio_deleted(movie_id=int(row["id"]), deleted_at=deleted_at)
        deleted_paths.append(storage_path)

    return {
        "success": True,
        "safe_only": True,
        "bucket": storage_service.bucket,
        "storage_provider": storage_service.storage_provider,
        "keep_last": keep_last,
        "deleted_count": len(deleted_paths),
        "deleted_paths": deleted_paths,
    }


def _mark_deleted_audio_rows(repository, deleted_paths: list[str], deleted_at: str, safe_only: bool) -> None:
    if not deleted_paths:
        return
    rows = repository.get_voice_audio_cleanup_candidates(safe_only=safe_only)
    path_set = set(deleted_paths)
    for row in rows:
        storage_path = _row_storage_path(row)
        if storage_path in path_set:
            repository.mark_voice_audio_deleted(movie_id=int(row["id"]), deleted_at=deleted_at)


def _row_storage_path(row: dict) -> str | None:
    voice_data = row.get("voice_data_json") or {}
    if isinstance(voice_data, dict) and voice_data.get("storage_path"):
        return str(voice_data["storage_path"])

    audio_path = row.get("voice_audio_path")
    if not audio_path:
        return None
    audio_path = str(audio_path)
    bucket_prefix = f"{settings.supabase_audio_bucket}/"
    if audio_path.startswith(bucket_prefix):
        return audio_path[len(bucket_prefix):]
    if audio_path.startswith("audio/"):
        return audio_path
    return None


@router.post("/pipeline-watchdog/run")
def run_pipeline_watchdog(limit: int = Query(default=20, ge=1, le=100)):
    """
    Pipeline Watchdog Agent — sab stuck WAITING_SOURCE_VIDEO movies scan karta hai aur fix karta hai.
    - source_videos_json se clips/non-trailer entries hataata hai
    - Valid trailer ke saath movies ko Video Downloader ke liye re-queue karta hai
    - Scene selection jo source video ki wajah se ruki hai use unblock karta hai
    """
    try:
        agent = build_pipeline_watchdog_agent()
        return agent.run(limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pipeline watchdog failed: {exc}") from exc


@router.post("/pipeline-watchdog/run/{movie_id}")
def run_pipeline_watchdog_for_movie(movie_id: int):
    """
    Pipeline Watchdog Agent — specific movie ko inspect aur fix karta hai.
    """
    try:
        agent = build_pipeline_watchdog_agent()
        return agent.run_for_movie(movie_id=movie_id)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pipeline watchdog failed: {exc}") from exc
