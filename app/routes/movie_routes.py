import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Body, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from app.agent_factory import build_movie_discovery_agent
from app.config import PROJECT_ROOT, settings
from app.core.agent_status import (
    NEXT_AGENT_SCENE_SELECTION,
    NEXT_AGENT_VIDEO_DOWNLOADER,
    OVERALL_VOICE_READY,
    OVERALL_WAITING_SOURCE_VIDEO,
)
from app.core.pipeline_utils import build_timeline_event
from app.repositories.movie_pipeline_repository import MoviePipelineRepository
from app.services.tmdb_service import HOLLYWOOD_LANGUAGE, TMDBService
from app.services.supabase_storage_service import SupabaseStorageService
from app.services.video_metadata_service import VideoMetadataService
from app.services.audio_metadata_service import AudioMetadataService
from app.services.lyria_music_service import LyriaMusicService
from app.services.cloudinary_video_storage_service import CloudinaryVideoStorageService


router = APIRouter()
logger = logging.getLogger(__name__)
MANUAL_DISCOVERY_CATEGORY = "manual_dashboard"


@router.get("/selector/api/movies")
def browse_selector_movies(
    query: str | None = Query(default=None),
    category: str = Query(default="all"),
    page: int = Query(default=1, ge=1, le=20),
    genre_id: int | None = Query(default=None),
    language: str | None = Query(default=None),
    original_language: str | None = Query(default=None),
    region: str | None = Query(default=None),
    year: int | None = Query(default=None, ge=1880, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    sort_by: str = Query(default="popularity.desc"),
    vote_average_min: float | None = Query(default=None),
    vote_count_min: int | None = Query(default=None),
    include_adult: bool = Query(default=False),
):
    tmdb_service = TMDBService()
    repository = MoviePipelineRepository()
    try:
        payload = tmdb_service.browse_movies_general(
            query=query,
            category=category,
            genre_id=genre_id,
            language=language,
            original_language=original_language,
            region=region,
            year=year,
            month=month,
            date_from=date_from,
            date_to=date_to,
            sort_by=sort_by,
            vote_average_min=vote_average_min,
            vote_count_min=vote_count_min,
            include_adult=include_adult,
            page=page,
        )
        tmdb_ids = [int(movie["id"]) for movie in payload.get("results") or [] if movie.get("id") is not None]
        selected_ids = repository.get_existing_tmdb_ids(tmdb_ids)
    except LookupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        _raise_tmdb_bad_gateway(exc)

    movies = [
        tmdb_service.build_selector_movie_payload(
            movie=movie,
            genre_map=payload["genre_map"],
            selected_ids=selected_ids,
        )
        for movie in payload.get("results") or []
    ]
    return {
        "success": True,
        "filters": {
            "query": query,
            "category": category,
            "genre_id": genre_id,
            "language": payload["effective_language"],
            "original_language": original_language,
            "region": region,
            "year": year,
            "month": month,
            "date_from": payload["effective_date_from"],
            "date_to": payload["effective_date_to"],
            "sort_by": sort_by,
            "vote_average_min": vote_average_min,
            "vote_count_min": vote_count_min,
            "include_adult": include_adult,
            "page": page,
        },
        "pagination": {
            "page": int(payload.get("page") or page),
            "total_pages": int(payload.get("total_pages") or 1),
            "total_results": int(payload.get("total_results") or len(movies)),
            "has_next": int(payload.get("page") or page) < int(payload.get("total_pages") or 1),
            "has_previous": int(payload.get("page") or page) > 1,
        },
        "movies": movies,
    }


@router.get("/selector/api/categories")
def get_selector_categories():
    return {"success": True, "categories": TMDBService().get_movie_categories()}


@router.get("/selector/api/genres")
def get_selector_genres(language: str = Query(default=HOLLYWOOD_LANGUAGE)):
    try:
        genres = TMDBService().get_all_movie_genres(language=language)
    except Exception as exc:
        _raise_tmdb_bad_gateway(exc)
    return {"success": True, "genres": genres}


@router.get("/selector/api/languages")
def get_selector_languages():
    try:
        languages = TMDBService().get_available_languages()
    except Exception as exc:
        _raise_tmdb_bad_gateway(exc)
    return {"success": True, "languages": languages}


@router.get("/selector/api/regions")
def get_selector_regions():
    try:
        regions = TMDBService().get_available_regions()
    except Exception as exc:
        _raise_tmdb_bad_gateway(exc)
    return {"success": True, "regions": regions}


@router.get("/selector/api/details/{tmdb_id}")
def get_selector_movie_details(tmdb_id: int, language: str = Query(default=HOLLYWOOD_LANGUAGE)):
    repository = MoviePipelineRepository()
    try:
        details = TMDBService().get_movie_details_for_selector(tmdb_id=tmdb_id, language=language)
        existing = repository.get_movie_by_tmdb_id(tmdb_id=tmdb_id)
    except Exception as exc:
        _raise_tmdb_bad_gateway(exc)

    return {
        "success": True,
        "movie": {
            "tmdb_id": int(details["id"]),
            "imdb_id": (details.get("external_ids") or {}).get("imdb_id"),
            "title": details.get("title") or details.get("original_title"),
            "original_title": details.get("original_title"),
            "tagline": details.get("tagline"),
            "overview": details.get("overview"),
            "release_date": details.get("release_date"),
            "release_year": _release_year(details.get("release_date")),
            "runtime": details.get("runtime"),
            "status": details.get("status"),
            "original_language": details.get("original_language"),
            "spoken_languages": list(details.get("spoken_languages") or []),
            "genres": list(details.get("genres") or []),
            "production_companies": list(details.get("production_companies") or []),
            "production_countries": list(details.get("production_countries") or []),
            "vote_average": details.get("vote_average"),
            "vote_count": details.get("vote_count"),
            "popularity": details.get("popularity"),
            "budget": details.get("budget"),
            "revenue": details.get("revenue"),
            "poster_url": _tmdb_image_url(details.get("poster_path")),
            "backdrop_url": _tmdb_image_url(details.get("backdrop_path")),
            "homepage": details.get("homepage"),
            "adult": bool(details.get("adult")),
            "is_selected": existing is not None,
        },
    }


@router.post("/selector/api/select")
def select_movie_for_discovery(payload: dict = Body(...)):
    tmdb_id = payload.get("tmdb_id")
    if not isinstance(tmdb_id, int):
        raise HTTPException(status_code=400, detail="tmdb_id must be an integer.")

    tmdb_service = TMDBService()
    repository = MoviePipelineRepository()
    try:
        existing = repository.get_movie_by_tmdb_id(tmdb_id=tmdb_id)
        if existing:
            return {
                "success": True,
                "already_exists": True,
                "message": "Movie already exists in pipeline",
                "pipeline_movie_id": int(existing["id"]),
                "tmdb_id": tmdb_id,
                "movie_title": existing.get("movie_title"),
                "next_agent": existing.get("next_agent"),
            }
        details = tmdb_service.get_movie_details_for_selector(tmdb_id=tmdb_id)
        build_movie_discovery_agent().queue_selected_movie(movie=details, category="selected")
        saved = repository.get_movie_by_tmdb_id(tmdb_id=tmdb_id)
    except Exception as exc:
        _raise_tmdb_bad_gateway(exc)

    if not saved:
        raise HTTPException(status_code=500, detail="Movie added but pipeline row could not be loaded")
    return {
        "success": True,
        "already_exists": False,
        "message": "Movie added to pipeline",
        "pipeline_movie_id": int(saved["id"]),
        "tmdb_id": tmdb_id,
        "movie_title": saved.get("movie_title"),
        "next_agent": saved.get("next_agent"),
    }


@router.get("/manual-movies/search")
def search_manual_movies(
    query: str = Query(..., min_length=2),
    page: int = Query(default=1, ge=1, le=20),
    language: str = Query(default=HOLLYWOOD_LANGUAGE),
):
    tmdb_service = TMDBService()
    repository = MoviePipelineRepository()
    try:
        payload = tmdb_service.browse_movies_general(
            query=query,
            category="all",
            genre_id=None,
            language=language,
            original_language=None,
            region=None,
            year=None,
            month=None,
            date_from=None,
            date_to=None,
            sort_by="popularity.desc",
            vote_average_min=None,
            vote_count_min=None,
            include_adult=False,
            page=page,
        )
        fallback_title, fallback_year = _split_trailing_release_year(query)
        if not payload.get("results") and fallback_title and fallback_year:
            payload = tmdb_service.browse_movies_general(
                query=fallback_title,
                category="all",
                genre_id=None,
                language=language,
                original_language=None,
                region=None,
                year=fallback_year,
                month=None,
                date_from=None,
                date_to=None,
                sort_by="popularity.desc",
                vote_average_min=None,
                vote_count_min=None,
                include_adult=False,
                page=page,
            )
        tmdb_ids = [int(movie["id"]) for movie in payload.get("results") or [] if movie.get("id") is not None]
        manual_ids = repository.get_existing_tmdb_ids_by_discovery_category(
            tmdb_ids=tmdb_ids,
            category=MANUAL_DISCOVERY_CATEGORY,
        )
    except LookupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        _raise_tmdb_bad_gateway(exc)

    movies = [
        tmdb_service.build_selector_movie_payload(
            movie=movie,
            genre_map=payload["genre_map"],
            selected_ids=manual_ids,
        )
        for movie in payload.get("results") or []
    ]
    return {
        "success": True,
        "pagination": {
            "page": int(payload.get("page") or page),
            "total_pages": int(payload.get("total_pages") or 1),
            "total_results": int(payload.get("total_results") or len(movies)),
        },
        "movies": movies,
    }


def _split_trailing_release_year(query: str) -> tuple[str | None, int | None]:
    match = re.fullmatch(r"\s*(.+?)\s*[\[(]?((?:18|19|20)\d{2})[\])]?\s*", query)
    if not match:
        return None, None
    title = match.group(1).strip()
    return (title, int(match.group(2))) if title else (None, None)


@router.post("/manual-movies")
def add_manual_movie(payload: dict = Body(...)):
    tmdb_id = payload.get("tmdb_id")
    if not isinstance(tmdb_id, int):
        raise HTTPException(status_code=400, detail="tmdb_id must be an integer.")

    repository = MoviePipelineRepository()
    try:
        existing = repository.get_movie_by_tmdb_id(tmdb_id=tmdb_id)
        already_manual = bool(existing and existing.get("discovery_category") == MANUAL_DISCOVERY_CATEGORY)
        if not already_manual:
            details = TMDBService().get_movie_details_for_selector(tmdb_id=tmdb_id)
            build_movie_discovery_agent().queue_selected_movie(
                movie=details,
                category=MANUAL_DISCOVERY_CATEGORY,
            )
        saved = repository.get_movie_by_tmdb_id(tmdb_id=tmdb_id)
    except Exception as exc:
        _raise_tmdb_bad_gateway(exc)

    if not saved or saved.get("discovery_category") != MANUAL_DISCOVERY_CATEGORY:
        raise HTTPException(status_code=500, detail="Movie could not be added to the manual pipeline list")
    return {
        "success": True,
        "already_exists": already_manual,
        "message": "Movie already exists in manual list" if already_manual else "Movie added to manual pipeline list",
        "pipeline_movie_id": int(saved["id"]),
        "tmdb_id": tmdb_id,
        "movie_title": saved.get("movie_title"),
        "next_agent": saved.get("next_agent"),
    }


@router.get("/manual-movies")
def list_manual_movies(limit: int = Query(default=100, ge=1, le=100)):
    repository = MoviePipelineRepository()
    try:
        items = repository.list_movies_by_discovery_category(
            category=MANUAL_DISCOVERY_CATEGORY,
            limit=limit,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not fetch manual movies: {exc}") from exc
    return {"items": items}


@router.get("/movies")
def list_movies(limit: int = Query(default=20, ge=1, le=100)):
    repository = MoviePipelineRepository()
    try:
        return {"items": repository.list_latest_movies(limit=limit)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not fetch movies: {exc}") from exc


@router.get("/movies/{movie_id}")
def get_movie(movie_id: int):
    repository = MoviePipelineRepository()
    try:
        movie = repository.get_movie_by_id(movie_id=movie_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not fetch movie: {exc}") from exc

    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found.")
    return movie


def _resolve_bgm_duration(movie: dict) -> float:
    scene_data = movie.get("scene_data_json") or {}
    duration = float(scene_data.get("target_duration_seconds") or 0) if isinstance(scene_data, dict) else 0.0
    if duration <= 0 and movie.get("voice_audio_path"):
        duration = AudioMetadataService().get_audio_duration_seconds(str(movie["voice_audio_path"])) + float(settings.scene_extra_seconds_after_voice)
    return duration if duration > 0 else 55.0


@router.get("/movies/{movie_id}/bgm-prompt")
def get_movie_bgm_prompt(movie_id: int):
    movie = MoviePipelineRepository().get_movie_by_id(movie_id=movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found.")
    if not movie.get("final_script"):
        raise HTTPException(status_code=400, detail="Generate the movie script before creating background music.")
    duration = _resolve_bgm_duration(movie)
    return {
        "success": True,
        "movie_id": movie_id,
        "model": settings.lyria_model,
        "requested_duration_seconds": round(duration, 3),
        "prompt": LyriaMusicService.build_prompt(movie=movie, duration_seconds=duration),
    }


@router.post("/movies/{movie_id}/bgm-upload")
def upload_movie_bgm(movie_id: int, file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".mp3"):
        raise HTTPException(status_code=400, detail="Only .mp3 background music files are allowed.")

    repository = MoviePipelineRepository()
    movie = repository.get_movie_by_id(movie_id=movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found.")
    if not movie.get("final_script"):
        raise HTTPException(status_code=400, detail="Generate the movie script before uploading background music.")

    uploaded_at = datetime.now(timezone.utc).isoformat()
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(file.filename).name)
    unique_name = f"movie_{movie_id}_manual_{uuid4().hex[:10]}_{safe_name}"
    local_dir = PROJECT_ROOT / "storage" / "bgm" / "manual" / f"movie_{movie_id}"
    local_dir.mkdir(parents=True, exist_ok=True)
    local_path = local_dir / unique_name
    relative_path = str(local_path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    max_bytes = 50 * 1024 * 1024
    written_bytes = 0

    try:
        with local_path.open("wb") as audio_file:
            while chunk := file.file.read(1024 * 1024):
                written_bytes += len(chunk)
                if written_bytes > max_bytes:
                    raise ValueError("BGM MP3 must be 50 MB or smaller.")
                audio_file.write(chunk)

        duration = AudioMetadataService().get_audio_duration_seconds(relative_path)
        if duration < 5:
            raise ValueError("BGM MP3 must be at least 5 seconds long.")
        target_duration = _resolve_bgm_duration(movie)
        prompt = LyriaMusicService.build_prompt(movie=movie, duration_seconds=target_duration)
        cloudinary_bgm = None
        if settings.cloudinary_bgm_upload_enabled:
            cloudinary_bgm = CloudinaryVideoStorageService().upload_bgm(
                movie_id=movie_id,
                local_file_path=relative_path,
            )

        bgm_data = {
            "provider": "manual_gemini_upload",
            "model": "Gemini manual generation",
            "prompt": prompt,
            "original_filename": file.filename,
            "content_type": file.content_type,
            "file_size_bytes": written_bytes,
            "duration_seconds": round(duration, 3),
            "requested_duration_seconds": round(target_duration, 3),
            "uploaded_at": uploaded_at,
            "bgm_audio_path": relative_path,
            "cloudinary_bgm_url": cloudinary_bgm["secure_url"] if cloudinary_bgm else None,
            "cloudinary_public_id": cloudinary_bgm["public_id"] if cloudinary_bgm else None,
            "cloudinary": cloudinary_bgm or {},
        }
        repository.update_bgm_generation(
            movie_id=movie_id,
            status="COMPLETED",
            bgm_audio_path=relative_path,
            bgm_data=bgm_data,
        )
    except ValueError as exc:
        local_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        local_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Could not upload background music: {exc}") from exc
    finally:
        file.file.close()

    return {
        "success": True,
        "message": "Background music MP3 uploaded and attached to this movie.",
        "movie_id": movie_id,
        "bgm_status": "COMPLETED",
        "bgm_audio_path": relative_path,
        "cloudinary_bgm_url": cloudinary_bgm["secure_url"] if cloudinary_bgm else None,
        "duration_seconds": round(duration, 3),
        "next_agent": "SHORTS_COMPOSER_AGENT",
    }


@router.post("/movies/{movie_id}/bgm-generate")
def generate_movie_bgm(movie_id: int):
    repository = MoviePipelineRepository()
    movie = repository.get_movie_by_id(movie_id=movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found.")
    if not movie.get("final_script"):
        raise HTTPException(status_code=400, detail="Generate the movie script before creating background music.")

    duration = _resolve_bgm_duration(movie)
    prompt = LyriaMusicService.build_prompt(movie=movie, duration_seconds=duration)

    repository.update_bgm_generation(movie_id=movie_id, status="RUNNING")
    try:
        generated = LyriaMusicService().generate_for_movie(movie=movie, duration_seconds=duration)
        if settings.cloudinary_bgm_upload_enabled:
            cloudinary_bgm = CloudinaryVideoStorageService().upload_bgm(
                movie_id=movie_id,
                local_file_path=generated["bgm_audio_path"],
            )
            generated.update(
                {
                    "cloudinary_bgm_url": cloudinary_bgm["secure_url"],
                    "cloudinary_public_id": cloudinary_bgm["public_id"],
                    "cloudinary": cloudinary_bgm,
                }
            )
        repository.update_bgm_generation(
            movie_id=movie_id,
            status="COMPLETED",
            bgm_audio_path=generated["bgm_audio_path"],
            bgm_data=generated,
        )
    except Exception as exc:
        repository.update_bgm_generation(
            movie_id=movie_id,
            status="FAILED",
            bgm_data={
                "provider": "google_lyria",
                "model": settings.lyria_model,
                "requested_duration_seconds": round(duration, 3),
                "prompt": prompt,
                "error": str(exc),
            },
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail=f"BGM generation failed: {exc}") from exc
    return {"success": True, "movie_id": movie_id, "bgm_status": "COMPLETED", **generated, "preview_url": f"/movies/{movie_id}/bgm-file"}


@router.get("/movies/{movie_id}/bgm-file")
def get_movie_bgm_file(movie_id: int):
    movie = MoviePipelineRepository().get_movie_by_id(movie_id=movie_id)
    if not movie or not movie.get("bgm_audio_path"):
        raise HTTPException(status_code=404, detail="Background music not found.")
    path = Path(str(movie["bgm_audio_path"]))
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists() or not path.is_file():
        bgm_data = movie.get("bgm_data_json") or {}
        cloudinary_url = bgm_data.get("cloudinary_bgm_url") if isinstance(bgm_data, dict) else None
        if cloudinary_url:
            return RedirectResponse(url=str(cloudinary_url))
        raise HTTPException(status_code=404, detail="Background music file is missing on disk.")
    return FileResponse(path=path, media_type="audio/mpeg", filename=path.name)


@router.delete("/movies/{movie_id}")
def delete_movie(movie_id: int):
    repository = MoviePipelineRepository()
    try:
        movie = repository.get_movie_by_id(movie_id=movie_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not fetch movie: {exc}") from exc

    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found.")

    cleanup_warnings = _delete_movie_assets(movie)

    try:
        deleted = repository.delete_movie(movie_id=movie_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not delete movie: {exc}") from exc

    if not deleted:
        raise HTTPException(status_code=404, detail="Movie not found.")

    return {
        "success": True,
        "movie_id": movie_id,
        "movie_title": movie.get("movie_title"),
        "cleanup_warnings": cleanup_warnings,
    }


@router.get("/movies/{movie_id}/frontend-data")
def get_movie_frontend_data(movie_id: int):
    repository = MoviePipelineRepository()
    try:
        movie = repository.get_movie_by_id(movie_id=movie_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not fetch movie: {exc}") from exc

    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found.")
    return _build_frontend_movie_payload(movie)


@router.get("/movies/{movie_id}/master-video-file")
def get_master_video_file(movie_id: int):
    repository = MoviePipelineRepository()
    try:
        movie = repository.get_movie_by_id(movie_id=movie_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not fetch movie: {exc}") from exc

    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found.")

    master_video_path = movie.get("master_video_path")
    if not master_video_path:
        raise HTTPException(status_code=404, detail="Master video not found.")

    local_path = Path(str(master_video_path))
    if not local_path.is_absolute():
        local_path = PROJECT_ROOT / local_path
    if not local_path.exists() or not local_path.is_file():
        raise HTTPException(status_code=404, detail="Master video file is missing on disk.")

    return FileResponse(path=local_path, media_type="video/mp4", filename=local_path.name)


@router.get("/movies/{movie_id}/draft-video-file")
def get_draft_video_file(movie_id: int, preview: bool = False):
    repository = MoviePipelineRepository()
    try:
        movie = repository.get_movie_by_id(movie_id=movie_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not fetch movie: {exc}") from exc

    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found.")

    draft_video_path = ((movie.get("shorts_data_json") or {}).get("preview_base_path") if preview else None) or movie.get("draft_video_path")
    if not draft_video_path:
        raise HTTPException(status_code=404, detail="Draft video not found.")

    local_path = Path(str(draft_video_path))
    if not local_path.is_absolute():
        local_path = PROJECT_ROOT / local_path
    if not local_path.exists() or not local_path.is_file():
        raise HTTPException(status_code=404, detail="Draft video file is missing on disk.")

    return FileResponse(path=local_path, media_type="video/mp4", filename=local_path.name)


@router.get("/movies/{movie_id}/final-video-file")
def get_final_video_file(movie_id: int):
    repository = MoviePipelineRepository()
    try:
        movie = repository.get_movie_by_id(movie_id=movie_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not fetch movie: {exc}") from exc

    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found.")

    final_video_path = movie.get("final_video_path") or movie.get("draft_video_path")
    if not final_video_path:
        raise HTTPException(status_code=404, detail="Final video not found.")

    local_path = Path(str(final_video_path))
    if not local_path.is_absolute():
        local_path = PROJECT_ROOT / local_path
    if not local_path.exists() or not local_path.is_file():
        shorts_data = movie.get("shorts_data_json") or {}
        cloudinary_url = shorts_data.get("cloudinary_video_url") if isinstance(shorts_data, dict) else None
        if cloudinary_url:
            return RedirectResponse(url=str(cloudinary_url))
        raise HTTPException(status_code=404, detail="Final video file is missing on disk.")

    return FileResponse(path=local_path, media_type="video/mp4", filename=local_path.name)


@router.post("/movies/{movie_id}/final-video-cloudinary-upload")
def upload_final_video_to_cloudinary(movie_id: int, force: bool = False):
    repository = MoviePipelineRepository()
    try:
        movie = repository.get_movie_by_id(movie_id=movie_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not fetch movie: {exc}") from exc

    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found.")

    shorts_data = movie.get("shorts_data_json") or {}
    existing_url = shorts_data.get("cloudinary_video_url") if isinstance(shorts_data, dict) else None
    if existing_url and not force:
        return {
            "success": True,
            "already_uploaded": True,
            "movie_id": movie_id,
            "cloudinary_video_url": existing_url,
            "cloudinary": shorts_data.get("cloudinary") or {},
        }

    local_video_path = movie.get("draft_video_path") or movie.get("final_video_path")
    if not local_video_path:
        raise HTTPException(status_code=404, detail="Final Shorts video path is unavailable.")

    try:
        upload_result = CloudinaryVideoStorageService().upload_final_video(
            movie_id=movie_id,
            local_file_path=str(local_video_path),
        )
        repository.update_cloudinary_final_video(movie_id=movie_id, cloudinary_payload=upload_result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Cloudinary final video upload failed for movie %s", movie_id)
        raise HTTPException(status_code=502, detail=f"Cloudinary final video upload failed: {exc}") from exc

    return {
        "success": True,
        "already_uploaded": False,
        "movie_id": movie_id,
        "cloudinary_video_url": upload_result["secure_url"],
        "cloudinary": upload_result,
    }


@router.get("/movies/{movie_id}/voice-text")
def get_voice_text(movie_id: int):
    repository = MoviePipelineRepository()
    try:
        movie = repository.get_movie_by_id(movie_id=movie_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not fetch movie: {exc}") from exc

    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found.")

    script_data = movie.get("script_data_json") or {}
    elevenlabs_script = script_data.get("elevenlabs_script") if isinstance(script_data, dict) else None
    final_script = movie.get("final_script")
    voice_text = elevenlabs_script or final_script
    if not voice_text:
        raise HTTPException(status_code=404, detail="Voice script not found.")

    return {
        "success": True,
        "movie_id": movie_id,
        "movie_title": movie.get("movie_title"),
        "recommended_voice": settings.elevenlabs_voice_name,
        "voice_text": voice_text,
        "final_script": final_script,
        "elevenlabs_script": elevenlabs_script,
    }


@router.post("/movies/{movie_id}/voice-upload")
def upload_voice_audio(movie_id: int, file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".mp3"):
        raise HTTPException(status_code=400, detail="Only .mp3 files are allowed.")

    repository = MoviePipelineRepository()
    try:
        movie = repository.get_movie_by_id(movie_id=movie_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not fetch movie: {exc}") from exc

    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found.")

    uploaded_at = datetime.now(timezone.utc).isoformat()
    safe_name = Path(file.filename).name.replace(" ", "_")
    unique_name = f"movie_{movie_id}_manual_{uuid4().hex[:10]}_{safe_name}"
    local_dir = PROJECT_ROOT / settings.audio_output_dir
    local_dir.mkdir(parents=True, exist_ok=True)
    local_path = local_dir / unique_name
    relative_local_path = str(local_path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    storage_path = f"audio/{unique_name}"

    try:
        with local_path.open("wb") as audio_file:
            while chunk := file.file.read(1024 * 1024):
                audio_file.write(chunk)

        voice_audio_path = relative_local_path
        upload_data = {
            "uploaded_to_supabase": False,
            "local_audio_path": relative_local_path,
        }
        if settings.upload_audio_to_supabase:
            storage_service = SupabaseStorageService()
            upload_data = storage_service.upload_audio(
                local_file_path=relative_local_path,
                storage_path=storage_path,
            )
            voice_audio_path = f"{settings.supabase_audio_bucket}/{storage_path}"

        voice_data = {
            "provider": "manual_upload",
            "voice_name": settings.elevenlabs_voice_name,
            "original_filename": file.filename,
            "content_type": file.content_type,
            "uploaded_at": uploaded_at,
            "voice_audio_path": voice_audio_path,
            "storage_path": storage_path if settings.upload_audio_to_supabase else None,
            **upload_data,
        }
        repository.update_voice_success(
            movie_id=movie_id,
            voice_payload={
                "audio_path": voice_audio_path,
                "voice_data": voice_data,
                "next_agent": _next_agent_after_voice_upload(),
                "overall_status": _overall_status_after_voice_upload(),
                "timeline_event": build_timeline_event(
                    agent="MANUAL_VOICE_UPLOAD",
                    status="COMPLETED",
                    message=f"Manual MP3 uploaded: {file.filename}",
                    data=voice_data,
                ),
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not upload voice audio: {exc}") from exc
    finally:
        file.file.close()

    return {
        "success": True,
        "message": "Voice MP3 uploaded successfully.",
        "movie_id": movie_id,
        "voice_status": "COMPLETED",
        "voice_audio_path": voice_audio_path,
        "overall_status": _overall_status_after_voice_upload(),
        "next_agent": _next_agent_after_voice_upload(),
    }


@router.post("/movies/{movie_id}/source-video-upload")
def upload_source_video(
    movie_id: int,
    file: UploadFile = File(...),
    label: str = Form(default="official_trailer"),
    type: str = Form(default="trailer"),
):
    if not file.filename or not file.filename.lower().endswith(".mp4"):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Only 16:9 trailer/teaser videos are allowed. Shorts/Reels/vertical videos are not allowed as source videos.",
            },
        )

    repository = MoviePipelineRepository()
    video_metadata_service = VideoMetadataService()
    try:
        movie = repository.get_movie_by_id(movie_id=movie_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not fetch movie: {exc}") from exc

    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found.")

    repository.ensure_source_videos_column()

    uploaded_at = datetime.now(timezone.utc).isoformat()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_label = _safe_source_label(label)
    unique_name = f"movie_{movie_id}_{safe_label}_{timestamp}.mp4"
    local_dir = PROJECT_ROOT / settings.video_source_dir
    local_dir.mkdir(parents=True, exist_ok=True)
    local_path = local_dir / unique_name
    relative_local_path = str(local_path.relative_to(PROJECT_ROOT)).replace("\\", "/")

    max_size_bytes = settings.source_video_max_size_mb * 1024 * 1024
    total_size = 0

    try:
        with local_path.open("wb") as output_file:
            while chunk := file.file.read(1024 * 1024):
                total_size += len(chunk)
                if total_size > max_size_bytes:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Source video must be {settings.source_video_max_size_mb} MB or smaller.",
                    )
                output_file.write(chunk)

        validation = video_metadata_service.validate_16x9_source_video(relative_local_path)
        if not validation["valid"]:
            local_path.unlink(missing_ok=True)
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": "Only 16:9 trailer/teaser videos are allowed. Shorts/Reels/vertical videos are not allowed as source videos.",
                },
            )

        metadata = validation["metadata"] or {}
        source_video_payload = {
            "label": safe_label,
            "source_video_path": relative_local_path,
            "type": str(type or "trailer"),
            "aspect_ratio": metadata.get("aspect_ratio", "16:9"),
            "aspect_ratio_value": metadata.get("aspect_ratio_value"),
            "width": metadata.get("width"),
            "height": metadata.get("height"),
            "duration_seconds": metadata.get("duration_seconds"),
            "uploaded_at": uploaded_at,
        }
        updated_movie = repository.add_source_video(movie_id=movie_id, source_video_payload=source_video_payload)
    except HTTPException:
        local_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        local_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Could not upload source video: {exc}") from exc
    finally:
        file.file.close()

    if not updated_movie:
        raise HTTPException(status_code=404, detail="Movie not found.")

    return {
        "success": True,
        "movie_id": movie_id,
        "source_video_path": updated_movie.get("source_video_path"),
        "source_videos_json": updated_movie.get("source_videos_json") or [],
        "next_agent": updated_movie.get("next_agent"),
        "overall_status": updated_movie.get("overall_status"),
        "message": "16:9 source video uploaded successfully",
    }


@router.post("/movies/{movie_id}/source-video-url")
def queue_source_video_url(movie_id: int, payload: dict = Body(...)):
    source_url = str(payload.get("url") or "").strip()
    label = _safe_source_label(str(payload.get("label") or "manual_url"))
    video_type = str(payload.get("type") or "trailer").strip().lower() or "trailer"

    if not source_url:
        raise HTTPException(status_code=400, detail="url is required.")

    repository = MoviePipelineRepository()
    try:
        movie = repository.get_movie_by_id(movie_id=movie_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not fetch movie: {exc}") from exc

    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found.")

    try:
        updated_movie = repository.queue_manual_source_video_url(
            movie_id=movie_id,
            source_url_payload={
                "label": label,
                "url": source_url,
                "type": video_type,
                "added_at": datetime.now(timezone.utc).isoformat(),
                "provider": "manual_url",
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not queue source video URL: {exc}") from exc

    if not updated_movie:
        raise HTTPException(status_code=404, detail="Movie not found.")

    error_data = updated_movie.get("error_data_json") or {}
    manual_candidates = error_data.get("manual_source_candidates") if isinstance(error_data, dict) else []
    return {
        "success": True,
        "movie_id": movie_id,
        "manual_source_candidates": manual_candidates or [],
        "next_agent": updated_movie.get("next_agent"),
        "overall_status": updated_movie.get("overall_status"),
        "video_download_status": updated_movie.get("video_download_status"),
        "message": "Source video URL queued successfully. Video downloader can use it now.",
    }


@router.post("/movies/{movie_id}/thumbnail-upload")
def upload_thumbnail(movie_id: int, file: UploadFile = File(...)):
    allowed_suffixes = {".jpg", ".jpeg", ".png", ".webp"}
    if not file.filename or Path(file.filename).suffix.lower() not in allowed_suffixes:
        raise HTTPException(status_code=400, detail="Only .jpg, .jpeg, .png, or .webp thumbnail files are allowed.")

    repository = MoviePipelineRepository()
    try:
        movie = repository.get_movie_by_id(movie_id=movie_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not fetch movie: {exc}") from exc

    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found.")
    if movie.get("is_locked") or movie.get("current_agent"):
        raise HTTPException(status_code=409, detail="Wait for the running pipeline step to finish before uploading.")

    uploaded_at = datetime.now(timezone.utc).isoformat()
    suffix = Path(file.filename).suffix.lower() or ".jpg"
    safe_name = Path(file.filename).name.replace(" ", "_")
    unique_name = f"thumbnail_{movie_id}_{uuid4().hex[:10]}_{safe_name}"
    local_dir = PROJECT_ROOT / settings.thumbnail_output_dir / f"movie_{movie_id}"
    local_dir.mkdir(parents=True, exist_ok=True)
    local_path = local_dir / unique_name
    relative_local_path = str(local_path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    storage_path = f"thumbnails/movie_{movie_id}/{unique_name}"
    content_type = file.content_type or _thumbnail_content_type(suffix)

    try:
        with local_path.open("wb") as output_file:
            while chunk := file.file.read(1024 * 1024):
                output_file.write(chunk)

        from PIL import Image, UnidentifiedImageError
        try:
            with Image.open(local_path) as uploaded_image:
                uploaded_image.verify()
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Upload a valid JPG, PNG, or WebP image.") from exc

        final_thumbnail_path = relative_local_path
        uploaded_to_supabase = False
        uploaded_to_cloudinary = False
        cloudinary_thumbnail = None
        storage_warnings = []
        if settings.cloudinary_thumbnail_upload_enabled:
            try:
                cloudinary_thumbnail = CloudinaryVideoStorageService().upload_thumbnail(
                    movie_id=movie_id,
                    local_file_path=relative_local_path,
                )
                uploaded_to_cloudinary = True
            except Exception as exc:
                logger.warning("Thumbnail Cloudinary upload failed for movie %s; keeping local image", movie_id, exc_info=True)
                if settings.cloudinary_thumbnail_upload_required:
                    raise ValueError(f"Cloudinary thumbnail upload failed: {exc}") from exc
                storage_warnings.append("Cloudinary backup unavailable. Thumbnail saved locally and ready for Shorts.")
        elif settings.thumbnail_upload_to_supabase and settings.supabase_url and settings.supabase_service_role_key:
            try:
                storage_service = SupabaseStorageService()
                upload_result = storage_service.upload_file(
                    local_file_path=relative_local_path,
                    bucket=settings.supabase_thumbnail_bucket,
                    storage_path=storage_path,
                    content_type=content_type,
                )
                final_thumbnail_path = upload_result["thumbnail_path"]
                uploaded_to_supabase = True
            except Exception:
                logger.warning("Thumbnail cloud upload failed for movie %s; keeping local image", movie_id, exc_info=True)
                storage_warnings.append("Cloud backup unavailable. Thumbnail saved locally and ready for Shorts.")

        script_data = movie.get("script_data_json") or {}
        if not isinstance(script_data, dict):
            script_data = {}

        thumbnail_data = {
            "provider": "manual_upload",
            "warnings": storage_warnings,
            "original_filename": file.filename,
            "content_type": content_type,
            "local_output_path": relative_local_path,
            "uploaded_to_supabase": uploaded_to_supabase,
            "uploaded_to_cloudinary": uploaded_to_cloudinary,
            "cloudinary_thumbnail_url": cloudinary_thumbnail["secure_url"] if cloudinary_thumbnail else None,
            "cloudinary_public_id": cloudinary_thumbnail["public_id"] if cloudinary_thumbnail else None,
            "cloudinary": cloudinary_thumbnail or {},
            "storage_path": storage_path if uploaded_to_supabase else None,
            "generated_at": uploaded_at,
        }
        repository.update_thumbnail_success(
            movie_id=movie_id,
            thumbnail_payload={
                "thumbnail_path": final_thumbnail_path,
                "thumbnail_data": thumbnail_data,
                "youtube_title": script_data.get("title") or script_data.get("youtube_title") or f"{movie.get('movie_title')} Review",
                "youtube_description": script_data.get("description") or script_data.get("youtube_description") or "",
                "youtube_tags": script_data.get("tags") or script_data.get("youtube_tags") or [],
                "youtube_keywords": script_data.get("keywords") or script_data.get("youtube_keywords") or [],
                "timeline_event": build_timeline_event(
                    agent="MANUAL_THUMBNAIL_UPLOAD",
                    status="COMPLETED",
                    message=f"Manual thumbnail uploaded: {file.filename}",
                    data={
                        "thumbnail_path": final_thumbnail_path,
                        "uploaded_to_supabase": uploaded_to_supabase,
                        "uploaded_to_cloudinary": uploaded_to_cloudinary,
                    },
                ),
            },
        )
    except HTTPException:
        local_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        local_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Could not upload thumbnail: {exc}") from exc
    finally:
        file.file.close()

    return {
        "success": True,
        "movie_id": movie_id,
        "thumbnail_path": final_thumbnail_path,
        "uploaded_to_supabase": uploaded_to_supabase,
        "uploaded_to_cloudinary": uploaded_to_cloudinary,
        "cloudinary_thumbnail_url": cloudinary_thumbnail["secure_url"] if cloudinary_thumbnail else None,
        "next_agent": "SHORTS_COMPOSER_AGENT" if movie.get("render_status") == "COMPLETED" else movie.get("next_agent"),
        "message": "Thumbnail uploaded. Compose Shorts to include it as a 2-second ending.",
    }


@router.get("/movies/{movie_id}/voice-signed-url")
def get_voice_signed_url(movie_id: int, expires_in: int = Query(default=3600, ge=60, le=86400)):
    repository = MoviePipelineRepository()
    try:
        movie = repository.get_movie_by_id(movie_id=movie_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not fetch movie: {exc}") from exc

    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found.")

    storage_path = _get_storage_path(movie)
    if not storage_path:
        raise HTTPException(status_code=404, detail="Voice audio path not found.")

    try:
        signed_url = SupabaseStorageService().create_signed_url(storage_path=storage_path, expires_in=expires_in)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not create signed URL: {exc}") from exc

    return {
        "success": True,
        "movie_id": movie_id,
        "voice_audio_path": movie.get("voice_audio_path"),
        "signed_url": signed_url,
        "expires_in": expires_in,
    }


@router.post("/movies/{movie_id}/approve-processing")
def approve_processing(movie_id: int):
    repository = MoviePipelineRepository()
    try:
        movie = repository.approve_processing(movie_id=movie_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not approve movie: {exc}") from exc

    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found.")
    return {
        "success": True,
        "movie_id": movie_id,
        "is_approved_for_processing": movie["is_approved_for_processing"],
    }


def _get_storage_path(movie: dict) -> str | None:
    voice_data = movie.get("voice_data_json") or {}
    if isinstance(voice_data, dict) and voice_data.get("storage_path"):
        return str(voice_data["storage_path"])

    audio_path = movie.get("voice_audio_path")
    if not audio_path:
        return None

    audio_path = str(audio_path)
    bucket_prefix = f"{settings.supabase_audio_bucket}/"
    if audio_path.startswith(bucket_prefix):
        return audio_path[len(bucket_prefix):]
    if audio_path.startswith("audio/"):
        return audio_path
    return None


def _delete_movie_assets(movie: dict) -> list[str]:
    warnings: list[str] = []
    movie_id = int(movie["id"])

    for path in _iter_local_movie_asset_paths(movie):
        try:
            _delete_local_path(path)
        except Exception as exc:
            warnings.append(f"Could not delete local path '{path}': {exc}")

    voice_storage_path = _get_storage_path(movie)
    if voice_storage_path:
        try:
            SupabaseStorageService().delete_file(storage_path=voice_storage_path)
        except Exception as exc:
            warnings.append(f"Could not delete voice audio from Supabase '{voice_storage_path}': {exc}")

    thumbnail_storage_path = _thumbnail_storage_path(movie.get("thumbnail_path"))
    if thumbnail_storage_path:
        try:
            SupabaseStorageService().delete_file(
                storage_path=thumbnail_storage_path,
                bucket=settings.supabase_thumbnail_bucket,
            )
        except Exception as exc:
            warnings.append(f"Could not delete thumbnail from Supabase '{thumbnail_storage_path}': {exc}")

    for directory in _movie_generated_directories(movie_id):
        try:
            _delete_local_path(directory)
        except Exception as exc:
            warnings.append(f"Could not delete directory '{directory}': {exc}")

    return warnings


def _iter_local_movie_asset_paths(movie: dict) -> list[str]:
    raw_paths: list[str] = []

    for key in (
        "voice_audio_path",
        "source_video_path",
        "master_video_path",
        "draft_video_path",
        "final_video_path",
        "thumbnail_path",
        "poster_local_path",
        "backdrop_local_path",
    ):
        value = movie.get(key)
        if isinstance(value, str) and value.strip():
            raw_paths.append(value.strip())

    source_videos = movie.get("source_videos_json") or []
    if isinstance(source_videos, list):
        for item in source_videos:
            if not isinstance(item, dict):
                continue
            value = item.get("source_video_path")
            if isinstance(value, str) and value.strip():
                raw_paths.append(value.strip())

    deduped: list[str] = []
    seen: set[str] = set()
    for path in raw_paths:
        normalized = path.replace("\\", "/")
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(path)
    return deduped


def _movie_generated_directories(movie_id: int) -> list[str]:
    return [
        f"{settings.video_source_dir}/movie_{movie_id}",
        f"{settings.final_video_dir}/movie_{movie_id}",
        f"{settings.thumbnail_output_dir}/movie_{movie_id}",
        f"{settings.thumbnail_reference_dir}/movie_{movie_id}",
        f"{settings.shorts_temp_dir}/movie_{movie_id}",
        f"{settings.poster_output_dir}/movie_{movie_id}",
    ]


def _delete_local_path(path_value: str) -> None:
    target = _resolve_project_local_path(path_value)
    if not target.exists():
        return
    if target.is_dir():
        shutil.rmtree(target, ignore_errors=False)
        return
    if target.is_file():
        target.unlink()


def _resolve_project_local_path(path_value: str) -> Path:
    candidate = Path(str(path_value))
    resolved = candidate.resolve(strict=False) if candidate.is_absolute() else (PROJECT_ROOT / candidate).resolve(strict=False)
    project_root = PROJECT_ROOT.resolve(strict=False)
    try:
        resolved.relative_to(project_root)
    except ValueError as exc:
        raise ValueError("Path is outside project root.") from exc
    return resolved


def _thumbnail_storage_path(thumbnail_path: str | None) -> str | None:
    if not thumbnail_path:
        return None
    normalized = str(thumbnail_path).strip()
    bucket_prefix = f"{settings.supabase_thumbnail_bucket}/"
    if normalized.startswith(bucket_prefix):
        return normalized[len(bucket_prefix):]
    return None


def _safe_source_label(label: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in label.strip().lower())
    cleaned = cleaned.strip("_")
    return cleaned or "official_trailer"


def _build_frontend_movie_payload(movie: dict) -> dict:
    movie_id = int(movie["id"])
    scene_data = movie.get("scene_data_json") or {}
    render_data = movie.get("render_data_json") or {}
    shorts_data = movie.get("shorts_data_json") or {}
    thumbnail_data = movie.get("thumbnail_data_json") or {}
    source_videos = list(movie.get("source_videos_json") or [])
    error_data = movie.get("error_data_json") or {}
    manual_source_candidates = error_data.get("manual_source_candidates") if isinstance(error_data, dict) else []
    scenes = list(scene_data.get("scenes") or [])
    master_video_path = movie.get("master_video_path")
    draft_video_path = movie.get("draft_video_path")
    final_video_path = movie.get("final_video_path") or draft_video_path
    thumbnail_path = movie.get("thumbnail_path")
    render_status = str(movie.get("render_status") or "")
    scene_status = str(movie.get("scene_status") or "")
    voice_status = str(movie.get("voice_status") or "")
    shorts_status = str(movie.get("shorts_status") or "")
    thumbnail_status = str(movie.get("thumbnail_status") or "")

    preview_url = f"/movies/{movie_id}/master-video-file" if master_video_path else None
    draft_preview_url = f"/movies/{movie_id}/draft-video-file" if draft_video_path else None
    final_preview_url = f"/movies/{movie_id}/final-video-file" if final_video_path else None
    cloudinary_thumbnail_url = thumbnail_data.get("cloudinary_thumbnail_url") if isinstance(thumbnail_data, dict) else None
    cloudinary_video_url = shorts_data.get("cloudinary_video_url") if isinstance(shorts_data, dict) else None
    bgm_data = movie.get("bgm_data_json") or {}
    cloudinary_bgm_url = bgm_data.get("cloudinary_bgm_url") if isinstance(bgm_data, dict) else None
    thumbnail_preview_url = cloudinary_thumbnail_url or (f"/movies/{movie_id}/thumbnail-file" if thumbnail_path else None)
    final_preview_url = cloudinary_video_url or final_preview_url
    run_cut_merge_url = f"/agents/cut-merge/run/{movie_id}?force=true"
    run_scene_selection_url = f"/agents/scene-selection/run/{movie_id}?force=true"
    run_shorts_composer_url = f"/agents/shorts-composer/run/{movie_id}?force=true"
    upload_thumbnail_url = f"/movies/{movie_id}/thumbnail-upload"
    upload_source_video_url = f"/movies/{movie_id}/source-video-url"

    return {
        "success": True,
        "movie": {
            "id": movie_id,
            "tmdb_id": movie.get("tmdb_id"),
            "title": movie.get("movie_title"),
            "release_date": _serialize_value(movie.get("release_date")),
            "poster_url": movie.get("poster_url"),
            "backdrop_url": movie.get("backdrop_url"),
            "discovery_category": movie.get("discovery_category"),
        },
        "pipeline": {
            "overall_status": movie.get("overall_status"),
            "current_agent": movie.get("current_agent"),
            "next_agent": movie.get("next_agent"),
            "progress_percent": movie.get("progress_percent"),
            "is_locked": bool(movie.get("is_locked")),
            "last_error_agent": movie.get("last_error_agent"),
            "last_error_message": movie.get("last_error_message"),
            "updated_at": _serialize_value(movie.get("updated_at")),
        },
        "statuses": {
            "trailer_status": movie.get("trailer_status"),
            "review_status": movie.get("review_status"),
            "script_status": movie.get("script_status"),
            "voice_status": movie.get("voice_status"),
            "video_download_status": movie.get("video_download_status"),
            "scene_status": scene_status,
            "render_status": render_status,
            "shorts_status": shorts_status,
            "thumbnail_status": thumbnail_status,
        },
        "assets": {
            "trailer_url": movie.get("trailer_url"),
            "voice_audio_path": movie.get("voice_audio_path"),
            "source_video_path": movie.get("source_video_path"),
            "source_video_count": len(source_videos),
            "manual_source_candidates": manual_source_candidates or [],
            "master_video_path": master_video_path,
            "master_video_file_url": preview_url,
            "draft_video_path": draft_video_path,
            "draft_video_file_url": draft_preview_url,
            "final_video_path": final_video_path,
            "final_video_file_url": final_preview_url,
            "thumbnail_path": thumbnail_path,
            "thumbnail_file_url": thumbnail_preview_url,
            "cloudinary_bgm_url": cloudinary_bgm_url,
            "cloudinary_thumbnail_url": cloudinary_thumbnail_url,
            "cloudinary_video_url": cloudinary_video_url,
        },
        "source_videos": [
            {
                "label": item.get("label"),
                "type": item.get("type"),
                "source_video_path": item.get("source_video_path"),
                "aspect_ratio": item.get("aspect_ratio"),
                "duration_seconds": item.get("duration_seconds"),
            }
            for item in source_videos
        ],
        "scene_selection": {
            "ready": scene_status == "COMPLETED",
            "scene_count": len(scenes),
            "target_duration_seconds": scene_data.get("target_duration_seconds"),
            "estimated_total_duration_seconds": scene_data.get("estimated_total_duration_seconds"),
            "video_format_for_next_agent": scene_data.get("video_format_for_next_agent"),
            "master_resolution": scene_data.get("master_resolution"),
            "scenes_preview": scenes[:5],
        },
        "render": {
            "ready": render_status == "COMPLETED" and bool(master_video_path),
            "master_video_path": master_video_path,
            "preview_url": preview_url,
            "clip_count": render_data.get("clip_count"),
            "estimated_duration_seconds": render_data.get("estimated_duration_seconds"),
            "transitions_used": render_data.get("transitions_used") or [],
            "warnings": render_data.get("warnings") or [],
        },
        "shorts": {
            "ready": shorts_status == "COMPLETED" and bool(final_video_path),
            "master_video_path": master_video_path,
            "voice_audio_path": movie.get("voice_audio_path"),
            "draft_video_path": draft_video_path,
            "final_video_path": final_video_path,
            "preview_url": final_preview_url,
            "duration_seconds": shorts_data.get("duration_seconds"),
            "layout": shorts_data.get("layout") or {},
            "preprocessing": shorts_data.get("preprocessing") or {},
            "audio_mix": shorts_data.get("audio_mix") or {},
            "warnings": shorts_data.get("warnings") or [],
            "cloudinary_video_url": cloudinary_video_url,
        },
        "thumbnail": {
            "ready": thumbnail_status == "COMPLETED" and bool(thumbnail_path),
            "thumbnail_status": thumbnail_status,
            "thumbnail_path": thumbnail_path,
            "preview_url": thumbnail_preview_url,
            "youtube_title": movie.get("youtube_title"),
            "youtube_description": movie.get("youtube_description"),
            "youtube_tags": list(movie.get("youtube_tags_json") or []) if movie.get("youtube_tags_json") else [],
            "youtube_keywords": list(movie.get("youtube_keywords_json") or []) if movie.get("youtube_keywords_json") else [],
            "style": thumbnail_data.get("style"),
            "text_used": thumbnail_data.get("text_used"),
            "references_used": list(thumbnail_data.get("references_used") or []),
            "foreground_used": thumbnail_data.get("foreground_used"),
            "warnings": list(thumbnail_data.get("warnings") or []),
            "cloudinary_thumbnail_url": cloudinary_thumbnail_url,
        },
        "actions": {
            "can_run_scene_selection": bool(movie.get("voice_audio_path")) and len(source_videos) > 0,
            "can_run_cut_merge": scene_status == "COMPLETED" and len(scenes) > 0,
            "can_run_shorts_composer": bool(thumbnail_path) and thumbnail_status == "COMPLETED" and render_status == "COMPLETED" and bool(master_video_path) and voice_status == "COMPLETED" and bool(movie.get("voice_audio_path")),
            "can_run_thumbnail": False,
            "can_upload_thumbnail": not bool(movie.get("is_locked") or movie.get("current_agent")),
            "can_preview_master_video": bool(preview_url),
            "can_preview_draft_video": bool(draft_preview_url),
            "can_preview_final_video": bool(final_preview_url),
            "can_preview_thumbnail": bool(thumbnail_preview_url),
            "can_upload_source_video_url": voice_status == "COMPLETED",
            "run_scene_selection_url": run_scene_selection_url,
            "run_cut_merge_url": run_cut_merge_url,
            "run_shorts_composer_url": run_shorts_composer_url,
            "run_thumbnail_url": None,
            "upload_thumbnail_url": upload_thumbnail_url,
            "upload_source_video_url": upload_source_video_url,
            "preview_master_video_url": preview_url,
            "preview_draft_video_url": draft_preview_url,
            "preview_final_video_url": final_preview_url,
            "preview_thumbnail_url": thumbnail_preview_url,
        },
        "messages": {
            "video_download": _video_download_message(
                video_download_status=str(movie.get("video_download_status") or ""),
                source_video_count=len(source_videos),
                last_error_message=movie.get("last_error_message"),
                error_data=error_data if isinstance(error_data, dict) else {},
            ),
            "scene": _scene_message(scene_status),
            "render": _render_message(render_status, master_video_path, movie.get("last_error_message")),
            "shorts": _shorts_message(
                render_status=render_status,
                voice_status=voice_status,
                shorts_status=shorts_status,
                final_video_path=final_video_path,
                last_error_message=movie.get("last_error_message"),
            ),
            "thumbnail": _thumbnail_message(
                shorts_status=shorts_status,
                thumbnail_status=thumbnail_status,
                thumbnail_path=thumbnail_path,
                last_error_message=movie.get("last_error_message"),
            ),
        },
        "timeline": list(movie.get("process_timeline_json") or []),
    }


def _scene_message(scene_status: str) -> str:
    if scene_status != "COMPLETED":
        return "Scene selection is not completed yet."
    return "Scene selection is ready."


def _video_download_message(
    video_download_status: str,
    source_video_count: int,
    last_error_message: str | None,
    error_data: dict,
) -> str:
    if source_video_count > 0:
        return "At least one valid source video is ready."
    if error_data.get("manual_source_url_required"):
        return last_error_message or "Auto download could not find a valid 16:9 video. Add a YouTube/source URL or upload an MP4 to continue."
    if video_download_status == "FAILED":
        return last_error_message or "Video download failed. Retry with a different source URL or upload an MP4."
    return "Source video is not ready yet."


def _render_message(render_status: str, master_video_path: str | None, last_error_message: str | None) -> str:
    if render_status == "COMPLETED" and master_video_path:
        return "16:9 master video is ready."
    if render_status == "FAILED":
        return last_error_message or "Master video render failed. Please retry."
    return "Master video is not rendered yet."


def _shorts_message(
    render_status: str,
    voice_status: str,
    shorts_status: str,
    final_video_path: str | None,
    last_error_message: str | None,
) -> str:
    if render_status != "COMPLETED":
        return "16:9 master video is not ready yet."
    if voice_status != "COMPLETED":
        return "Voice audio is not ready yet."
    if shorts_status == "COMPLETED" and final_video_path:
        return "9:16 final Shorts video is ready."
    if shorts_status == "FAILED":
        return last_error_message or "Final Shorts composition failed. Please retry."
    return "Final Shorts video is not composed yet."


def _serialize_value(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _thumbnail_message(shorts_status: str, thumbnail_status: str, thumbnail_path: str | None, last_error_message: str | None) -> str:
    if thumbnail_status == "COMPLETED" and thumbnail_path:
        return "Thumbnail is ready."
    if thumbnail_status == "FAILED":
        return last_error_message or "Thumbnail generation failed. Please retry."
    return "Upload a thumbnail before composing Shorts. It will appear for 2 seconds at the end."


def _next_agent_after_voice_upload() -> str:
    if settings.source_video_mode == "manual":
        return NEXT_AGENT_SCENE_SELECTION
    return NEXT_AGENT_VIDEO_DOWNLOADER


def _overall_status_after_voice_upload() -> str:
    if settings.source_video_mode == "manual":
        return OVERALL_WAITING_SOURCE_VIDEO
    return OVERALL_VOICE_READY


def _thumbnail_content_type(suffix: str) -> str:
    content_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    return content_types.get(suffix, "image/jpeg")


def _tmdb_image_url(path: str | None) -> str | None:
    if not path:
        return None
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"https://image.tmdb.org/t/p/original{path}"


def _release_year(release_date: str | None) -> int | None:
    if not release_date or len(release_date) < 4 or not release_date[:4].isdigit():
        return None
    return int(release_date[:4])


def _raise_tmdb_bad_gateway(exc: Exception) -> None:
    raise HTTPException(status_code=502, detail="TMDB unavailable") from exc


@router.get("/movies/{movie_id}/thumbnail-file")
def get_thumbnail_file(movie_id: int):
    repository = MoviePipelineRepository()
    try:
        movie = repository.get_movie_by_id(movie_id=movie_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not fetch movie: {exc}") from exc

    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found.")

    thumbnail_path = movie.get("thumbnail_path")
    if not thumbnail_path:
        raise HTTPException(status_code=404, detail="Thumbnail not found.")

    local_path = Path(str(thumbnail_path))
    if not local_path.is_absolute():
        local_path = PROJECT_ROOT / local_path

    if local_path.exists() and local_path.is_file():
        return FileResponse(path=local_path, media_type=_thumbnail_content_type(local_path.suffix.lower()), filename=local_path.name)

    thumbnail_data = movie.get("thumbnail_data_json") or {}
    cloudinary_url = thumbnail_data.get("cloudinary_thumbnail_url") if isinstance(thumbnail_data, dict) else None
    if cloudinary_url:
        return RedirectResponse(url=str(cloudinary_url))

    # Supabase signed URL or redirect
    bucket_prefix = f"{settings.supabase_thumbnail_bucket}/"
    storage_path = str(thumbnail_path)
    if storage_path.startswith(bucket_prefix):
        storage_path = storage_path[len(bucket_prefix):]

    try:
        storage_service = SupabaseStorageService()
        # Temp change bucket to thumbnail bucket, get signed url, restore bucket
        original_bucket = storage_service.bucket
        storage_service.bucket = settings.supabase_thumbnail_bucket
        storage_service.storage = storage_service.client.storage.from_(settings.supabase_thumbnail_bucket)
        try:
            signed_url = storage_service.create_signed_url(storage_path=storage_path, expires_in=600)
        finally:
            storage_service.bucket = original_bucket
            storage_service.storage = storage_service.client.storage.from_(original_bucket)
            
        return RedirectResponse(url=signed_url)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not get thumbnail from Supabase: {exc}") from exc

