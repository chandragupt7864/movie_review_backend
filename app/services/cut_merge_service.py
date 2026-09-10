from app.config import settings
from app.services.ffmpeg_render_service import FFmpegRenderService


class CutMergeService(FFmpegRenderService):
    def create_master_video(self, scenes: list[dict], output_path: str, target_fps: int | None = None) -> str:
        del target_fps
        output = self._resolve_local_path(output_path)
        result = self.render_master_video(
            movie_id=0,
            scene_plan={"scenes": scenes, "master_resolution": settings.master_video_resolution},
            output_dir=str(output.parent),
        )
        rendered_path = self._resolve_local_path(result["master_video_path"])
        rendered_path.replace(output)
        return self._to_relative_path(output)
