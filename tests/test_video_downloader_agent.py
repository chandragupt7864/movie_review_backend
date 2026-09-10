from pathlib import Path

from app.agents.video_downloader_agent.agent import VideoDownloaderAgent
from app.config import PROJECT_ROOT
from app.core.agent_status import (
    NEXT_AGENT_VIDEO_DOWNLOADER,
    VIDEO_DOWNLOAD_COMPLETED,
    VIDEO_DOWNLOAD_FAILED,
    VOICE_COMPLETED,
)


def test_downloader_agent_fails_when_voice_audio_missing():
    class FakeRepository:
        def get_movie_by_id(self, movie_id):
            return {
                "id": movie_id,
                "movie_title": "Test Movie",
                "tmdb_id": 101,
                "is_active": True,
                "is_locked": False,
                "next_agent": NEXT_AGENT_VIDEO_DOWNLOADER,
                "voice_status": "PENDING",
                "voice_audio_path": None,
            }

    agent = VideoDownloaderAgent(
        repository=FakeRepository(),
        youtube_downloader_service=None,
        video_metadata_service=None,
    )
    result = agent.run_for_movie(movie_id=1)
    assert result["results"][0]["status"] == VIDEO_DOWNLOAD_FAILED
    assert "voice audio is not ready" in result["results"][0]["error"]


def test_downloader_agent_succeeds_with_valid_trailer(monkeypatch):
    class FakeRepository:
        def __init__(self):
            self.success_payload = None

        def get_movie_by_id(self, movie_id):
            return {
                "id": movie_id,
                "movie_title": "Test Movie",
                "tmdb_id": 102,
                "is_active": True,
                "is_locked": False,
                "next_agent": NEXT_AGENT_VIDEO_DOWNLOADER,
                "voice_status": VOICE_COMPLETED,
                "voice_audio_path": "storage/audio/movie_1_hash.mp3",
                "trailer_youtube_id": "abc1234",
                "trailer_url": "https://youtube.com/watch?v=abc1234",
                "trailer_data_json": {
                    "selected_videos": [
                        {"key": "abc1234", "type": "Trailer", "official": True},
                        {"key": "def5678", "type": "Teaser", "official": True},
                    ]
                },
                "source_videos_json": [],
            }

        def lock_movie_for_agent(self, movie_id, agent_name):
            movie = self.get_movie_by_id(movie_id)
            movie["is_locked"] = True
            return movie

        def update_video_downloader_success(self, movie_id, download_payload):
            self.success_payload = download_payload

    class FakeDownloader:
        def download_video(self, youtube_url, output_path):
            if "abc1234" in youtube_url:
                return "storage/source_videos/movie_1/trailer_abc1234.mp4"
            assert "def5678" in youtube_url
            return "storage/source_videos/movie_1/teaser_def5678.mp4"

    class FakeVideoMetadataService:
        def validate_16x9_source_video(self, video_path):
            assert video_path in {
                "storage/source_videos/movie_1/trailer_abc1234.mp4",
                "storage/source_videos/movie_1/teaser_def5678.mp4",
            }
            return {
                "valid": True,
                "metadata": {
                    "width": 1920,
                    "height": 1080,
                    "duration_seconds": 120.0,
                    "aspect_ratio_value": 1.778,
                    "aspect_ratio": "16:9",
                },
                "message": "valid video",
            }

    monkeypatch.setattr("app.agents.video_downloader_agent.agent.settings.video_source_dir", "storage/source_videos")

    repository = FakeRepository()
    agent = VideoDownloaderAgent(
        repository=repository,
        youtube_downloader_service=FakeDownloader(),
        video_metadata_service=FakeVideoMetadataService(),
    )

    result = agent.run_for_movie(movie_id=1)

    assert result["results"][0]["status"] == VIDEO_DOWNLOAD_COMPLETED
    assert result["completed"] == 1
    assert repository.success_payload is not None
    assert repository.success_payload["primary_source_video_path"] == "storage/source_videos/movie_1/trailer_abc1234.mp4"
    assert len(repository.success_payload["source_video_payloads"]) == 2
    assert repository.success_payload["source_video_payloads"][0]["width"] == 1920


