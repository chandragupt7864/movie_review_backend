from app.agents.shorts_composer_agent.agent import ShortsComposerAgent
from app.core.agent_status import NEXT_AGENT_SHORTS_COMPOSER, RENDER_COMPLETED, SHORTS_COMPLETED, VOICE_COMPLETED


def test_shorts_composer_accepts_bgm_ready_state() -> None:
    movie = {
        "is_active": True,
        "is_locked": False,
        "next_agent": NEXT_AGENT_SHORTS_COMPOSER,
        "render_status": RENDER_COMPLETED,
        "master_video_path": "storage/final_videos/movie_230/master.mp4",
        "voice_status": VOICE_COMPLETED,
        "voice_audio_path": "storage/audio/movie_230.mp3",
        "thumbnail_path": "storage/thumbnail.png",
                "thumbnail_status": "COMPLETED",
                "shorts_status": "PENDING",
        "overall_status": "BGM_READY",
    }

    assert ShortsComposerAgent._eligibility_error(movie=movie, force=False) is None


def test_shorts_composer_agent_completes_with_master_video_and_voice():
    class FakeRepository:
        def __init__(self):
            self.shorts_payload = None

        def get_movie_by_id(self, movie_id):
            return {
                "id": movie_id,
                "movie_title": "Vertical Movie",
                "tmdb_id": 701,
                "is_active": True,
                "is_locked": False,
                "next_agent": NEXT_AGENT_SHORTS_COMPOSER,
                "render_status": RENDER_COMPLETED,
                "master_video_path": "storage/final_videos/movie_1/movie_1_master.mp4",
                "voice_status": VOICE_COMPLETED,
                "voice_audio_path": "storage/audio/movie_1.mp3",
                "thumbnail_path": "storage/thumbnail.png",
                "thumbnail_status": "COMPLETED",
                "shorts_status": "PENDING",
                "overall_status": "MASTER_VIDEO_READY",
            }

        def lock_movie_for_agent(self, movie_id, agent_name):
            movie = self.get_movie_by_id(movie_id)
            movie["is_locked"] = True
            return movie

        def update_shorts_composer_success(self, movie_id, shorts_payload):
            self.shorts_payload = shorts_payload

        def update_shorts_composer_failed(self, movie_id, error_payload):
            raise AssertionError(error_payload["error_message"])

    class FakeShortsComposerService:
        def build_output_path(self, movie_id):
            return f"storage/final_videos/movie_{movie_id}/movie_{movie_id}_draft_shorts.mp4"

        def compose_shorts_draft(self, movie_id, master_video_path, voice_audio_path, output_path, bgm_path=None, thumbnail_path=None, appearance=None):
            assert thumbnail_path == "storage/thumbnail.png"
            assert movie_id == 1
            assert master_video_path.endswith("movie_1_master.mp4")
            assert voice_audio_path.endswith("movie_1.mp3")
            assert output_path.endswith("movie_1_draft_shorts.mp4")
            return {
                "draft_video_path": output_path,
                "final_video_path": output_path,
                "master_video_path": master_video_path,
                "voice_audio_path": voice_audio_path,
                "bgm_path": bgm_path,
                "duration_seconds": 55.2,
                "master_duration_seconds": 52.0,
                "voice_duration_seconds": 55.2,
                "resolution": "1080x1920",
                "fps": 30,
                "layout": {
                    "background": "blurred cropped video full screen",
                    "foreground": "cropped, zoomed, centered video",
                    "foreground_width": 1220,
                    "foreground_x_alignment": "center",
                    "foreground_y_alignment": "center",
                    "foreground_y_offset": 0,
                },
                "preprocessing": {
                    "black_bar_detection_enabled": True,
                    "has_black_bars": True,
                    "crop_applied": True,
                    "crop_method": "cropdetect",
                    "crop_area": {"crop_w": 1920, "crop_h": 800, "crop_x": 0, "crop_y": 140},
                    "foreground_zoom_base": 1.50,
                    "foreground_zoom_applied": 1.70,
                    "foreground_light_adjustment": {"brightness": 0.06, "contrast": 1.08, "saturation": 1.08},
                    "background_light_adjustment": {"brightness": -0.08, "contrast": 1.0, "saturation": 1.0},
                },
                "audio_mix": {"bgm_enabled": False},
                "warnings": ["Voice audio is longer than master video; extended final frame to match voice duration."],
            }

    class FakeCloudinaryVideoStorageService:
        def upload_final_video(self, movie_id, local_file_path):
            assert movie_id == 1
            assert local_file_path.endswith("movie_1_draft_shorts.mp4")
            return {
                "storage_provider": "cloudinary",
                "secure_url": "https://res.cloudinary.com/test/video/upload/final_shorts.mp4",
                "public_id": "reelybee/final-videos/movie_1/final_shorts",
            }

    repository = FakeRepository()
    agent = ShortsComposerAgent(
        repository=repository,
        shorts_composer_service=FakeShortsComposerService(),
        cloudinary_video_storage_service=FakeCloudinaryVideoStorageService(),
    )

    result = agent.run_for_movie(movie_id=1)

    assert result["success"] is True
    assert result["agent"] == "SHORTS_COMPOSER_AGENT"
    assert result["results"][0]["status"] == SHORTS_COMPLETED
    assert repository.shorts_payload["draft_video_path"].endswith("movie_1_draft_shorts.mp4")
    assert repository.shorts_payload["next_agent"] == "DONE"
    assert repository.shorts_payload["preprocessing"]["crop_applied"] is True
    assert repository.shorts_payload["preprocessing"]["foreground_zoom_applied"] == 1.70
    assert repository.shorts_payload["layout"]["foreground_width"] == 1220
    assert repository.shorts_payload["cloudinary_video_url"].startswith("https://res.cloudinary.com/")
    assert result["results"][0]["cloudinary_video_url"] == repository.shorts_payload["cloudinary_video_url"]


def test_shorts_composer_force_still_requires_master_and_voice_assets():
    class FakeRepository:
        def get_movie_by_id(self, movie_id):
            return {
                "id": movie_id,
                "movie_title": "Broken Movie",
                "tmdb_id": 702,
                "is_active": True,
                "is_locked": False,
                "next_agent": "SOMETHING_ELSE",
                "render_status": "PENDING",
                "master_video_path": None,
                "voice_status": "PENDING",
                "voice_audio_path": None,
                "thumbnail_path": "storage/thumbnail.png",
                "thumbnail_status": "COMPLETED",
                "shorts_status": "PENDING",
            }

    agent = ShortsComposerAgent(repository=FakeRepository(), shorts_composer_service=object())
    result = agent.run_for_movie(movie_id=1, force=True)

    assert result["failed"] == 1
    assert result["results"][0]["error"] == "16:9 master video is not ready yet."


def test_shorts_requires_thumbnail_even_when_forced():
    movie = {"render_status": "COMPLETED", "master_video_path": "master.mp4",
             "voice_status": "COMPLETED", "voice_audio_path": "voice.mp3"}
    assert ShortsComposerAgent._eligibility_error(movie, force=True) == "Upload a thumbnail before composing Shorts."


def test_manual_controller_waits_for_thumbnail():
    from app.services.manual_pipeline_controller import ManualPipelineController
    movie = {"next_agent": NEXT_AGENT_SHORTS_COMPOSER}
    assert ManualPipelineController()._should_pause_for_manual_step(movie)
    movie.update(thumbnail_path="thumbnail.png", thumbnail_status="COMPLETED")
    assert not ManualPipelineController()._should_pause_for_manual_step(movie)
