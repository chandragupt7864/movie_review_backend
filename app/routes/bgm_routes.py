from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.config import settings
from app.repositories.bgm_library_repository import BGMLibraryRepository
from app.services.bgm_library_service import BGMLibraryService
from app.services.supabase_storage_service import SupabaseStorageService


router = APIRouter()


@router.post("/bgm/api/upload")
def upload_bgm_track(file: UploadFile = File(...)):
    try:
        payload = BGMLibraryService().upload_track(file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"BGM upload failed: {exc}") from exc
    finally:
        file.file.close()

    return {
        "success": True,
        "already_exists": payload["already_exists"],
        "track": BGMLibraryService.serialize_track(payload["track"]),
    }


@router.get("/bgm/api/list")
def list_bgm_tracks(
    q: str | None = Query(default=None),
    copyright_status: str | None = Query(default=None),
    analysis_status: str | None = Query(default=None),
    recognition_status: str | None = Query(default=None),
    recognized: bool | None = Query(default=None),
    artist: str | None = Query(default=None),
    duration_min: float | None = Query(default=None),
    duration_max: float | None = Query(default=None),
    bpm_min: float | None = Query(default=None),
    bpm_max: float | None = Query(default=None),
    tempo_category: str | None = Query(default=None),
    energy_level: str | None = Query(default=None),
    is_instrumental: bool | None = Query(default=None),
    mood: str | None = Query(default=None),
    genre: str | None = Query(default=None),
    sort_by: str = Query(default="created_at.desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    repository = BGMLibraryRepository()
    try:
        result = repository.list_bgm_tracks(
            {
                "q": q,
                "copyright_status": copyright_status,
                "analysis_status": analysis_status,
                "recognition_status": recognition_status,
                "recognized": recognized,
                "artist": artist,
                "duration_min": duration_min,
                "duration_max": duration_max,
                "bpm_min": bpm_min,
                "bpm_max": bpm_max,
                "tempo_category": tempo_category,
                "energy_level": energy_level,
                "is_instrumental": is_instrumental,
                "mood": mood,
                "genre": genre,
                "sort_by": sort_by,
                "page": page,
                "page_size": page_size,
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not list BGM tracks: {exc}") from exc

    return {
        "success": True,
        "filters": result["filters"],
        "pagination": result["pagination"],
        "tracks": [BGMLibraryService.serialize_track(row) for row in result["tracks"]],
    }


@router.get("/bgm/api/filter-options")
def get_bgm_filter_options():
    try:
        payload = BGMLibraryRepository().get_bgm_filter_options()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not fetch filter options: {exc}") from exc
    return {"success": True, **payload}


@router.get("/bgm/api/stats")
def get_bgm_stats():
    try:
        payload = BGMLibraryRepository().get_bgm_stats()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not fetch BGM stats: {exc}") from exc
    return {"success": True, **payload}


@router.get("/bgm/api/{track_id}")
def get_bgm_track(track_id: int):
    try:
        row = BGMLibraryRepository().get_bgm_by_id(track_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not fetch BGM track: {exc}") from exc
    if not row:
        raise HTTPException(status_code=404, detail="Track not found.")
    return {"success": True, "track": BGMLibraryService.serialize_detail(row)}


@router.get("/bgm/api/{track_id}/play-url")
def get_bgm_play_url(track_id: int):
    repository = BGMLibraryRepository()
    try:
        row = repository.get_bgm_by_id(track_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not fetch BGM track: {exc}") from exc
    if not row:
        raise HTTPException(status_code=404, detail="Track not found.")
    if not row.get("storage_path"):
        raise HTTPException(status_code=404, detail="Track storage path not found.")

    if row.get("storage_bucket") == "cloudinary" or str(row["storage_path"]).startswith("https://"):
        return {
            "success": True,
            "track_id": track_id,
            "signed_url": str(row["storage_path"]),
            "expires_in_seconds": None,
        }

    try:
        signed_url = SupabaseStorageService().create_signed_url(
            storage_path=str(row["storage_path"]),
            expires_in=settings.bgm_signed_url_expires_seconds,
            bucket=str(row.get("storage_bucket") or settings.supabase_bgm_bucket),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not create BGM signed URL: {exc}") from exc

    return {
        "success": True,
        "track_id": track_id,
        "signed_url": signed_url,
        "expires_in_seconds": settings.bgm_signed_url_expires_seconds,
    }


@router.post("/bgm/api/{track_id}/reanalyze")
def reanalyze_bgm_track(track_id: int):
    try:
        row = BGMLibraryService().reanalyze_track(track_id)
    except ValueError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not reanalyze BGM track: {exc}") from exc
    return {"success": True, "track": BGMLibraryService.serialize_detail(row)}
