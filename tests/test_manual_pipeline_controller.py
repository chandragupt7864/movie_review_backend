from unittest.mock import patch

from app.core.agent_status import NEXT_AGENT_VIDEO_DOWNLOADER, OVERALL_WAITING_SOURCE_VIDEO
from app.services.manual_pipeline_controller import ManualPipelineController


def test_waiting_source_movie_runs_queued_downloader_instead_of_watchdog():
    controller = ManualPipelineController()
    movie = {
        "id": 42,
        "next_agent": NEXT_AGENT_VIDEO_DOWNLOADER,
        "overall_status": OVERALL_WAITING_SOURCE_VIDEO,
    }

    with (
        patch("app.services.manual_pipeline_controller.build_video_downloader_agent") as downloader_factory,
        patch("app.services.manual_pipeline_controller.build_pipeline_watchdog_agent") as watchdog_factory,
    ):
        assert controller._run_next_step(movie) is True

    downloader_factory.return_value.run_for_movie.assert_called_once_with(movie_id=42)
    watchdog_factory.assert_not_called()
