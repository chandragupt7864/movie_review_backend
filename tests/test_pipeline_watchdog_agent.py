from pathlib import Path

from app.agents.pipeline_watchdog_agent.agent import PipelineWatchdogAgent
from app.config import PROJECT_ROOT


def test_watchdog_cleans_trailer_discovery_data():
    class FakeRepository:
        def __init__(self):
            self.updated_trailer_data = None

        def update_trailer_data_json(self, movie_id, trailer_data, timeline_event, removed_labels):
            self.updated_trailer_data = {
                "movie_id": movie_id,
                "trailer_data": trailer_data,
                "removed_labels": removed_labels,
                "timeline_event": timeline_event,
            }

    repository = FakeRepository()
    agent = PipelineWatchdogAgent(repository=repository)

    result = agent._clean_trailer_discovery_data(
        movie_id=7,
        movie={
            "id": 7,
            "tmdb_id": 700,
            "trailer_data_json": {
                "selected_videos": [
                    {"site": "YouTube", "type": "Trailer", "key": "trailer-1", "name": "Official Trailer"},
                    {"site": "YouTube", "type": "Clip", "key": "clip-1", "name": "Fight Clip"},
                ],
                "tmdb_videos_response": {
                    "results": [
                        {"site": "YouTube", "type": "Trailer", "key": "trailer-1", "name": "Official Trailer"},
                        {"site": "YouTube", "type": "Featurette", "key": "featurette-1", "name": "Behind the Scenes"},
                        {"site": "Vimeo", "type": "Trailer", "key": "vimeo-1", "name": "Vimeo Trailer"},
                    ]
                },
            },
        },
    )

    assert len(result["removed"]) == 3
    assert repository.updated_trailer_data is not None
    assert [item["key"] for item in repository.updated_trailer_data["trailer_data"]["selected_videos"]] == ["trailer-1"]
    assert repository.updated_trailer_data["trailer_data"]["selected_video"]["key"] == "trailer-1"
    assert [
        item["key"] for item in repository.updated_trailer_data["trailer_data"]["tmdb_videos_response"]["results"]
    ] == ["trailer-1"]


def test_watchdog_run_scans_non_waiting_pipeline_movies_and_cleans_source_videos():
    trailer_path = PROJECT_ROOT / "storage/source_videos/movie_99/trailer_valid.mp4"
    trailer_path.parent.mkdir(parents=True, exist_ok=True)
    trailer_path.write_bytes(b"valid")

    class FakeRepository:
        def __init__(self):
            self.movie = {
                "id": 99,
                "tmdb_id": 9900,
                "movie_title": "Cleanup Movie",
                "is_locked": False,
                "current_agent": None,
                "scene_status": "COMPLETED",
                "source_video_path": str(trailer_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "source_videos_json": [
                    {
                        "label": "official_trailer",
                        "type": "trailer",
                        "source_video_path": str(trailer_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                    },
                    {
                        "label": "fight_clip",
                        "type": "clip",
                        "source_video_path": "storage/source_videos/movie_99/fight_clip.mp4",
                    },
                ],
                "trailer_data_json": {},
                "error_data_json": {},
                "trailer_youtube_id": None,
            }
            self.updated_source_videos = None

        def get_watchdog_candidates(self, limit):
            return [self.movie]

        def get_movie_by_id(self, movie_id):
            return self.movie

        def update_source_videos_json(self, movie_id, kept_videos, removed_labels, timeline_event):
            self.updated_source_videos = {
                "movie_id": movie_id,
                "kept_videos": kept_videos,
                "removed_labels": removed_labels,
                "timeline_event": timeline_event,
            }
            self.movie["source_videos_json"] = kept_videos

        def reset_scene_to_pending(self, movie_id, timeline_event):
            raise AssertionError("scene reset should not be triggered")

        def requeue_for_video_downloader(self, movie_id, timeline_event):
            raise AssertionError("requeue should not be triggered")

    repository = FakeRepository()
    agent = PipelineWatchdogAgent(repository=repository)

    try:
        result = agent.run(limit=10)
    finally:
        trailer_path.unlink(missing_ok=True)

    assert result["processed"] == 1
    assert result["fixed"] == 1
    assert repository.updated_source_videos is not None
    assert [item["label"] for item in repository.updated_source_videos["kept_videos"]] == ["official_trailer"]
    assert "fight_clip" in repository.updated_source_videos["removed_labels"][0]


def test_watchdog_does_not_requeue_completed_movie_with_trailer_metadata():
    class FakeRepository:
        def requeue_for_video_downloader(self, movie_id, timeline_event):
            raise AssertionError("completed movie must not be requeued")

    agent = PipelineWatchdogAgent(repository=FakeRepository())

    requeued = agent._maybe_requeue_video_downloader(
        movie_id=12,
        movie={
            "next_agent": "DONE",
            "trailer_data_json": {
                "selected_videos": [
                    {"site": "YouTube", "type": "Trailer", "key": "trailer", "name": "Official Trailer"}
                ]
            },
            "error_data_json": {},
        },
    )

    assert requeued is False


def test_watchdog_requeues_manual_movie_when_an_untried_candidate_exists():
    class FakeRepository:
        def __init__(self):
            self.requeued = False

        def requeue_for_video_downloader(self, movie_id, timeline_event):
            self.requeued = movie_id == 21

    repository = FakeRepository()
    agent = PipelineWatchdogAgent(repository=repository)

    requeued = agent._maybe_requeue_video_downloader(
        movie_id=21,
        movie={
            "next_agent": "VIDEO_DOWNLOADER_AGENT",
            "trailer_data_json": {
                "selected_videos": [
                    {"site": "YouTube", "type": "Trailer", "key": "failed", "name": "Official Trailer"},
                    {"site": "YouTube", "type": "Teaser", "key": "untried", "name": "Official Teaser"},
                ]
            },
            "error_data_json": {
                "manual_source_url_required": True,
                "failed_candidate_keys": ["failed"],
            },
        },
    )

    assert requeued is True
    assert repository.requeued is True


def test_watchdog_does_not_requeue_movie_already_pending_without_manual_error():
    class FakeRepository:
        def requeue_for_video_downloader(self, movie_id, timeline_event):
            raise AssertionError("already queued movie must not be requeued")

    agent = PipelineWatchdogAgent(repository=FakeRepository())

    requeued = agent._maybe_requeue_video_downloader(
        movie_id=22,
        movie={
            "next_agent": "VIDEO_DOWNLOADER_AGENT",
            "overall_status": "WAITING_SOURCE_VIDEO",
            "video_download_status": "PENDING",
            "trailer_data_json": {
                "selected_videos": [
                    {"site": "YouTube", "type": "Trailer", "key": "ready", "name": "Official Trailer"}
                ]
            },
            "error_data_json": {},
        },
    )

    assert requeued is False
