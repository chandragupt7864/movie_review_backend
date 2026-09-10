import os
import pytest
from pathlib import Path
from PIL import Image
from app.agents.thumbnail_metadata_agent.agent import ThumbnailMetadataAgent
from app.services.python_thumbnail_generator_service import PythonThumbnailGeneratorService
from app.services.thumbnail_asset_service import ThumbnailAssetService
from app.core.agent_status import THUMBNAIL_COMPLETED, THUMBNAIL_FAILED


def test_enhance_and_generate_thumbnail_pil(tmp_path):
    # Create dummy backdrop and poster images
    backdrop_path = tmp_path / "backdrop.jpg"
    poster_path = tmp_path / "poster.jpg"
    
    # 100x100 white image
    Image.new("RGB", (100, 100), (255, 255, 255)).save(backdrop_path)
    Image.new("RGB", (80, 120), (100, 150, 200)).save(poster_path)

    generator = PythonThumbnailGeneratorService()
    
    movie_row = {
        "id": 999,
        "movie_title": "Test Movie",
        "script_data_json": {
            "thumbnail_text": "CRAZY TWIST!"
        }
    }
    
    references = [
        {"type": "backdrop", "local_path": str(backdrop_path.relative_to(Path(backdrop_path).anchor))},
        {"type": "poster", "local_path": str(poster_path.relative_to(Path(poster_path).anchor))}
    ]

    output_path = tmp_path / "final_thumbnail.jpg"

    # Make absolute paths work relative to project root mock
    import app.services.python_thumbnail_generator_service as tgs
    old_root = tgs.PROJECT_ROOT
    tgs.PROJECT_ROOT = tmp_path
    
    try:
        res = generator.generate_thumbnail(
            movie_row=movie_row,
            references=references,
            output_path=str(output_path)
        )
        
        assert os.path.exists(str(output_path))
        assert res["width"] == 1080
        assert res["height"] == 1920
        assert res["text_used"] == "CRAZY TWIST!"
        assert res["generated_by"] == "python_pillow_opencv"
    finally:
        tgs.PROJECT_ROOT = old_root


def test_thumbnail_metadata_agent_run():
    class FakeRepository:
        def __init__(self):
            self.success_payload = None
            self.failed_payload = None

        def get_movie_by_id(self, movie_id):
            return {
                "id": movie_id,
                "movie_title": "Supergirl",
                "tmdb_id": 115,
                "is_active": True,
                "is_locked": False,
                "next_agent": "THUMBNAIL_METADATA_AGENT",
                "shorts_status": "COMPLETED",
                "draft_video_path": "storage/final_videos/movie_115/draft.mp4",
                "thumbnail_status": "PENDING"
            }

        def lock_movie_for_agent(self, movie_id, agent_name):
            movie = self.get_movie_by_id(movie_id)
            movie["is_locked"] = True
            return movie

        def update_thumbnail_success(self, movie_id, thumbnail_payload):
            self.success_payload = thumbnail_payload

        def update_thumbnail_failed(self, movie_id, error_payload):
            self.failed_payload = error_payload

    class FakeAssetService:
        def collect_thumbnail_references(self, movie):
            return {
                "references": [
                    {"type": "poster", "local_path": "storage/thumbnail_refs/movie_115/poster.jpg"},
                    {"type": "backdrop", "local_path": "storage/thumbnail_refs/movie_115/backdrop.jpg"}
                ],
                "warnings": ["Frame extraction skipped in mock."]
            }

    class FakeGeneratorService:
        def generate_thumbnail(self, movie_row, references, output_path):
            return {
                "output_path": output_path,
                "width": 1080,
                "height": 1920,
                "text_used": "SUPERGIRL RISE!",
                "references_used": [ref["local_path"] for ref in references],
                "generated_by": "python_pillow_opencv"
            }

    class FakeStorageService:
        def upload_file(self, local_file_path, bucket, storage_path, content_type):
            return {
                "storage_provider": "supabase",
                "bucket": bucket,
                "storage_path": storage_path,
                "thumbnail_path": f"{bucket}/{storage_path}",
                "uploaded_to_supabase": True
            }

    repo = FakeRepository()
    agent = ThumbnailMetadataAgent(
        repository=repo,
        asset_service=FakeAssetService(),
        generator_service=FakeGeneratorService(),
        storage_service=FakeStorageService()
    )

    res = agent.run_for_movie(movie_id=115)
    
    assert res["success"] is True
    assert res["completed"] == 1
    assert res["failed"] == 0
    assert repo.success_payload is not None
    assert repo.success_payload["thumbnail_path"].startswith("movie-thumbnails/thumbnails/movie_115/thumbnail_")
    assert repo.success_payload["youtube_title"] == "Supergirl Review - Movie Review"
