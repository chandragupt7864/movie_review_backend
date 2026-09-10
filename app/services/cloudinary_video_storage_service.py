from pathlib import Path

from app.config import PROJECT_ROOT, settings


class CloudinaryVideoStorageService:
    storage_provider = "cloudinary"

    def __init__(self) -> None:
        if not settings.cloudinary_cloud_name:
            raise ValueError("CLOUDINARY_CLOUD_NAME is not configured.")
        if not settings.cloudinary_api_key:
            raise ValueError("CLOUDINARY_API_KEY is not configured.")
        if not settings.cloudinary_api_secret:
            raise ValueError("CLOUDINARY_API_SECRET is not configured.")

        try:
            import cloudinary
            import cloudinary.uploader
        except ModuleNotFoundError as exc:
            raise ValueError("cloudinary package is not installed. Run pip install -r requirements.txt.") from exc

        cloudinary.config(
            cloud_name=settings.cloudinary_cloud_name,
            api_key=settings.cloudinary_api_key,
            api_secret=settings.cloudinary_api_secret,
            secure=True,
        )
        self.uploader = cloudinary.uploader

    def upload_final_video(self, movie_id: int, local_file_path: str) -> dict:
        path = self._local_path(local_file_path)
        if not path.exists() or not path.is_file():
            raise ValueError(f"Local final video file not found: {local_file_path}")
        if path.suffix.lower() != ".mp4":
            raise ValueError("Final video must be an MP4 file.")

        folder = settings.cloudinary_video_folder.strip("/")
        public_id = f"{folder}/movie_{movie_id}/final_shorts" if folder else f"movie_{movie_id}/final_shorts"
        chunk_size = max(5, settings.cloudinary_video_chunk_size_mb) * 1024 * 1024
        result = self.uploader.upload_large(
            str(path),
            resource_type="video",
            public_id=public_id,
            overwrite=True,
            invalidate=True,
            unique_filename=False,
            use_filename=False,
            chunk_size=chunk_size,
        )

        secure_url = result.get("secure_url")
        if not secure_url:
            raise ValueError("Cloudinary upload completed without a secure URL.")

        return {
            "storage_provider": self.storage_provider,
            "secure_url": str(secure_url),
            "public_id": str(result.get("public_id") or public_id),
            "resource_type": str(result.get("resource_type") or "video"),
            "format": str(result.get("format") or "mp4"),
            "version": result.get("version"),
            "bytes": result.get("bytes"),
            "duration": result.get("duration"),
            "width": result.get("width"),
            "height": result.get("height"),
        }

    @staticmethod
    def _local_path(local_file_path: str) -> Path:
        path = Path(local_file_path)
        return path if path.is_absolute() else PROJECT_ROOT / path