def test_downloader_agent_allows_direct_movie_run_when_not_queued(monkeypatch):
    class FakeRepository:
        def __init__(self):
            self.success_payload = None

        def get_movie_by_id(self, movie_id):
            return {
                "id": movie_id,
                "movie_title": "Direct Run Movie",
                "tmdb_id": 103,
                "is_active": True,
                "is_locked": False,
                "next_agent": "SCENE_SELECTION_AGENT",
                "voice_status": VOICE_COMPLETED,
                "voice_audio_path": "storage/audio/movie_2_hash.mp3",
                "trailer_youtube_id": "xyz9876",
                "trailer_url": "https://youtube.com/watch?v=xyz9876",
                "trailer_data_json": {
                    "selected_videos": [
                        {"key": "xyz9876", "type": "Trailer", "official": True},
                    ]
                },
                "source_video_path": None,
                "source_videos_json": [],
            }

        def lock_movie_for_agent(self, movie_id, agent_name):
            movie = self.get_movie_by_id(movie_id)
            movie["is_locked"] = True
            return movie

        def update_video_downloader_success(self, movie_id, download_payload):
            self.success_payload = download_payload

    class FakeDownloader:
        def download_video(self, youtube_url, output_path):
            assert "xyz9876" in youtube_url
            return "storage/source_videos/movie_2/trailer_xyz9876.mp4"

    class FakeVideoMetadataService:
        def validate_16x9_source_video(self, video_path):
            assert "trailer_xyz9876.mp4" in video_path
            return {
                "valid": True,
                "metadata": {
                    "width": 1920,
                    "height": 1080,
                    "duration_seconds": 90.0,
                    "aspect_ratio_value": 1.778,
                    "aspect_ratio": "16:9",
                },
                "message": "valid video",
            }

    monkeypatch.setattr("app.agents.video_downloader_agent.agent.settings.video_source_dir", "storage/source_videos")

    repository = FakeRepository()
    agent = VideoDownloaderAgent(
        repository=repository,
        youtube_downloader_service=FakeDownloader(),
        video_metadata_service=FakeVideoMetadataService(),
    )

    result = agent.run_for_movie(movie_id=2)

    assert result["results"][0]["status"] == VIDEO_DOWNLOAD_COMPLETED
    assert result["completed"] == 1
    assert repository.success_payload is not None


def test_downloader_agent_skips_already_downloaded_and_fetches_remaining(monkeypatch):
    existing_file = PROJECT_ROOT / "storage/source_videos/movie_3/trailer_aaa111.mp4"
    existing_file.parent.mkdir(parents=True, exist_ok=True)
    existing_file.write_bytes(b"existing")

    class FakeRepository:
        def __init__(self):
            self.success_payload = None

        def get_movie_by_id(self, movie_id):
            return {
                "id": movie_id,
                "movie_title": "Partial Movie",
                "tmdb_id": 104,
                "is_active": True,
                "is_locked": False,
                "next_agent": "SCENE_SELECTION_AGENT",
                "voice_status": VOICE_COMPLETED,
                "voice_audio_path": "storage/audio/movie_3_hash.mp3",
                "trailer_data_json": {
                    "selected_videos": [
                        {"key": "aaa111", "type": "Trailer", "official": True},
                        {"key": "bbb222", "type": "Teaser", "official": True},
                    ]
                },
                "source_video_path": "storage/source_videos/movie_3/trailer_aaa111.mp4",
                "source_videos_json": [
                    {"source_video_path": "storage/source_videos/movie_3/trailer_aaa111.mp4", "label": "official_trailer"}
                ],
            }

        def lock_movie_for_agent(self, movie_id, agent_name):
            movie = self.get_movie_by_id(movie_id)
            movie["is_locked"] = True
            return movie

        def update_video_downloader_success(self, movie_id, download_payload):
            self.success_payload = download_payload

        def update_video_downloader_failed(self, movie_id, error_payload):
            raise AssertionError(error_payload["error_message"])

    class FakeDownloader:
        def download_video(self, youtube_url, output_path):
            assert "bbb222" in youtube_url
            return "storage/source_videos/movie_3/teaser_bbb222.mp4"

    class FakeVideoMetadataService:
        def validate_16x9_source_video(self, video_path):
            assert video_path == "storage/source_videos/movie_3/teaser_bbb222.mp4"
            return {
                "valid": True,
                "metadata": {
                    "width": 1920,
                    "height": 1080,
                    "duration_seconds": 45.0,
                    "aspect_ratio_value": 1.778,
                    "aspect_ratio": "16:9",
                },
                "message": "valid video",
            }

    monkeypatch.setattr("app.agents.video_downloader_agent.agent.settings.video_source_dir", "storage/source_videos")
    monkeypatch.setattr("app.agents.video_downloader_agent.agent.settings.video_downloader_max_videos", 3)

    repository = FakeRepository()
    agent = VideoDownloaderAgent(
        repository=repository,
        youtube_downloader_service=FakeDownloader(),
        video_metadata_service=FakeVideoMetadataService(),
    )

    result = agent.run_for_movie(movie_id=3)

    assert result["results"][0]["status"] == VIDEO_DOWNLOAD_COMPLETED
    assert repository.success_payload["primary_source_video_path"] == "storage/source_videos/movie_3/teaser_bbb222.mp4"
    assert len(repository.success_payload["source_video_payloads"]) == 1
    existing_file.unlink(missing_ok=True)


