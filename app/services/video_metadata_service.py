import json
import subprocess
from pathlib import Path

from app.config import PROJECT_ROOT, settings


class VideoMetadataService:
    def get_video_metadata(self, video_path: str) -> dict:
        path = self._resolve_local_path(video_path)
        if not path.exists():
            raise ValueError(f"Source video not found: {video_path}")
        if not settings.ffprobe_binary:
            raise ValueError("FFPROBE_BINARY is not configured or ffprobe is unavailable.")

        probe_data = self._run_ffprobe(path)
        stream = self._pick_video_stream(probe_data)
        if not isinstance(stream, dict):
            raise ValueError(f"Could not detect a video stream for: {video_path}")

        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
        if not width or not height:
            raise ValueError(f"Could not detect video dimensions for: {video_path}")

        format_info = probe_data.get("format") or {}
        duration_raw = format_info.get("duration") or stream.get("duration") or 0.0
        try:
            duration_seconds = float(duration_raw or 0.0)
        except (TypeError, ValueError):
            duration_seconds = 0.0

        aspect_ratio_value = round(float(width) / float(height), 3)
        return {
            "width": width,
            "height": height,
            "duration_seconds": round(duration_seconds, 3),
            "aspect_ratio_value": aspect_ratio_value,
            "aspect_ratio": self._aspect_ratio_label(aspect_ratio_value),
        }

    def validate_16x9_source_video(self, video_path: str) -> dict:
        path = self._resolve_local_path(video_path)
        if path.suffix.lower() != ".mp4":
            return {
                "valid": False,
                "metadata": None,
                "message": "Only MP4 files are allowed.",
            }

        try:
            metadata = self.get_video_metadata(video_path=video_path)
        except Exception as exc:
            return {
                "valid": False,
                "metadata": None,
                "message": str(exc),
            }

        width = metadata["width"]
        height = metadata["height"]
        aspect_ratio_value = metadata["aspect_ratio_value"]

        if width < height or aspect_ratio_value < 1.30:
            return {
                "valid": False,
                "metadata": metadata,
                "message": "Only 16:9 trailer/teaser videos are allowed. Shorts/Reels/vertical videos are not allowed as source videos.",
            }

        if not (
            settings.source_video_min_aspect_ratio
            <= aspect_ratio_value
            <= settings.source_video_max_aspect_ratio
        ):
            return {
                "valid": False,
                "metadata": metadata,
                "message": "Only 16:9 trailer/teaser videos are allowed. Shorts/Reels/vertical videos are not allowed as source videos.",
            }

        return {
            "valid": True,
            "metadata": metadata,
            "message": "valid 16:9 video",
        }

    @staticmethod
    def _resolve_local_path(video_path: str) -> Path:
        path = Path(video_path)
        if path.is_absolute():
            return path
        return PROJECT_ROOT / path

    @staticmethod
    def _aspect_ratio_label(aspect_ratio_value: float) -> str:
        if 1.70 <= aspect_ratio_value <= 1.85:
            return "16:9"
        return f"{aspect_ratio_value:.3f}:1"

    @staticmethod
    def _pick_video_stream(probe_data: dict) -> dict | None:
        streams = probe_data.get("streams") or []
        if not isinstance(streams, list):
            return None
        for stream in streams:
            if isinstance(stream, dict) and stream.get("codec_type") == "video":
                return stream
        return None

    @staticmethod
    def _run_ffprobe(path: Path) -> dict:
        command = [
            settings.ffprobe_binary,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=30)
        except FileNotFoundError as exc:
            raise ValueError("ffprobe is unavailable.") from exc
        except subprocess.TimeoutExpired as exc:
            raise ValueError("ffprobe timed out while reading the source video.") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise ValueError(stderr or "ffprobe could not read the source video.") from exc

        try:
            return json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise ValueError("ffprobe returned invalid metadata output.") from exc
