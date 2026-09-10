from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.config import PROJECT_ROOT, settings


class FFmpegRenderService:
    def __init__(self) -> None:
        self.ffmpeg_binary = self._resolve_binary(settings.ffmpeg_binary, "ffmpeg")
        self.ffprobe_binary = self._resolve_binary(settings.ffprobe_binary, "ffprobe")

    def cut_scene_clip(
        self,
        source_video_path: str,
        start: str,
        end: str,
        output_path: str,
        resolution: str,
        fps: int,
        speed: str = "normal",
        zoom: str = "none",
    ) -> dict:
        source_path = self._resolve_local_path(source_video_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Source video not found: {source_video_path}")

        output = self._resolve_local_path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        width, height = self._parse_resolution(resolution)
        source_duration = max(self._calculate_duration_seconds(start, end), 0.01)
        speed_multiplier = self._speed_multiplier(speed)
        output_duration = round(source_duration / speed_multiplier, 3)

        vf_parts = [
            f"scale={width}:{height}:force_original_aspect_ratio=increase",
            f"crop={width}:{height}",
            f"fps={int(fps)}",
        ]
        if self._zoom_supported(zoom):
            vf_parts.append(self._zoom_filter(zoom, width, height))
        if speed_multiplier != 1.0:
            vf_parts.append(f"setpts={1 / speed_multiplier:.6f}*PTS")
        vf_parts.append("format=yuv420p")

        command = [
            self.ffmpeg_binary,
            "-y",
            "-ss",
            start,
            "-to",
            end,
            "-i",
            str(source_path),
            "-an",
            "-vf",
            ",".join(vf_parts),
            "-c:v",
            "libx264",
            "-preset",
            settings.master_video_preset,
            "-crf",
            str(settings.master_video_crf),
        ]

        command.extend(
            [
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output),
            ]
        )

        self._run_subprocess(command)
        return {
            "output_path": self._to_relative_path(output),
            "start": start,
            "end": end,
            "duration_seconds": output_duration,
            "speed": speed,
            "zoom": zoom,
            "success": True,
        }

    def create_flash_clip(
        self,
        output_path: str,
        color: str,
        duration_seconds: float,
        resolution: str,
        fps: int,
    ) -> dict:
        output = self._resolve_local_path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        width, height = self._parse_resolution(resolution)
        safe_duration = max(round(float(duration_seconds), 3), 0.01)
        command = [
            self.ffmpeg_binary,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s={width}x{height}:r={int(fps)}:d={safe_duration}",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            settings.master_video_preset,
            "-crf",
            str(settings.master_video_crf),
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ]
        self._run_subprocess(command)
        return {
            "output_path": self._to_relative_path(output),
            "color": color,
            "duration_seconds": safe_duration,
            "success": True,
        }

    def merge_clips_simple(self, clip_paths: list, output_path: str) -> dict:
        if not clip_paths:
            raise ValueError("No clips were provided for merging.")

        output = self._resolve_local_path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        concat_file = output.parent / f"{output.stem}_concat.txt"
        concat_file.write_text(
            "".join(f"file '{self._resolve_local_path(path).as_posix()}'\n" for path in clip_paths),
            encoding="utf-8",
        )
        command = [
            self.ffmpeg_binary,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            settings.master_video_preset,
            "-crf",
            str(settings.master_video_crf),
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ]
        try:
            self._run_subprocess(command)
        finally:
            concat_file.unlink(missing_ok=True)
        return {
            "output_path": self._to_relative_path(output),
            "clip_count": len(clip_paths),
            "success": True,
        }

    def render_master_video(self, movie_id: int, scene_plan: dict, output_dir: str) -> dict:
        scenes = list(scene_plan.get("scenes") or [])
        if not scenes:
            raise ValueError("Scene selection JSON does not contain any scenes.")

        resolution = scene_plan.get("master_resolution") or settings.master_video_resolution
        fps = int(settings.master_video_fps)
        temp_dir = self._resolve_local_path(settings.temp_clip_dir) / f"movie_{movie_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)

        output_directory = self._resolve_local_path(output_dir)
        output_directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        master_filename = f"movie_{movie_id}_master_16x9_{timestamp}.mp4"
        master_output = output_directory / master_filename

        warnings: list[str] = []
        transitions_used: list[str] = []
        ordered_scenes = sorted(scenes, key=lambda item: int(item.get("order", 0)))
        merge_inputs: list[str] = []
        clip_metadata: list[dict] = []

        try:
            for index, scene in enumerate(ordered_scenes, start=1):
                clip_output = temp_dir / f"clip_{int(scene.get('order', index)):02d}.mp4"
                zoom = str(scene.get("zoom") or "none")
                speed = str(scene.get("speed") or "normal")
                clip_result = self.cut_scene_clip(
                    source_video_path=str(scene.get("source_video_path") or ""),
                    start=str(scene.get("start") or ""),
                    end=str(scene.get("end") or ""),
                    output_path=str(clip_output),
                    resolution=resolution,
                    fps=fps,
                    speed=speed,
                    zoom=zoom,
                )
                if zoom not in {"", "none"} and not self._zoom_supported(zoom):
                    warnings.append(f"Zoom '{zoom}' not applied for scene {scene.get('order', index)}; used normal framing.")
                clip_metadata.append(clip_result)
                merge_inputs.append(clip_result["output_path"])

                if index >= len(ordered_scenes):
                    continue

                transition_name = self._normalize_transition(scene.get("transition_after"))
                transition_duration = float(scene.get("transition_duration_seconds") or 0.0)
                fallback_transition = transition_name

                if transition_name == "crossfade":
                    warnings.append("Crossfade requested but falling back to hard cut for stable rendering.")
                    fallback_transition = "cut"
                elif transition_name in {"glitch", "whip_pan"}:
                    warnings.append(f"Transition '{transition_name}' is not supported yet; falling back safely.")
                    fallback_transition = "flash_cut"

                flash_color = None
                if fallback_transition == "flash_cut":
                    flash_color = "white"
                elif fallback_transition == "black_flash":
                    flash_color = "black"

                if flash_color:
                    flash_duration = self._transition_duration(fallback_transition, transition_duration)
                    flash_output = temp_dir / f"transition_{int(scene.get('order', index)):02d}_{fallback_transition}.mp4"
                    flash_result = self.create_flash_clip(
                        output_path=str(flash_output),
                        color=flash_color,
                        duration_seconds=flash_duration,
                        resolution=resolution,
                        fps=fps,
                    )
                    merge_inputs.append(flash_result["output_path"])
                    transitions_used.append(fallback_transition)
                elif fallback_transition in {"cut", "zoom_cut"}:
                    transitions_used.append("cut")

            merge_result = self.merge_clips_simple(merge_inputs, str(master_output))
            duration_seconds = self._probe_duration_seconds(master_output)
            return {
                "master_video_path": merge_result["output_path"],
                "clip_count": len(clip_metadata),
                "estimated_duration_seconds": duration_seconds,
                "resolution": resolution,
                "fps": fps,
                "transitions_used": transitions_used,
                "warnings": warnings,
                "clips": clip_metadata,
                "video_format_for_next_agent": scene_plan.get("video_format_for_next_agent", "16:9"),
                "target_duration_seconds": scene_plan.get("target_duration_seconds"),
            }
        finally:
            if not settings.render_keep_temp_clips:
                shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def _calculate_duration_seconds(start: str, end: str) -> float:
        return round(FFmpegRenderService._parse_timestamp(end) - FFmpegRenderService._parse_timestamp(start), 3)

    @staticmethod
    def _parse_timestamp(value: str) -> float:
        parts = str(value).split(":")
        if len(parts) != 3:
            raise ValueError(f"Invalid timestamp: {value}")
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds

    @staticmethod
    def _parse_resolution(resolution: str) -> tuple[int, int]:
        try:
            width_text, height_text = str(resolution).lower().split("x", maxsplit=1)
            return int(width_text), int(height_text)
        except Exception as exc:
            raise ValueError(f"Invalid resolution: {resolution}") from exc

    @staticmethod
    def _speed_multiplier(speed: str) -> float:
        normalized = str(speed or "normal").strip().lower()
        if normalized in {"normal", ""}:
            return 1.0
        if normalized in {"1.10x", "1.1x"}:
            return 1.10
        if normalized == "1.25x":
            return 1.25
        if normalized == "slow_motion":
            return 0.85
        return 1.0

    @staticmethod
    def _zoom_supported(zoom: str) -> bool:
        return str(zoom or "none").strip().lower() in {"slow_zoom_in", "slow_zoom_out", "punch_zoom"}

    @staticmethod
    def _zoom_filter(zoom: str, width: int, height: int) -> str:
        normalized = str(zoom or "none").strip().lower()
        if normalized == "slow_zoom_in":
            return f"zoompan=z='min(zoom+0.0015,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={width}x{height}:fps={settings.master_video_fps}"
        if normalized == "slow_zoom_out":
            return f"zoompan=z='if(lte(on,1),1.12,max(zoom-0.0015,1.0))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={width}x{height}:fps={settings.master_video_fps}"
        if normalized == "punch_zoom":
            return f"zoompan=z='if(lte(on,2),1.18,1.0)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={width}x{height}:fps={settings.master_video_fps}"
        return "null"

    @staticmethod
    def _normalize_transition(transition_name: str | None) -> str:
        normalized = str(transition_name or "cut").strip().lower()
        if not normalized:
            return "cut"
        return normalized

    @staticmethod
    def _transition_duration(transition_name: str, requested_duration: float) -> float:
        if transition_name == "flash_cut":
            return max(0.08, min(requested_duration or 0.12, 0.15))
        if transition_name == "black_flash":
            return max(0.08, min(requested_duration or 0.12, 0.20))
        return 0.0

    def _probe_duration_seconds(self, path: Path) -> float:
        command = [
            self.ffprobe_binary,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ]
        result = self._run_subprocess(command, capture_json=True)
        duration = ((result or {}).get("format") or {}).get("duration")
        try:
            return round(float(duration), 3)
        except (TypeError, ValueError):
            return 0.0

    def _run_subprocess(self, command: list[str], capture_json: bool = False) -> dict | None:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "Subprocess command failed.").strip()
            raise RuntimeError(stderr[-4000:])
        if capture_json:
            return json.loads(result.stdout or "{}")
        return None

    @staticmethod
    def _resolve_local_path(path_str: str) -> Path:
        path = Path(path_str)
        if path.is_absolute():
            return path
        return PROJECT_ROOT / path

    @staticmethod
    def _to_relative_path(path: Path) -> str:
        try:
            return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
        except ValueError:
            return str(path).replace("\\", "/")

    @staticmethod
    def _resolve_binary(configured_path: str, command_name: str) -> str:
        if configured_path:
            path = Path(configured_path)
            if path.exists():
                return str(path)
            resolved = shutil.which(configured_path)
            if resolved:
                return resolved
        resolved = shutil.which(command_name)
        if resolved:
            return resolved
        raise ValueError(f"{command_name} executable is not available. Install it and make sure it is in PATH.")
