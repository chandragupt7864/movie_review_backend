import json
import math
import re
import subprocess
from pathlib import Path

from app.config import settings


class BGMAudioAnalysisService:
    def analyze(self, file_path: str | Path) -> dict:
        path = Path(file_path)
        probe_data = self._run_ffprobe(path)
        format_info = probe_data.get("format") or {}
        stream = self._pick_audio_stream(probe_data.get("streams") or [])
        if not stream:
            raise ValueError("Invalid audio: no audio stream found.")

        embedded_metadata = self._read_embedded_metadata(path)
        duration = self._to_float(format_info.get("duration")) or self._to_float(stream.get("duration"))
        codec = stream.get("codec_name")
        bit_rate = self._to_int(stream.get("bit_rate")) or self._to_int(format_info.get("bit_rate"))
        sample_rate = self._to_int(stream.get("sample_rate"))
        channels = self._to_int(stream.get("channels"))
        audio_format = format_info.get("format_name")
        loudness_data = self._analyze_loudness(path)
        rhythm_data = self._analyze_rhythm(path)
        genre_value = embedded_metadata.get("genre")

        return {
            "duration_seconds": duration,
            "codec": codec,
            "bit_rate": bit_rate,
            "sample_rate": sample_rate,
            "channels": channels,
            "audio_format": audio_format,
            "file_size_bytes": path.stat().st_size,
            "bpm": rhythm_data.get("bpm"),
            "tempo_category": self._tempo_category(rhythm_data.get("bpm")),
            "energy_level": self._energy_category(rhythm_data.get("energy")),
            "loudness_lufs": loudness_data.get("loudness_lufs"),
            "peak_db": loudness_data.get("peak_db"),
            "is_instrumental": None,
            "technical_data": {
                "ffprobe_format": format_info,
                "ffprobe_stream": stream,
                "rhythm_analysis": rhythm_data,
                "loudness_analysis": loudness_data,
            },
            "embedded_metadata": embedded_metadata,
            "mood_tags": [],
            "genre_tags": [genre_value] if genre_value else [],
        }

    def validate_audio(self, file_path: str | Path) -> None:
        path = Path(file_path)
        probe_data = self._run_ffprobe(path)
        if not self._pick_audio_stream(probe_data.get("streams") or []):
            raise ValueError("Uploaded file is not a valid audio file.")

    def _run_ffprobe(self, path: Path) -> dict:
        if not settings.ffprobe_binary:
            raise ValueError("FFPROBE_BINARY is not configured or ffprobe is unavailable.")
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
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=120)
        except FileNotFoundError as exc:
            raise ValueError("ffprobe is unavailable.") from exc
        except subprocess.CalledProcessError as exc:
            raise ValueError("Uploaded file is not a valid audio file.") from exc
        return json.loads(result.stdout or "{}")

    @staticmethod
    def _pick_audio_stream(streams: list[dict]) -> dict | None:
        for stream in streams:
            if stream.get("codec_type") == "audio":
                return stream
        return None

    @staticmethod
    def _read_embedded_metadata(path: Path) -> dict:
        try:
            from mutagen import File as MutagenFile
        except ModuleNotFoundError as exc:
            raise ValueError("mutagen package is not installed. Run pip install -r requirements.txt.") from exc

        audio = MutagenFile(path)
        tags = getattr(audio, "tags", None)
        flat: dict[str, object] = {}
        if tags:
            for key, value in tags.items():
                if isinstance(value, list):
                    flat[key] = value[0] if value else None
                else:
                    flat[key] = value

        return {
            "title": BGMAudioAnalysisService._first_tag(flat, ["TIT2", "title", "\xa9nam"]),
            "artist": BGMAudioAnalysisService._first_tag(flat, ["TPE1", "artist", "\xa9ART"]),
            "album": BGMAudioAnalysisService._first_tag(flat, ["TALB", "album", "\xa9alb"]),
            "genre": BGMAudioAnalysisService._first_tag(flat, ["TCON", "genre", "\xa9gen"]),
            "copyright": BGMAudioAnalysisService._first_tag(flat, ["TCOP", "copyright", "cprt"]),
            "raw_tags": {str(key): BGMAudioAnalysisService._stringify_tag(value) for key, value in flat.items()},
        }

    @staticmethod
    def _first_tag(tags: dict, keys: list[str]) -> str | None:
        for key in keys:
            value = tags.get(key)
            if value is None:
                continue
            return BGMAudioAnalysisService._stringify_tag(value)
        return None

    @staticmethod
    def _stringify_tag(value: object) -> str | None:
        if value is None:
            return None
        if hasattr(value, "text"):
            text = getattr(value, "text")
            if isinstance(text, list) and text:
                return str(text[0]).strip() or None
        return str(value).strip() or None

    def _analyze_loudness(self, path: Path) -> dict:
        if not settings.ffmpeg_binary:
            return {"warning": "ffmpeg unavailable", "loudness_lufs": None, "peak_db": None}

        command = [
            settings.ffmpeg_binary,
            "-hide_banner",
            "-i",
            str(path),
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
            "-f",
            "null",
            "NUL",
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=180)
        except FileNotFoundError:
            return {"warning": "ffmpeg unavailable", "loudness_lufs": None, "peak_db": None}

        stderr = result.stderr or ""
        match = re.search(r"\{\s*\"input_i\".*?\}", stderr, re.DOTALL)
        if not match:
            return {"warning": "loudness analysis unavailable", "loudness_lufs": None, "peak_db": None}
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {"warning": "loudness analysis parse failed", "loudness_lufs": None, "peak_db": None}
        return {
            "loudness_lufs": self._to_float(payload.get("input_i")),
            "peak_db": self._to_float(payload.get("input_tp")),
            "raw": payload,
        }

    def _analyze_rhythm(self, path: Path) -> dict:
        try:
            import librosa
        except ModuleNotFoundError:
            return {"warning": "librosa unavailable", "bpm": None, "energy": None}
        except Exception as exc:
            return {"warning": f"librosa import failed: {exc}", "bpm": None, "energy": None}

        try:
            y, sr = librosa.load(path, sr=None, mono=True)
            if y.size == 0:
                return {"warning": "empty audio stream", "bpm": None, "energy": None}
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            rms = librosa.feature.rms(y=y)[0]
            energy = float(rms.mean()) if len(rms) else None
            return {"bpm": self._normalize_number(tempo), "energy": energy}
        except Exception as exc:
            return {"warning": f"rhythm analysis failed: {exc}", "bpm": None, "energy": None}

    @staticmethod
    def _tempo_category(bpm: float | None) -> str | None:
        if bpm is None:
            return None
        if bpm < 90:
            return "SLOW"
        if bpm <= 130:
            return "MEDIUM"
        return "FAST"

    @staticmethod
    def _energy_category(energy: float | None) -> str | None:
        if energy is None:
            return None
        if energy < 0.04:
            return "LOW"
        if energy < 0.10:
            return "MEDIUM"
        return "HIGH"

    @staticmethod
    def _to_float(value: object) -> float | None:
        if value in (None, "", "nan", "N/A", "inf", "-inf"):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if math.isnan(number) or math.isinf(number):
            return None
        return number

    @staticmethod
    def _to_int(value: object) -> int | None:
        try:
            return int(value) if value is not None and str(value).strip() != "" else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_number(value: object) -> float | None:
        number = BGMAudioAnalysisService._to_float(value)
        return round(number, 2) if number is not None else None
