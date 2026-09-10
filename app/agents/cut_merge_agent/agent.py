from pathlib import Path

from app.agents.cut_merge_agent.schema import CutMergeResult, CutMergeRunResponse
from app.config import settings
from app.core.agent_status import (
    CURRENT_AGENT_CUT_MERGE,
    NEXT_AGENT_CUT_MERGE,
    NEXT_AGENT_SHORTS_COMPOSER,
    OVERALL_MASTER_VIDEO_READY,
    RENDER_COMPLETED,
    RENDER_FAILED,
    SCENE_COMPLETED,
)
from app.core.pipeline_utils import build_timeline_event


class CutMergeAgent:
    agent_name = CURRENT_AGENT_CUT_MERGE

    def __init__(self, repository, cut_merge_service) -> None:
        self.repository = repository
        self.cut_merge_service = cut_merge_service

    def run(self, limit: int = 1) -> dict:
        jobs = self.repository.get_pending_cut_merge_jobs(limit=limit)
        return self._run_jobs(jobs)

    def run_for_movie(self, movie_id: int, force: bool = False) -> dict:
        movie = self.repository.get_movie_by_id(movie_id=movie_id)
        if not movie:
            result = CutMergeResult(movie_id=movie_id, status=RENDER_FAILED, error="Movie not found.")
            return CutMergeRunResponse(processed=0, completed=0, failed=1, results=[result]).model_dump()
        return self._run_jobs([movie], force=force)

    def _run_jobs(self, jobs: list[dict], force: bool = False) -> dict:
        results: list[CutMergeResult] = []
        completed = 0
        failed = 0
        for movie in jobs:
            result = self._process_movie(movie, force=force)
            results.append(result)
            if result.status == RENDER_COMPLETED:
                completed += 1
            else:
                failed += 1
        return CutMergeRunResponse(
            processed=len(jobs),
            completed=completed,
            failed=failed,
            results=results,
        ).model_dump()

    def _process_movie(self, movie: dict, force: bool = False) -> CutMergeResult:
        movie_id = int(movie["id"])
        tmdb_id = movie.get("tmdb_id")
        title = movie.get("movie_title")
        eligibility_error = self._eligibility_error(movie, force=force)
        if eligibility_error:
            return CutMergeResult(movie_id=movie_id, tmdb_id=tmdb_id, title=title, status=RENDER_FAILED, error=eligibility_error)

        locked_movie = self.repository.lock_movie_for_agent(movie_id=movie_id, agent_name=self.agent_name)
        if not locked_movie:
            return CutMergeResult(movie_id=movie_id, tmdb_id=tmdb_id, title=title, status=RENDER_FAILED, error="Movie is already locked or inactive.")

        try:
            scene_data = locked_movie.get("scene_data_json") or {}
            scenes = list(scene_data.get("scenes") or [])
            if not scenes:
                raise ValueError("Scene selection JSON does not contain any scenes.")
            output_dir = Path(settings.final_video_dir) / f"movie_{movie_id}"
            render_result = self.cut_merge_service.render_master_video(
                movie_id=movie_id,
                scene_plan=scene_data,
                output_dir=str(output_dir),
            )
            master_video_path = render_result["master_video_path"]
            self.repository.update_cut_merge_success(
                movie_id=movie_id,
                render_payload={
                    "master_video_path": master_video_path,
                    "render_data": {
                        **render_result,
                        "scene_count": len(scenes),
                        "source_videos_used": scene_data.get("source_videos_used") or [],
                        "next_agent": NEXT_AGENT_SHORTS_COMPOSER,
                        "overall_status": OVERALL_MASTER_VIDEO_READY,
                    },
                    "timeline_event": build_timeline_event(
                        agent=self.agent_name,
                        status=RENDER_COMPLETED,
                        message="16:9 master video rendered successfully from selected scenes",
                        data={"tmdb_id": tmdb_id, "master_video_path": master_video_path, "clip_count": render_result.get("clip_count")},
                    ),
                },
            )
            return CutMergeResult(
                movie_id=movie_id,
                tmdb_id=tmdb_id,
                title=title,
                status=RENDER_COMPLETED,
                master_video_path=master_video_path,
                clip_count=render_result.get("clip_count"),
                transitions_used=list(render_result.get("transitions_used") or []),
            )
        except Exception as exc:
            self.repository.update_cut_merge_failed(
                movie_id=movie_id,
                error_payload={
                    "error_message": str(exc),
                    "error_data": {"tmdb_id": tmdb_id, "title": title, "error_type": type(exc).__name__, "error_message": str(exc)},
                    "timeline_event": build_timeline_event(
                        agent=self.agent_name,
                        status=RENDER_FAILED,
                        message=str(exc),
                        data={"tmdb_id": tmdb_id},
                    ),
                },
            )
            return CutMergeResult(movie_id=movie_id, tmdb_id=tmdb_id, title=title, status=RENDER_FAILED, error=str(exc))

    @staticmethod
    def _eligibility_error(movie: dict, force: bool = False) -> str | None:
        if not movie.get("is_active", True):
            return "Movie is inactive."
        if movie.get("is_locked"):
            return "Movie is already locked."
        if not force and movie.get("next_agent") != NEXT_AGENT_CUT_MERGE:
            return "Movie is not queued for cut merge."
        if str(movie.get("scene_status") or "") != SCENE_COMPLETED:
            return "Movie scenes are not ready."
        if not movie.get("scene_data_json"):
            return "Scene selection JSON is missing."
        return None
