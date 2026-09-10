from pathlib import Path

from app.services.cloudinary_video_storage_service import CloudinaryVideoStorageService
from app.routes.movie_routes import _build_frontend_movie_payload


class FakeUploader:
    def __init__(self):
        self.calls = []

    def upload(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return {
            "secure_url": f"https://res.cloudinary.test/{kwargs['resource_type']}/asset",
            "public_id": kwargs["public_id"],
            "resource_type": kwargs["resource_type"],
            "format": Path(path).suffix.lstrip("."),
        }


def _service(uploader):
    service = CloudinaryVideoStorageService.__new__(CloudinaryVideoStorageService)
    service.uploader = uploader
    return service


def test_upload_bgm_uses_cloudinary_video_resource(tmp_path, monkeypatch):
    audio = tmp_path / "music.mp3"
    audio.write_bytes(b"audio")
    uploader = FakeUploader()
    service = _service(uploader)
    monkeypatch.setattr("app.services.cloudinary_video_storage_service.settings.cloudinary_bgm_folder", "app/music")

    result = service.upload_bgm(movie_id=23, local_file_path=str(audio))

    assert result["secure_url"].startswith("https://")
    assert result["public_id"] == "app/music/movie_23/background_music"
    assert uploader.calls[0][1]["resource_type"] == "video"


def test_upload_thumbnail_uses_cloudinary_image_resource(tmp_path, monkeypatch):
    thumbnail = tmp_path / "thumbnail.webp"
    thumbnail.write_bytes(b"image")
    uploader = FakeUploader()
    service = _service(uploader)
    monkeypatch.setattr("app.services.cloudinary_video_storage_service.settings.cloudinary_thumbnail_folder", "app/thumbnails")

    result = service.upload_thumbnail(movie_id=23, local_file_path=str(thumbnail))

    assert result["public_id"] == "app/thumbnails/movie_23/thumbnail"
    assert uploader.calls[0][1]["resource_type"] == "image"


def test_upload_library_bgm_uses_track_code(tmp_path, monkeypatch):
    audio = tmp_path / "library.mp3"
    audio.write_bytes(b"audio")
    uploader = FakeUploader()
    service = _service(uploader)
    monkeypatch.setattr("app.services.cloudinary_video_storage_service.settings.cloudinary_bgm_folder", "app/music")

    result = service.upload_library_bgm(track_code="BGM-000123", local_file_path=str(audio))

    assert result["public_id"] == "app/music/library/BGM-000123"
    assert uploader.calls[0][1]["resource_type"] == "video"


def test_frontend_payload_prefers_cloudinary_asset_urls():
    payload = _build_frontend_movie_payload(
        {
            "id": 23,
            "movie_title": "Cloud Movie",
            "draft_video_path": "storage/final_videos/movie_23/final.mp4",
            "thumbnail_path": "storage/thumbnails/movie_23/thumbnail.jpg",
            "shorts_data_json": {"cloudinary_video_url": "https://res.cloudinary.test/video/final.mp4"},
            "thumbnail_data_json": {"cloudinary_thumbnail_url": "https://res.cloudinary.test/image/thumbnail.jpg"},
            "bgm_data_json": {"cloudinary_bgm_url": "https://res.cloudinary.test/video/music.mp3"},
        }
    )

    assert payload["assets"]["final_video_file_url"] == "https://res.cloudinary.test/video/final.mp4"
    assert payload["assets"]["thumbnail_file_url"] == "https://res.cloudinary.test/image/thumbnail.jpg"
    assert payload["assets"]["cloudinary_bgm_url"] == "https://res.cloudinary.test/video/music.mp3"