def test_downloader_third_failure_pauses_for_manual_recovery(monkeypatch):
    class FakeRepository:
        def __init__(self):
            self.failed_payload = None

        def update_video_downloader_failed(self, movie_id, error_payload):
            self.failed_payload = error_payload

        def update_video_downloader_waiting_source(self, movie_id, error_payload):
            raise AssertionError("third failure must not be requeued")

    class FakeDownloader:
        @staticmethod
        def is_transient_error(exc):
            return True

    monkeypatch.setattr("app.agents.video_downloader_agent.agent.settings.video_downloader_max_attempts", 3)
    repository = FakeRepository()
    agent = VideoDownloaderAgent(repository, FakeDownloader(), video_metadata_service=None)

    status = agent._mark_waiting_for_manual_source(
        movie_id=142,
        movie={
            "tmdb_id": 1061474,
            "movie_title": "Superman",
            "error_data_json": {"video_download_attempt_count": 2},
        },
        exc=ValueError("HTTP Error 403: Forbidden"),
        failed_candidate_keys={"trailer"},
    )

    assert status == VIDEO_DOWNLOAD_FAILED
    assert repository.failed_payload["error_data"]["video_download_attempt_count"] == 3
    assert repository.failed_payload["error_data"]["retry_exhausted"] is True
    assert repository.failed_payload["error_data"]["automatic_retry_blocked"] is True
    assert repository.failed_payload["error_data"]["manual_source_url_required"] is True


def test_downloader_failure_before_limit_is_requeued(monkeypatch):
    class FakeRepository:
        def __init__(self):
            self.retry_payload = None

        def update_video_downloader_failed(self, movie_id, error_payload):
            raise AssertionError("second failure must still be retried")

        def update_video_downloader_waiting_source(self, movie_id, error_payload):
            self.retry_payload = error_payload

    class FakeDownloader:
        @staticmethod
        def is_transient_error(exc):
            return True

    monkeypatch.setattr("app.agents.video_downloader_agent.agent.settings.video_downloader_max_attempts", 3)
    repository = FakeRepository()
    agent = VideoDownloaderAgent(repository, FakeDownloader(), video_metadata_service=None)

    status = agent._mark_waiting_for_manual_source(
        movie_id=142,
        movie={
            "tmdb_id": 1061474,
            "movie_title": "Superman",
            "error_data_json": {"video_download_attempt_count": 1},
        },
        exc=ValueError("HTTP Error 403: Forbidden"),
    )

    assert status == "WAITING_SOURCE_VIDEO"
    assert repository.retry_payload["error_data"]["video_download_attempt_count"] == 2
    assert repository.retry_payload["error_data"]["retry_exhausted"] is False


def test_direct_movie_retry_ignores_previous_failed_candidate_keys():
    agent = VideoDownloaderAgent(
        repository=None,
        youtube_downloader_service=None,
        video_metadata_service=None,
    )
    movie = {
        "error_data_json": {"failed_candidate_keys": ["blocked-video"]},
        "trailer_data_json": {
            "selected_videos": [
                {"key": "blocked-video", "type": "Trailer"},
            ],
        },
    }

    regular_candidates = agent._video_candidates(movie)
    retry_candidates = agent._video_candidates(movie, ignore_failed_candidates=True)

    assert regular_candidates == []
    assert retry_candidates[0]["youtube_id"] == "blocked-video"
