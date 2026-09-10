from app.agents.cut_merge_agent.agent import CutMergeAgent
from app.core.agent_status import NEXT_AGENT_CUT_MERGE, RENDER_COMPLETED, SCENE_COMPLETED


def test_cut_merge_agent_completes_with_scene_json():
    class FakeRepository:
        def __init__(self):
            self.render_payload = None

        def get_movie_by_id(self, movie_id):
            return {
                "id": movie_id,
                "movie_title": "Render Movie",
                "tmdb_id": 501,
                "is_active": True,
                "is_locked": False,
                "next_agent": NEXT_AGENT_CUT_MERGE,
                "scene_status": SCENE_COMPLETED,
                "scene_data_json": {
                    "scenes": [
                        {
                            "source_video_path": "storage/source_videos/movie_1/trailer.mp4",
                            "start": "00:00:00.000",
                            "end": "00:00:04.000",
                        }
                    ],
                    "source_videos_used": [],
                },
            }

        def lock_movie_for_agent(self, movie_id, agent_name):
            movie = self.get_movie_by_id(movie_id)
            movie["is_locked"] = True
            return movie

        def update_cut_merge_success(self, movie_id, render_payload):
            self.render_payload = render_payload

        def update_cut_merge_failed(self, movie_id, error_payload):
            raise AssertionError(error_payload["error_message"])

    class FakeCutMergeService:
        def render_master_video(self, movie_id, scene_plan, output_dir):
            assert movie_id == 1
            assert len(scene_plan["scenes"]) == 1
            assert "movie_1" in output_dir
            return {
                "master_video_path": "storage/final_videos/movie_1/movie_1_master_16x9_20260628_000000.mp4",
                "clip_count": 1,
                "transitions_used": ["cut"],
            }

    repository = FakeRepository()
    agent = CutMergeAgent(repository=repository, cut_merge_service=FakeCutMergeService())

    result = agent.run_for_movie(movie_id=1)

    assert result["results"][0]["status"] == RENDER_COMPLETED
    assert result["success"] is True
    assert result["agent"] == "CUT_MERGE_AGENT"
    assert repository.render_payload["master_video_path"] == "storage/final_videos/movie_1/movie_1_master_16x9_20260628_000000.mp4"
    assert repository.render_payload["render_data"]["next_agent"] == "SHORTS_COMPOSER_AGENT"


def test_cut_merge_agent_force_still_requires_completed_scenes():
    class FakeRepository:
        def get_movie_by_id(self, movie_id):
            return {
                "id": movie_id,
                "movie_title": "Render Movie",
                "tmdb_id": 501,
                "is_active": True,
                "is_locked": False,
                "next_agent": "SOMETHING_ELSE",
                "scene_status": "PENDING",
                "scene_data_json": {"scenes": []},
            }

    agent = CutMergeAgent(repository=FakeRepository(), cut_merge_service=object())
    result = agent.run_for_movie(movie_id=1, force=True)

    assert result["failed"] == 1
    assert result["results"][0]["error"] == "Movie scenes are not ready."
