from app.services.visual_scene_selection_service import VisualSceneSelectionService


def test_visual_fallback_expands_to_target_duration():
    service = VisualSceneSelectionService()
    candidates = []
    for index in range(12):
        candidates.append(
            {
                "start": float(index * 5),
                "end": float(index * 5 + 4.5),
                "duration": 4.5,
                "activity_score": 10.0 - (index * 0.1),
                "timeline_position": index / 12,
                "source_video_path": f"storage/source_videos/movie_1/trailer_{1 + (index % 3)}.mp4",
                "source_video_label": f"trailer_{1 + (index % 3)}",
            }
        )

    scenes = service._select_fallback_scenes(
        candidates=candidates,
        target_duration_seconds=40.0,
        min_scene_duration=4.0,
        max_scene_duration=5.0,
        action_mode=False,
    )

    assert len(scenes) >= 8
    assert sum(scene["duration_seconds"] for scene in scenes) >= 36.0
    assert sum(scene["duration_seconds"] for scene in scenes) <= 45.0


def test_action_mode_is_inferred_from_story_context_for_horror_action_movie():
    service = VisualSceneSelectionService()

    assert service._is_action_mode(
        {
            "genres": ["Horror"],
            "overview": "An immortal warrior is trapped in a war and must fight for humanity.",
        }
    ) is True


def test_action_mode_stays_off_for_non_kinetic_context():
    service = VisualSceneSelectionService()

    assert service._is_action_mode(
        {
            "genres": ["Drama"],
            "overview": "A quiet family rebuilds trust over one summer.",
        }
    ) is False


def test_visual_fallback_balances_sources_before_reusing_one():
    service = VisualSceneSelectionService()
    candidates = []
    for index in range(8):
        path = "storage/source_videos/trailer.mp4" if index < 6 else "storage/source_videos/teaser.mp4"
        candidates.append(
            {
                "start": float(index * 6),
                "end": float(index * 6 + 5),
                "duration": 5.0,
                "activity_score": 20.0 - index,
                "timeline_position": 0.1 + (index * 0.1),
                "source_video_path": path,
                "source_video_label": "trailer" if index < 6 else "teaser",
            }
        )

    scenes = service._select_fallback_scenes(
        candidates=candidates,
        target_duration_seconds=25.0,
        min_scene_duration=4.0,
        max_scene_duration=5.0,
        action_mode=True,
    )

    assert {scene["source_video_path"] for scene in scenes} == {
        "storage/source_videos/trailer.mp4",
        "storage/source_videos/teaser.mp4",
    }
