from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, UploadFile
from PIL import Image
from app.routes import movie_routes as routes


def test_thumbnail_cloud_failure_keeps_local_image_and_preview(tmp_path, monkeypatch):
    movie = {"id": 230, "movie_title": "Test", "render_status": "COMPLETED"}
    repository = Mock()
    repository.get_movie_by_id.return_value = movie
    monkeypatch.setattr(routes, "MoviePipelineRepository", lambda: repository)
    monkeypatch.setattr(routes, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(routes.settings, "thumbnail_output_dir", "thumbnails")
    monkeypatch.setattr(routes.settings, "thumbnail_upload_to_supabase", True)
    monkeypatch.setattr(routes.settings, "supabase_url", "https://example.test")
    monkeypatch.setattr(routes.settings, "supabase_service_role_key", "test")
    storage = Mock()
    storage.upload_file.side_effect = RuntimeError("Bucket not found")
    monkeypatch.setattr(routes, "SupabaseStorageService", lambda: storage)
    image = BytesIO()
    Image.new("RGB", (24, 32), "red").save(image, format="WEBP")
    image.seek(0)
    result = routes.upload_thumbnail(230, UploadFile(file=image, filename="poster.webp"))
    assert result["success"]
    assert result["uploaded_to_supabase"] is False
    assert (tmp_path / result["thumbnail_path"]).is_file()
    payload = repository.update_thumbnail_success.call_args.kwargs["thumbnail_payload"]
    assert payload["thumbnail_data"]["warnings"]
    movie["thumbnail_path"] = result["thumbnail_path"]
    preview = routes.get_thumbnail_file(230)
    assert preview.media_type == "image/webp"
