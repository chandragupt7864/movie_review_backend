from __future__ import annotations

import json
import re
import subprocess
from uuid import uuid4
from app.services.shorts_appearance import ShortsAppearance
from datetime import datetime, timezone
from pathlib import Path

from app.config import PROJECT_ROOT, settings
from app.services.ffmpeg_render_service import FFmpegRenderService
from app.services.supabase_storage_service import SupabaseStorageService

try:
    from mutagen import File as MutagenFile
except ModuleNotFoundError:  # pragma: no cover
    MutagenFile = None


class ShortsComposerService(FFmpegRenderService):
    def __init__(self, storage_service: SupabaseStorageService | None = None) -> None:
        super().__init__()
        self.storage_service = storage_service

    def get_media_duration(self, path: str) -> float:
        local_path = self._resolve_local_path(path)
        if local_path.exists():
            return self._probe_duration_seconds(local_path)
        raise FileNotFoundError(f"Media file not found: {path}")

    def download_voice_if_needed(self, movie_id: int, voice_audio_path: str) -> str:
        local_candidate = self._resolve_local_path(voice_audio_path)
        if local_candidate.exists():
            return self._to_relative_path(local_candidate)

        storage_path = self._extract_storage_path(voice_audio_path)
        if not storage_path:
            raise FileNotFoundError(f"Voice audio not found locally: {voice_audio_path}")

        storage_service = self._get_storage_service()
        temp_dir = self._resolve_local_path(settings.shorts_temp_dir) / f"movie_{movie_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / "voice.mp3"
        storage_service.download_file(storage_path=storage_path, local_file_path=str(temp_path))
        return self._to_relative_path(temp_path)

    def compose_shorts_draft(
        self,
        movie_id: int,
        master_video_path: str,
        voice_audio_path: str,
        output_path: str,
        bgm_path: str | None = None,
        thumbnail_path: str | None = None,
        appearance: dict | None = None,
    ) -> dict:
        look = ShortsAppearance.model_validate(appearance or {})
        master_path = self._resolve_local_path(master_video_path)
        if not master_path.exists():
            raise FileNotFoundError(f"Master video not found: {master_video_path}")

        resolved_voice_path = self.download_voice_if_needed(movie_id=movie_id, voice_audio_path=voice_audio_path)
        voice_path = self._resolve_local_path(resolved_voice_path)
        if not voice_path.exists():
            raise FileNotFoundError(f"Voice audio not found: {resolved_voice_path}")

        output = self._resolve_local_path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        master_duration = self._probe_duration_seconds(master_path)
        voice_duration = self._probe_audio_duration_seconds(voice_path)
        if master_duration <= 0:
            raise ValueError("Master video duration could not be determined.")
        if voice_duration <= 0:
            raise ValueError("Voice audio duration could not be determined.")

        warnings: list[str] = []
        crop_info = self.detect_crop_area(master_video_path=self._to_relative_path(master_path))
        if crop_info.get("warning"):
            warnings.append(str(crop_info["warning"]))
        applied_foreground_width = (
            settings.shorts_foreground_width_with_crop
            if crop_info.get("crop_applied")
            else settings.shorts_foreground_width_no_crop
        )
        applied_zoom = (
            settings.shorts_foreground_zoom_with_crop
            if crop_info.get("crop_applied")
            else settings.shorts_foreground_zoom_base
        )
        output_duration = master_duration
        if voice_duration > master_duration:
            output_duration = voice_duration
            warnings.append("Voice audio is longer than master video; extended final frame to match voice duration.")

        bgm_enabled = bool(settings.bgm_enabled)
        resolved_bgm_path: str | None = None
        bgm_exists = False
        if bgm_enabled and bgm_path:
            bgm_candidate = self._resolve_local_path(bgm_path)
            if bgm_candidate.exists():
                resolved_bgm_path = self._to_relative_path(bgm_candidate)
                bgm_exists = True
            else:
                warnings.append(f"Background music file was not found and was skipped: {bgm_path}")
        elif bgm_enabled:
            warnings.append("Background music is enabled but no default BGM file was configured.")

        content_duration = output_duration
        end_card_duration = 2.0 if thumbnail_path else 0.0
        thumbnail_local = self._resolve_local_path(thumbnail_path) if thumbnail_path else None
        if thumbnail_local and not thumbnail_local.is_file():
            raise FileNotFoundError(f"Thumbnail image not found: {thumbnail_path}. Upload it again.")
        output_duration += end_card_duration

        fade_out_seconds = min(max(settings.bgm_fade_out_seconds, 0.0), output_duration)
        fade_start = max(output_duration - fade_out_seconds, 0.0)
        stop_pad_duration = max(content_duration - master_duration, 0.0)
        filter_parts = [
            self.build_video_filter(
                crop_info=crop_info,
                shorts_width=settings.shorts_width,
                shorts_height=settings.shorts_height,
                foreground_width=applied_foreground_width,
                foreground_zoom=applied_zoom,
                background_blur=settings.shorts_background_blur,
                background_darkness=settings.shorts_background_darkness,
                foreground_y_offset=settings.shorts_foreground_y_offset,
                stop_pad_duration=stop_pad_duration,
            ),
            f"[1:a]volume={settings.voice_volume},apad=pad_dur={output_duration:.3f},atrim=0:{output_duration:.3f}[voice]",
        ]

        command = [
            self.ffmpeg_binary,
            "-y",
            "-i",
            str(master_path),
            "-i",
            str(voice_path),
        ]

        if bgm_exists and resolved_bgm_path:
            bgm_local_path = self._resolve_local_path(resolved_bgm_path)
            filter_parts.append(
                f"[2:a]volume={settings.bgm_volume},afade=t=out:st={fade_start:.3f}:d={fade_out_seconds:.3f},atrim=0:{output_duration:.3f}[bgm]"
            )
            filter_parts.append("[voice][bgm]amix=inputs=2:duration=longest:dropout_transition=2,aresample=async=1:first_pts=0[a]")
            command.extend(["-stream_loop", "-1", "-i", str(bgm_local_path)])
        else:
            filter_parts.append("[voice]aresample=async=1:first_pts=0[a]")

        if thumbnail_local:
            image_index = 3 if bgm_exists else 2
            command.extend(["-loop", "1", "-framerate", str(settings.shorts_fps), "-i", str(thumbnail_local)])
            width, height, fps = settings.shorts_width, settings.shorts_height, settings.shorts_fps
            filter_parts.extend([
                f"[v]trim=duration={content_duration:.3f},setpts=PTS-STARTPTS,fps={fps},setsar=1,format=yuv420p[content]",
                f"[{image_index}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={fps},format=yuv420p,trim=duration={end_card_duration:.3f},setpts=PTS-STARTPTS[endcard]",
                "[content][endcard]concat=n=2:v=1:a=0[vfinal]",
            ])

        source_label = "vfinal" if thumbnail_local else "v"
        filter_parts.append(f"[{source_label}]null[styled]")
        preview_output = output.with_name(output.stem + "_preview.mp4")

        command.extend(
            [
                "-filter_complex",
                ";".join(filter_parts),
                "-map",
                "[styled]",
                "-map",
                "[a]",
                "-t",
                f"{output_duration:.3f}",
                "-r",
                str(settings.shorts_fps),
                "-c:v",
                "libx264",
                "-preset",
                settings.shorts_video_preset,
                "-crf",
                str(settings.shorts_video_crf),
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(preview_output),
            ]
        )

        self._run_subprocess(command)
        if look == ShortsAppearance():
            import shutil
            shutil.copyfile(preview_output, output)
        else:
            self._run_subprocess([
                self.ffmpeg_binary, "-y", "-i", str(preview_output),
                "-vf", look.video_filter(), "-c:v", "libx264",
                "-preset", settings.shorts_video_preset, "-crf", str(settings.shorts_video_crf),
                "-c:a", "copy", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
            ])

        output_duration_actual = self._probe_duration_seconds(output)
        final_video_path = self._to_relative_path(output) if settings.shorts_set_final_video_path else None
        return {
            "preview_base_path": self._to_relative_path(preview_output),
            "appearance": look.model_dump(),
            "thumbnail_end_card": {"path": thumbnail_path, "duration_seconds": end_card_duration, "starts_at_seconds": content_duration},
            "draft_video_path": self._to_relative_path(output),
            "final_video_path": final_video_path,
            "master_video_path": self._to_relative_path(master_path),
            "voice_audio_path": resolved_voice_path,
            "bgm_path": resolved_bgm_path,
            "duration_seconds": output_duration_actual or round(output_duration, 3),
            "master_duration_seconds": master_duration,
            "voice_duration_seconds": voice_duration,
            "resolution": f"{settings.shorts_width}x{settings.shorts_height}",
            "fps": settings.shorts_fps,
            "layout": {
                "background": "blurred cropped video full screen",
                "foreground": "cropped, zoomed, centered video",
                "foreground_width": applied_foreground_width,
                "foreground_x_alignment": "center" if settings.shorts_foreground_x_center else "custom",
                "foreground_y_alignment": "center" if settings.shorts_foreground_y_center else "custom",
                "foreground_y_offset": settings.shorts_foreground_y_offset,
            },
            "preprocessing": {
                "black_bar_detection_enabled": True,
                "has_black_bars": bool(crop_info.get("has_black_bars")),
                "crop_applied": bool(crop_info.get("crop_applied")),
                "crop_method": crop_info.get("crop_method"),
                "crop_area": {
                    "crop_w": crop_info.get("crop_w"),
                    "crop_h": crop_info.get("crop_h"),
                    "crop_x": crop_info.get("crop_x"),
                    "crop_y": crop_info.get("crop_y"),
                }
                if crop_info.get("crop_applied")
                else None,
                "foreground_zoom_base": settings.shorts_foreground_zoom_base,
                "foreground_zoom_applied": applied_zoom,
                "foreground_width": applied_foreground_width,
                "foreground_light_adjustment": {
                    "brightness": settings.shorts_foreground_brightness,
                    "contrast": settings.shorts_foreground_contrast,
                    "saturation": settings.shorts_foreground_saturation,
                },
                "background_light_adjustment": {
                    "brightness": settings.shorts_background_darkness,
                    "contrast": settings.shorts_background_contrast,
                    "saturation": settings.shorts_background_saturation,
                },
            },
            "audio_mix": {
                "voice_starts_at": 0,
                "voice_volume": settings.voice_volume,
                "bgm_enabled": bgm_exists,
                "bgm_volume": settings.bgm_volume if bgm_exists else 0.0,
                "bgm_fade_out_seconds": fade_out_seconds if bgm_exists else 0.0,
            },
            "warnings": warnings,
        }

    def build_output_path(self, movie_id: int) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_dir = self._resolve_local_path(settings.shorts_output_dir) / f"movie_{movie_id}"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"movie_{movie_id}_draft_shorts_9x16_{timestamp}_{uuid4().hex[:8]}.mp4"
        return self._to_relative_path(output_path)

    def detect_crop_area(self, master_video_path: str) -> dict:
        master_path = self._resolve_local_path(master_video_path)
        if not master_path.exists():
            raise FileNotFoundError(f"Master video not found: {master_video_path}")

        stream_info = self._probe_video_stream(master_path)
        original_width = int(stream_info.get("width") or 0)
        original_height = int(stream_info.get("height") or 0)
        default_result = {
            "detected": False,
            "original_width": original_width,
            "original_height": original_height,
            "has_black_bars": False,
            "crop_applied": False,
            "crop_method": None,
            "message": "No black bars detected",
        }
        if original_width <= 0 or original_height <= 0:
            return {**default_result, "warning": "Crop detection skipped because source dimensions were unavailable."}

        sample_duration = min(max(self._probe_duration_seconds(master_path), 3.0), 20.0)
        crop_result = self._run_cropdetect(master_path=master_path, sample_duration=sample_duration, limit=0.08)
        if not crop_result:
            crop_result = self._run_cropdetect(master_path=master_path, sample_duration=sample_duration, limit=0.03, start_offset=1.0)
        if not crop_result:
            return self._fallback_crop_or_default(default_result=default_result)

        crop_w, crop_h, crop_x, crop_y = crop_result
        if not self._is_valid_crop(
            original_width=original_width,
            original_height=original_height,
            crop_w=crop_w,
            crop_h=crop_h,
            crop_x=crop_x,
            crop_y=crop_y,
        ):
            return self._fallback_crop_or_default(
                default_result=default_result,
                warning="Crop detection returned an invalid crop area; used fallback crop."
            )

        height_difference = original_height - crop_h
        if height_difference < max(20, int(original_height * 0.08)):
            return self._fallback_crop_or_default(
                default_result=default_result,
                warning="Crop detection was not strong enough for letterbox removal; used fallback crop."
            )

        crop_x = 0 if abs(crop_x) <= 4 else crop_x
        crop_w = original_width if abs(original_width - crop_w) <= 8 else crop_w
        return {
            "detected": True,
            "original_width": original_width,
            "original_height": original_height,
            "crop_w": crop_w,
            "crop_h": crop_h,
            "crop_x": crop_x,
            "crop_y": crop_y,
            "has_black_bars": True,
            "crop_applied": True,
            "crop_method": "cropdetect",
            "message": "Top and bottom black bars detected",
        }

    def build_video_filter(
        self,
        crop_info: dict,
        shorts_width: int,
        shorts_height: int,
        foreground_width: int,
        foreground_zoom: float,
        background_blur: int,
        background_darkness: float,
        foreground_y_offset: int,
        stop_pad_duration: float,
    ) -> str:
        source_chain = f"[0:v]fps={settings.shorts_fps},format=yuv420p,tpad=stop_mode=clone:stop_duration={stop_pad_duration:.3f}"
        if crop_info.get("crop_applied"):
            source_chain += f",crop={self._build_crop_expression(crop_info)}"
        source_chain += ",split=2[bgsrc][fgsrc]"

        effective_width = int(foreground_width * foreground_zoom)
        overlay_x = "(W-w)/2" if settings.shorts_foreground_x_center else "(W-w)/2"
        overlay_y = self._build_overlay_y_expression(
            canvas_height=shorts_height,
            foreground_width=effective_width,
            y_offset=foreground_y_offset,
            crop_info=crop_info,
        )

        return ";".join(
            [
                source_chain,
                (
                    f"[bgsrc]scale={shorts_width}:{shorts_height}:force_original_aspect_ratio=increase,"
                    f"crop={shorts_width}:{shorts_height},"
                    f"boxblur={background_blur}:1,"
                    f"eq=brightness={background_darkness}:contrast={settings.shorts_background_contrast}:"
                    f"saturation={settings.shorts_background_saturation}[bg]"
                ),
                (
                    f"[fgsrc]eq=brightness={settings.shorts_foreground_brightness}:"
                    f"contrast={settings.shorts_foreground_contrast}:"
                    f"saturation={settings.shorts_foreground_saturation},"
                    f"scale={effective_width}:-2[fg]"
                ),
                f"[bg][fg]overlay={overlay_x}:{overlay_y},format=yuv420p[v]",
            ]
        )

    def _probe_audio_duration_seconds(self, path: Path) -> float:
        duration = self._probe_duration_seconds(path)
        if duration > 0:
            return duration
        if MutagenFile is None:
            return 0.0
        audio_file = MutagenFile(path)
        info = getattr(audio_file, "info", None)
        length = getattr(info, "length", 0.0)
        try:
            return round(float(length), 3)
        except (TypeError, ValueError):
            return 0.0

    def _probe_video_stream(self, path: Path) -> dict:
        command = [
            self.ffprobe_binary,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(path),
        ]
        result = self._run_subprocess(command, capture_json=True) or {}
        streams = result.get("streams") or []
        if not streams:
            return {}
        return streams[0]

    def _fallback_crop_or_default(self, default_result: dict, warning: str | None = None) -> dict:
        original_width = int(default_result.get("original_width") or 0)
        original_height = int(default_result.get("original_height") or 0)
        if original_width <= 0 or original_height <= 0:
            return {**default_result, "warning": warning or "Crop detection was unavailable; used original frame."}

        crop_w = original_width
        crop_h = max(int(round(original_height * 0.74)), 2)
        if crop_h % 2 != 0:
            crop_h -= 1
        crop_y = max(int(round(original_height * 0.13)), 0)
        if crop_y % 2 != 0:
            crop_y -= 1
        if crop_y + crop_h > original_height:
            crop_h = original_height - crop_y
            if crop_h % 2 != 0:
                crop_h -= 1

        if crop_h <= 0 or crop_h >= original_height:
            return {**default_result, "warning": warning or "Crop detection was unavailable; used original frame."}

        return {
            "detected": True,
            "original_width": original_width,
            "original_height": original_height,
            "crop_w": crop_w,
            "crop_h": crop_h,
            "crop_x": 0,
            "crop_y": crop_y,
            "has_black_bars": True,
            "crop_applied": True,
            "crop_method": "fallback",
            "message": "Fallback top and bottom crop applied",
            "warning": warning or "Crop detection was unavailable; applied safe fallback crop.",
        }

    @staticmethod
    def _build_crop_expression(crop_info: dict) -> str:
        if crop_info.get("crop_method") == "fallback":
            return "in_w:in_h*0.74:0:in_h*0.13"
        return f"{int(crop_info['crop_w'])}:{int(crop_info['crop_h'])}:{int(crop_info['crop_x'])}:{int(crop_info['crop_y'])}"

    def _run_cropdetect(self, master_path: Path, sample_duration: float, limit: float, start_offset: float = 0.0) -> tuple[int, int, int, int] | None:
        command = [
            self.ffmpeg_binary,
            "-hide_banner",
            "-ss",
            f"{start_offset:.3f}",
            "-t",
            f"{sample_duration:.3f}",
            "-i",
            str(master_path),
            "-vf",
            f"cropdetect=limit={limit}:round=2:reset=0",
            "-an",
            "-f",
            "null",
            "-",
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        crop_matches = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", (result.stderr or "") + "\n" + (result.stdout or ""))
        if result.returncode != 0 or not crop_matches:
            return None
        return tuple(int(value) for value in crop_matches[-1])

    def _get_storage_service(self) -> SupabaseStorageService:
        if self.storage_service is None:
            self.storage_service = SupabaseStorageService()
        return self.storage_service

    @staticmethod
    def _extract_storage_path(voice_audio_path: str) -> str | None:
        bucket_prefix = f"{settings.supabase_audio_bucket}/"
        normalized = str(voice_audio_path or "").strip()
        if normalized.startswith(bucket_prefix):
            return normalized[len(bucket_prefix) :]
        if normalized.startswith("audio/"):
            return normalized
        return None

    @staticmethod
    def _clamp_foreground_y(canvas_height: int, foreground_width: int, y_offset: int, crop_info: dict | None = None) -> int:
        h_ratio, w_ratio = 9, 16
        if crop_info:
            if crop_info.get("crop_applied"):
                w_ratio = crop_info.get("crop_w") or 16
                h_ratio = crop_info.get("crop_h") or 9
            elif crop_info.get("original_width") and crop_info.get("original_height"):
                w_ratio = crop_info.get("original_width") or 16
                h_ratio = crop_info.get("original_height") or 9
        foreground_height = round(foreground_width * h_ratio / w_ratio)
        centered_y = round((canvas_height - foreground_height) / 2) + y_offset
        min_y = 0
        max_y = max(canvas_height - foreground_height, 0)
        return max(min_y, min(centered_y, max_y))

    @classmethod
    def _build_overlay_y_expression(cls, canvas_height: int, foreground_width: int, y_offset: int, crop_info: dict | None = None) -> str:
        centered_y = cls._clamp_foreground_y(canvas_height=canvas_height, foreground_width=foreground_width, y_offset=y_offset, crop_info=crop_info)
        if settings.shorts_foreground_y_center:
            return str(centered_y)
        return str(centered_y)

    @staticmethod
    def _is_valid_crop(
        original_width: int,
        original_height: int,
        crop_w: int,
        crop_h: int,
        crop_x: int,
        crop_y: int,
    ) -> bool:
        if min(original_width, original_height, crop_w, crop_h) <= 0:
            return False
        if crop_w > original_width or crop_h > original_height:
            return False
        if crop_x < 0 or crop_y < 0:
            return False
        if crop_x + crop_w > original_width or crop_y + crop_h > original_height:
            return False
        return True
