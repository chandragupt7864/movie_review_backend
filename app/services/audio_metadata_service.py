from pathlib import Path
from tempfile import NamedTemporaryFile

import requests

from app.config import PROJECT_ROOT
from app.services.supabase_storage_service import SupabaseStorageService


class AudioMetadataService:
    def get_audio_duration_seconds(self, audio_path: str) -> float:
        local_path = self._resolve_local_path(audio_path)
        if local_path and local_path.exists():
            return self._read_duration_from_file(local_path)

        storage_path = self._storage_path_from_audio_path(audio_path)
        if storage_path:
            return self._read_duration_from_supabase(storage_path)

        raise ValueError(f"Audio file not found or unsupported path: {audio_path}")

    @staticmethod
    def _resolve_local_path(audio_path: str) -> Path | None:
        path = Path(audio_path)
        if path.is_absolute():
            return path
        candidate = PROJECT_ROOT / path
        if candidate.exists():
            return candidate
        return None

    def _read_duration_from_supabase(self, storage_path: str) -> float:
        signed_url = SupabaseStorageService().create_signed_url(storage_path=storage_path, expires_in=900)
        response = requests.get(signed_url, timeout=60)
        response.raise_for_status()

        temp_path: Path | None = None
        try:
            with NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
                temp_path = Path(temp_file.name)
                temp_file.write(response.content)
                temp_file.flush()
            return self._read_duration_from_file(temp_path)
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)

    @staticmethod
    def _read_duration_from_file(file_path: Path) -> float:
        try:
            from mutagen import File as MutagenFile
        except ModuleNotFoundError as exc:
            raise ValueError("mutagen package is not installed. Run pip install -r requirements.txt.") from exc

        metadata = MutagenFile(file_path)
        duration = getattr(getattr(metadata, "info", None), "length", None)
        if duration is None:
            raise ValueError(f"Could not detect audio duration for: {file_path}")
        return float(duration)

    @staticmethod
    def _storage_path_from_audio_path(audio_path: str) -> str | None:
        if not audio_path:
            return None
        path = str(audio_path)
        if path.startswith("movie-audio/"):
            return path[len("movie-audio/") :]
        if path.startswith("audio/"):
            return path
        return None
