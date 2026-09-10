from fastapi import APIRouter, HTTPException

from app.services.manual_pipeline_controller import manual_pipeline_controller


router = APIRouter()


@router.get("/status")
def get_pipeline_control_status():
    return {"success": True, "controller": manual_pipeline_controller.status()}


@router.post("/start")
def start_global_pipeline():
    try:
        return {"success": True, "controller": manual_pipeline_controller.start_global()}
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/start/{movie_id}")
def start_movie_pipeline(movie_id: int):
    try:
        return {"success": True, "controller": manual_pipeline_controller.start_movie(movie_id=movie_id)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/stop")
def stop_pipeline():
    return {"success": True, "controller": manual_pipeline_controller.stop()}
