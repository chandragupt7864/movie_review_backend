from datetime import datetime, timezone
from pathlib import Path

from app.config import PROJECT_ROOT, settings


class SupabaseStorageService:
    storage_provider = "supabase"

    def __init__(self) -> None:
        if not settings.supabase_url:
            raise ValueError("SUPABASE_URL is not configured.")
        if not settings.supabase_service_role_key:
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY is not configured.")

        try:
            from supabase import create_client
        except ModuleNotFoundError as exc:
            raise ValueError("supabase package is not installed. Run pip install -r requirements.txt.") from exc

        self.bucket = settings.supabase_audio_bucket
        self.client = create_client(settings.supabase_url, settings.supabase_service_role_key)
        self.storage = self.client.storage.from_(self.bucket)

    def upload_audio(self, local_file_path: str, storage_path: str, bucket: str | None = None, content_type: str = "audio/mpeg") -> dict:
        path = self._local_path(local_file_path)
        if not path.exists():
            raise ValueError(f"Local audio file not found: {local_file_path}")

        target_bucket = bucket or self.bucket
        bucket_storage = self.client.storage.from_(target_bucket)
        with path.open("rb") as audio_file:
            bucket_storage.upload(
                path=storage_path,
                file=audio_file,
                file_options={
                    "content-type": content_type,
                    "upsert": "true",
                },
            )

        return {
            "bucket": target_bucket,
            "storage_path": storage_path,
            "storage_provider": self.storage_provider,
            "uploaded": True,
        }

    def upload_file(self, local_file_path: str, bucket: str, storage_path: str, content_type: str) -> dict:
        path = self._local_path(local_file_path)
        if not path.exists():
            raise ValueError(f"Local file not found: {local_file_path}")

        bucket_storage = self.client.storage.from_(bucket)
        with path.open("rb") as file_data:
            bucket_storage.upload(
                path=storage_path,
                file=file_data,
                file_options={
                    "content-type": content_type,
                    "upsert": "true",
                },
            )

        return {
            "storage_provider": self.storage_provider,
            "bucket": bucket,
            "storage_path": storage_path,
            "thumbnail_path": f"{bucket}/{storage_path}",
            "uploaded_to_supabase": True,
        }

    def delete_file(self, storage_path: str, bucket: str | None = None) -> dict:
        target_bucket = bucket or self.bucket
        self.client.storage.from_(target_bucket).remove([storage_path])
        return {
            "bucket": target_bucket,
            "storage_path": storage_path,
            "storage_provider": self.storage_provider,
            "deleted": True,
        }

    def download_file(self, storage_path: str, local_file_path: str, bucket: str | None = None) -> dict:
        target_bucket = bucket or self.bucket
        payload = self.client.storage.from_(target_bucket).download(storage_path)
        local_path = self._local_path(local_file_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(payload)
        return {
            "bucket": target_bucket,
            "storage_path": storage_path,
            "local_file_path": str(local_path),
            "storage_provider": self.storage_provider,
            "downloaded": True,
        }

    def create_signed_url(self, storage_path: str, expires_in: int = 3600, bucket: str | None = None) -> str:
        target_bucket = bucket or self.bucket
        response = self.client.storage.from_(target_bucket).create_signed_url(storage_path, expires_in)
        if isinstance(response, dict):
            signed_url = response.get("signedURL") or response.get("signed_url")
            if signed_url:
                return str(signed_url)
        signed_url = getattr(response, "signed_url", None) or getattr(response, "signedURL", None)
        if signed_url:
            return str(signed_url)
        raise ValueError("Supabase did not return a signed URL.")

    def cleanup_old_audio_files(self, keep_last: int = 20) -> dict:
        files = self._list_audio_files()
        files = sorted(files, key=self._file_sort_key, reverse=True)
        deleted_paths = [item["storage_path"] for item in files[keep_last:]]
        for storage_path in deleted_paths:
            self.delete_file(storage_path=storage_path)

        return {
            "bucket": self.bucket,
            "storage_provider": self.storage_provider,
            "keep_last": keep_last,
            "deleted_count": len(deleted_paths),
            "deleted_paths": deleted_paths,
        }

    def file_exists(self, storage_path: str) -> bool:
        folder, name = self._split_storage_path(storage_path)
        try:
            files = self.storage.list(folder, {"search": name})
        except Exception:
            return False
        return any(item.get("name") == name for item in files or [])

    def list_audio_files(self) -> list[dict]:
        return sorted(self._list_audio_files(), key=self._file_sort_key, reverse=True)

    def _list_audio_files(self) -> list[dict]:
        files = self.storage.list("audio")
        results = []
        for item in files or []:
            name = item.get("name")
            if not name or not name.endswith(".mp3"):
                continue
            results.append({**item, "storage_path": f"audio/{name}"})
        return results

    @staticmethod
    def _local_path(local_file_path: str) -> Path:
        path = Path(local_file_path)
        if path.is_absolute():
            return path
        return PROJECT_ROOT / path

    @staticmethod
    def _split_storage_path(storage_path: str) -> tuple[str, str]:
        path = Path(storage_path)
        folder = str(path.parent).replace("\\", "/")
        return ("" if folder == "." else folder, path.name)

    @staticmethod
    def _file_sort_key(item: dict) -> str:
        return str(
            item.get("updated_at")
            or item.get("created_at")
            or item.get("last_accessed_at")
            or datetime.now(timezone.utc).isoformat()
        )
