import os
import requests
from pathlib import Path
from app.config import settings, PROJECT_ROOT

class PosterDownloadService:
    def download_image(self, url: str, output_path_without_ext: str) -> dict:
        if not url:
            raise ValueError("URL is empty.")

        allowed_types = [t.strip().lower() for t in settings.poster_allowed_content_types.split(",")]
        timeout = settings.poster_download_timeout_seconds
        max_size_bytes = settings.poster_max_size_mb * 1024 * 1024

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        # Stream download to validate content length/chunks on the fly
        response = requests.get(url, headers=headers, timeout=timeout, stream=True)
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if content_type not in allowed_types:
            raise ValueError(f"Content type '{content_type}' is not allowed. Supported: {settings.poster_allowed_content_types}")

        # Map content-type to extension
        ext_map = {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp"
        }
        ext = ext_map.get(content_type)
        if not ext:
            # Fallback based on subtype
            parts = content_type.split("/")
            if len(parts) > 1:
                ext = f".{parts[1]}"
            else:
                ext = ".jpg"

        resolved_out_path = Path(output_path_without_ext + ext)
        if not resolved_out_path.is_absolute():
            resolved_out_path = PROJECT_ROOT / resolved_out_path
        
        resolved_out_path.parent.mkdir(parents=True, exist_ok=True)

        total_bytes = 0
        with open(resolved_out_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    total_bytes += len(chunk)
                    if total_bytes > max_size_bytes:
                        # Clean up file
                        f.close()
                        resolved_out_path.unlink(missing_ok=True)
                        raise ValueError(f"Image size exceeds the maximum limit of {settings.poster_max_size_mb} MB.")
                    f.write(chunk)

        # Validate image dimension
        meta = self.validate_image(str(resolved_out_path))

        relative_path = self._to_relative_path(resolved_out_path)

        return {
            "success": True,
            "source_url": url,
            "local_path": relative_path,
            "content_type": content_type,
            "file_size_bytes": total_bytes,
            "width": meta.get("width", 0),
            "height": meta.get("height", 0)
        }

    def validate_image(self, local_path: str) -> dict:
        resolved_path = Path(local_path)
        if not resolved_path.is_absolute():
            resolved_path = PROJECT_ROOT / resolved_path

        try:
            from PIL import Image
            with Image.open(resolved_path) as img:
                return {
                    "width": img.width,
                    "height": img.height,
                    "format": img.format
                }
        except ImportError:
            # Do not fail agent if PIL is unavailable
            return {"width": 0, "height": 0, "format": ""}
        except Exception:
            return {"width": 0, "height": 0, "format": ""}

    @staticmethod
    def _to_relative_path(path: Path) -> str:
        try:
            return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
        except ValueError:
            return str(path).replace("\\", "/")
