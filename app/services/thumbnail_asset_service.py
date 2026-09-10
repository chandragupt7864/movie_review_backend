import os
import requests
import cv2
from pathlib import Path
from app.config import PROJECT_ROOT, settings

class ThumbnailAssetService:
    def download_image(self, url: str, output_path: str) -> dict:
        if not url:
            raise ValueError("URL is empty.")
        
        resolved_path = self._resolve_local_path(output_path)
        resolved_path.parent.mkdir(parents=True, exist_ok=True)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        response = requests.get(url, headers=headers, timeout=15, stream=True)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "").lower()
        allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
        if not any(t in content_type for t in allowed_types):
            # Try to guess or proceed anyway if headers don't specify, but raise if clearly wrong format
            if "html" in content_type or "text" in content_type:
                raise ValueError(f"URL did not return an image. Content-Type: {content_type}")

        with open(resolved_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        file_size = resolved_path.stat().st_size
        return {
            "source_url": url,
            "local_path": self._to_relative_path(resolved_path),
            "content_type": content_type,
            "file_size_bytes": file_size
        }

    def extract_video_frames(self, video_path: str, output_dir: str, movie_id: int) -> list:
        resolved_video = self._resolve_local_path(video_path)
        if not resolved_video.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        resolved_out_dir = self._resolve_local_path(output_dir)
        resolved_out_dir.mkdir(parents=True, exist_ok=True)

        cap = cv2.VideoCapture(str(resolved_video))
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        duration_seconds = total_frames / fps if total_frames > 0 else 0.0

        percentages = [0.08, 0.25, 0.45, 0.65, 0.85]
        frames_extracted = []

        for idx, pct in enumerate(percentages, start=1):
            frame_num = int(total_frames * pct)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            success, frame = cap.read()
            if success:
                timestamp = frame_num / fps
                frame_filename = f"frame_movie_{movie_id}_{idx}.jpg"
                frame_local_path = resolved_out_dir / frame_filename
                
                # Save frame
                cv2.imwrite(str(frame_local_path), frame)
                
                frames_extracted.append({
                    "type": "video_frame",
                    "local_path": self._to_relative_path(frame_local_path),
                    "timestamp_seconds": round(timestamp, 2)
                })

        cap.release()
        return frames_extracted

    def collect_thumbnail_references(self, movie_row: dict) -> dict:
        movie_id = movie_row["id"]
        ref_dir = Path(settings.thumbnail_reference_dir) / f"movie_{movie_id}"
        ref_dir.mkdir(parents=True, exist_ok=True)

        references = []
        warnings = []

        # 1. Download Poster
        poster_url = movie_row.get("poster_url")
        if poster_url:
            try:
                poster_path = ref_dir / f"poster_{movie_id}.jpg"
                res = self.download_image(poster_url, str(poster_path))
                references.append({
                    "type": "poster",
                    "local_path": res["local_path"],
                    "source_url": poster_url
                })
            except Exception as e:
                warnings.append(f"Failed to download poster: {e}")

        # 2. Download Backdrop
        backdrop_url = movie_row.get("backdrop_url")
        if backdrop_url:
            try:
                backdrop_path = ref_dir / f"backdrop_{movie_id}.jpg"
                res = self.download_image(backdrop_url, str(backdrop_path))
                references.append({
                    "type": "backdrop",
                    "local_path": res["local_path"],
                    "source_url": backdrop_url
                })
            except Exception as e:
                warnings.append(f"Failed to download backdrop: {e}")

        # 3. Download YouTube Trailer Thumbnail if available
        trailer_youtube_id = movie_row.get("trailer_youtube_id")
        if not trailer_youtube_id and movie_row.get("trailer_data_json"):
            # try to extract from trailer_data_json
            td = movie_row["trailer_data_json"] or {}
            if isinstance(td, dict):
                trailer_youtube_id = td.get("youtube_id") or td.get("id")

        if trailer_youtube_id:
            # Try maxresdefault, fallback to hqdefault
            yt_thumb_urls = [
                f"https://img.youtube.com/vi/{trailer_youtube_id}/maxresdefault.jpg",
                f"https://img.youtube.com/vi/{trailer_youtube_id}/hqdefault.jpg"
            ]
            for url in yt_thumb_urls:
                try:
                    trailer_path = ref_dir / f"trailer_thumb_{movie_id}.jpg"
                    res = self.download_image(url, str(trailer_path))
                    references.append({
                        "type": "trailer_thumbnail",
                        "local_path": res["local_path"],
                        "source_url": url
                    })
                    break  # Success
                except Exception:
                    continue
            else:
                warnings.append("Failed to download trailer thumbnail from YouTube.")

        # 4. Extract video frames from draft_video_path or final_video_path
        video_path = movie_row.get("draft_video_path") or movie_row.get("final_video_path")
        if video_path:
            try:
                frames_dir = ref_dir / "frames"
                extracted = self.extract_video_frames(
                    video_path=video_path,
                    output_dir=str(frames_dir),
                    movie_id=movie_id
                )
                references.extend(extracted)
            except Exception as e:
                warnings.append(f"Failed to extract video frames: {e}")
        else:
            warnings.append("Neither draft_video_path nor final_video_path was available for frame extraction.")

        return {
            "references": references,
            "warnings": warnings
        }

    @staticmethod
    def _resolve_local_path(video_path: str) -> Path:
        path = Path(video_path)
        if path.is_absolute():
            return path
        return PROJECT_ROOT / path

    @staticmethod
    def _to_relative_path(path: Path) -> str:
        try:
            return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
        except ValueError:
            return str(path).replace("\\", "/")
