import json

from app.agents.scene_selection_agent.agent import SceneSelectionAgent
from app.core.agent_status import (
    NEXT_AGENT_SCENE_SELECTION,
    SCENE_COMPLETED,
    SCENE_FAILED,
    SCENE_WAITING_SOURCE_VIDEO,
    SCENE_WAITING_VOICE_AUDIO,
    VOICE_COMPLETED,
)
from app.services.gemini_video_service import GeminiVideoService
from app.services.visual_scene_selection_service import VisualSceneSelectionService
import concurrent.futures


def test_scene_selection_agent_marks_waiting_when_voice_is_missing():
    class FakeRepository:
        def __init__(self):
            self.waiting_voice_called = False

        def get_movie_by_id(self, movie_id):
            return {
                "id": movie_id,
                "movie_title": "Test Movie",
                "tmdb_id": 101,
                "is_active": True,
                "is_locked": False,
                "next_agent": NEXT_AGENT_SCENE_SELECTION,
                "scene_status": "PENDING",
                "voice_status": "PENDING",
                "voice_audio_path": None,
            }

        def update_scene_waiting_voice_audio(self, movie_id, error_payload):
            self.waiting_voice_called = True

    repository = FakeRepository()
    agent = SceneSelectionAgent(
        repository=repository,
        audio_metadata_service=None,
        video_metadata_service=None,
        gemini_video_service=None,
    )

    result = agent.run_for_movie(movie_id=1)

    assert result["results"][0]["status"] == SCENE_WAITING_VOICE_AUDIO
    assert result["waiting_voice_audio"] == 1
    assert repository.waiting_voice_called is True


def test_scene_selection_agent_marks_waiting_when_no_valid_source_video():
    class FakeRepository:
        def __init__(self):
            self.waiting_source_called = False

        def get_movie_by_id(self, movie_id):
            return {
                "id": movie_id,
                "movie_title": "Test Movie",
                "tmdb_id": 102,
                "is_active": True,
                "is_locked": False,
                "next_agent": NEXT_AGENT_SCENE_SELECTION,
                "scene_status": "PENDING",
                "voice_status": VOICE_COMPLETED,
                "voice_audio_path": "movie-audio/audio/test.mp3",
                "source_video_path": "storage/source_videos/bad.mp4",
                "source_videos_json": [],
            }

        def update_scene_waiting_source_video(self, movie_id, error_payload):
            self.waiting_source_called = True

    class FakeVideoMetadataService:
        def validate_16x9_source_video(self, video_path):
            return {"valid": False, "metadata": None, "message": "invalid source video"}

    repository = FakeRepository()
    agent = SceneSelectionAgent(
        repository=repository,
        audio_metadata_service=None,
        video_metadata_service=FakeVideoMetadataService(),
        gemini_video_service=None,
    )

    result = agent.run_for_movie(movie_id=1)

    assert result["results"][0]["status"] == SCENE_WAITING_SOURCE_VIDEO
    assert result["waiting_source_video"] == 1
    assert repository.waiting_source_called is True


def test_scene_selection_agent_completes_with_valid_scene_plan(monkeypatch):
    class FakeRepository:
        def __init__(self):
            self.success_payload = None

        def get_movie_by_id(self, movie_id):
            return {
                "id": movie_id,
                "movie_title": "Test Movie",
                "tmdb_id": 103,
                "is_active": True,
                "is_locked": False,
                "next_agent": NEXT_AGENT_SCENE_SELECTION,
                "scene_status": "PENDING",
                "voice_status": VOICE_COMPLETED,
                "voice_audio_path": "movie-audio/audio/test.mp3",
                "source_video_path": "storage/source_videos/test.mp4",
                "source_videos_json": [],
                "script_data_json": {"title": "Test Script"},
                "final_script": "Ruko bhai...",
                "target_genres_json": ["Action"],
            }

        def lock_movie_for_agent(self, movie_id, agent_name):
            movie = self.get_movie_by_id(movie_id)
            movie["is_locked"] = True
            return movie

        def update_scene_success(self, movie_id, scene_payload):
            self.success_payload = scene_payload

    class FakeAudioMetadataService:
        def get_audio_duration_seconds(self, audio_path):
            return 38.0

    class FakeVideoMetadataService:
        def validate_16x9_source_video(self, video_path):
            return {
                "valid": True,
                "metadata": {
                    "width": 1920,
                    "height": 1080,
                    "duration_seconds": 120.0,
                    "aspect_ratio_value": 1.777,
                    "aspect_ratio": "16:9",
                },
                "message": "valid 16:9 video",
            }

    class FakeGeminiVideoService:
        def analyze_video_for_scenes(self, source_videos, movie_context, voice_duration_seconds, target_duration_seconds, extra_visual_seconds_after_voice):
            assert round(voice_duration_seconds, 1) == 38.0
            assert round(target_duration_seconds, 1) == 45.0
            return {
                "agent": "SCENE_SELECTION_AGENT",
                "target_duration_seconds": target_duration_seconds,
                "estimated_total_duration_seconds": 44.5,
                "source_videos_used": [
                    {
                        "label": source_videos[0]["label"],
                        "source_video_path": source_videos[0]["source_video_path"],
                        "type": source_videos[0]["type"],
                        "aspect_ratio": "16:9",
                    }
                ],
                "scenes": [
                    {
                        "order": 1,
                        "source_video_label": source_videos[0]["label"],
                        "source_video_path": source_videos[0]["source_video_path"],
                        "start": "00:00:00.000",
                        "end": "00:00:04.000",
                        "duration_seconds": 4.0,
                        "scene_type": "hook",
                        "mood": "hype",
                        "visual_energy": "high",
                        "transition_after": "flash_cut",
                        "transition_duration_seconds": 0.12,
                        "zoom": "slow_zoom_in",
                        "speed": "normal",
                        "text_overlay_suggestion": "Ruko ruko bhai...",
                        "reason": "Strong hook",
                        "score": 9,
                    }
                ],
                "warnings": [],
            }

    monkeypatch.setattr("app.agents.scene_selection_agent.agent.settings.scene_extra_seconds_after_voice", 7.0)
    monkeypatch.setattr("app.agents.scene_selection_agent.agent.settings.scene_extra_seconds_min", 5.0)
    monkeypatch.setattr("app.agents.scene_selection_agent.agent.settings.scene_extra_seconds_max", 10.0)

    repository = FakeRepository()
    agent = SceneSelectionAgent(
        repository=repository,
        audio_metadata_service=FakeAudioMetadataService(),
        video_metadata_service=FakeVideoMetadataService(),
        gemini_video_service=FakeGeminiVideoService(),
    )

    result = agent.run_for_movie(movie_id=1)

    assert result["results"][0]["status"] == SCENE_COMPLETED
    assert result["completed"] == 1
    assert repository.success_payload is not None


def test_gemini_scene_plan_validation_retries_when_total_duration_is_too_short():
    service = object.__new__(GeminiVideoService)
    validation = service.validate_scene_plan(
        scene_plan={
            "scenes": [
                {
                    "order": 1,
                    "source_video_label": "official_trailer",
                    "source_video_path": "storage/source_videos/test.mp4",
                    "start": "00:00:00.000",
                    "end": "00:00:02.000",
                    "duration_seconds": 2.0,
                    "transition_after": "cut",
                    "zoom": "none",
                    "speed": "normal",
                    "score": 8,
                }
            ]
        },
        source_videos=[
            {
                "label": "official_trailer",
                "source_video_path": "storage/source_videos/test.mp4",
                "type": "trailer",
                "aspect_ratio": "16:9",
            }
        ],
        voice_duration_seconds=38.0,
        target_duration_seconds=45.0,
    )

    assert validation["valid"] is False
    assert "retry_reason" in validation


def test_gemini_analysis_retries_short_plans_until_duration_is_valid(monkeypatch):
    service = object.__new__(GeminiVideoService)
    source = {
        "label": "official_trailer",
        "source_video_path": "storage/source_videos/test.mp4",
        "type": "trailer",
        "aspect_ratio": "16:9",
    }

    def plan(scene_count):
        return json.dumps(
            {
                "scenes": [
                    {
                        "order": index + 1,
                        "source_video_label": source["label"],
                        "source_video_path": source["source_video_path"],
                        "start": service._seconds_to_timestamp(index * 5 + 1),
                        "end": service._seconds_to_timestamp(index * 5 + 5),
                        "duration_seconds": 4.0,
                    }
                    for index in range(scene_count)
                ]
            }
        )

    responses = iter([plan(1), plan(2), plan(4)])
    prompts = []
    monkeypatch.setattr(service, "_upload_video", lambda _path: object())
    monkeypatch.setattr(
        service,
        "_generate_response_text",
        lambda prompt, uploaded_files: prompts.append(prompt) or next(responses),
    )

    result = service.analyze_video_for_scenes(
        source_videos=[source],
        movie_context={"genres": ["Drama"], "overview": "A family story."},
        voice_duration_seconds=15.0,
        target_duration_seconds=20.0,
        extra_visual_seconds_after_voice=5.0,
    )

    assert len(result["scenes"]) == 4
    assert len(prompts) == 3
    assert "Minimum number of distinct scenes required:\n5" in prompts[0]
    assert "Selected scenes total only 8.0 seconds" in prompts[2]


def test_scene_selection_agent_force_bypasses_next_agent_check():
    class FakeRepository:
        def get_movie_by_id(self, movie_id):
            return {
                "id": movie_id,
                "movie_title": "Test Movie",
                "tmdb_id": 104,
                "is_active": True,
                "is_locked": False,
                "next_agent": "VOICE_GENERATOR_AGENT",
                "scene_status": "COMPLETED",
                "voice_status": VOICE_COMPLETED,
                "voice_audio_path": "movie-audio/audio/test.mp3",
                "source_video_path": "storage/source_videos/test.mp4",
                "source_videos_json": [],
            }

        def lock_movie_for_agent(self, movie_id, agent_name):
            return self.get_movie_by_id(movie_id)

        def update_scene_success(self, movie_id, scene_payload):
            self.scene_payload = scene_payload

    class FakeAudioMetadataService:
        def get_audio_duration_seconds(self, audio_path):
            return 40.0

    class FakeVideoMetadataService:
        def validate_16x9_source_video(self, video_path):
            return {
                "valid": True,
                "metadata": {
                    "width": 1920,
                    "height": 1080,
                    "duration_seconds": 90.0,
                    "aspect_ratio_value": 1.777,
                    "aspect_ratio": "16:9",
                },
                "message": "valid 16:9 video",
            }

    class FakeGeminiVideoService:
        def analyze_video_for_scenes(self, source_videos, movie_context, voice_duration_seconds, target_duration_seconds, extra_visual_seconds_after_voice):
            return {
                "target_duration_seconds": target_duration_seconds,
                "estimated_total_duration_seconds": target_duration_seconds,
                "source_videos_used": source_videos,
                "scenes": [
                    {
                        "order": 1,
                        "source_video_label": source_videos[0]["label"],
                        "source_video_path": source_videos[0]["source_video_path"],
                        "start": "00:00:00.000",
                        "end": "00:00:04.000",
                        "duration_seconds": 4.0,
                        "transition_after": "cut",
                        "zoom": "none",
                        "speed": "normal",
                        "score": 8,
                    }
                ],
            }

    agent = SceneSelectionAgent(
        repository=FakeRepository(),
        audio_metadata_service=FakeAudioMetadataService(),
        video_metadata_service=FakeVideoMetadataService(),
        gemini_video_service=FakeGeminiVideoService(),
    )

    result = agent.run_for_movie(movie_id=1, force=True)

    assert result["results"][0]["status"] == SCENE_COMPLETED
    assert result["failed"] == 0


def test_scene_selection_agent_uses_visual_fallback_when_gemini_fails():
    class FakeRepository:
        def __init__(self):
            self.scene_payload = None

        def get_movie_by_id(self, movie_id):
            return {
                "id": movie_id,
                "movie_title": "Fallback Movie",
                "tmdb_id": 105,
                "is_active": True,
                "is_locked": False,
                "next_agent": NEXT_AGENT_SCENE_SELECTION,
                "scene_status": "PENDING",
                "voice_status": VOICE_COMPLETED,
                "voice_audio_path": "movie-audio/audio/test.mp3",
                "source_video_path": "storage/source_videos/test.mp4",
                "source_videos_json": [],
                "script_data_json": {"title": "Test Script"},
                "final_script": "Fallback script",
                "target_genres_json": ["Action"],
            }

        def lock_movie_for_agent(self, movie_id, agent_name):
            movie = self.get_movie_by_id(movie_id)
            movie["is_locked"] = True
            return movie

        def update_scene_success(self, movie_id, scene_payload):
            self.scene_payload = scene_payload

    class FakeAudioMetadataService:
        def get_audio_duration_seconds(self, audio_path):
            return 35.0

    class FakeVideoMetadataService:
        def validate_16x9_source_video(self, video_path):
            return {
                "valid": True,
                "metadata": {"width": 1920, "height": 1080, "duration_seconds": 120.0, "aspect_ratio_value": 1.777, "aspect_ratio": "16:9"},
                "message": "valid 16:9 video",
            }

    class FailingGeminiService:
        def analyze_video_for_scenes(self, **kwargs):
            raise RuntimeError("Gemini down")

    class FakeVisualFallbackService:
        def build_scene_plan(self, source_videos, movie_context, voice_duration_seconds, target_duration_seconds, extra_visual_seconds_after_voice):
            return {
                "target_duration_seconds": target_duration_seconds,
                "estimated_total_duration_seconds": target_duration_seconds,
                "source_videos_used": source_videos,
                "scenes": [
                    {
                        "order": 1,
                        "source_video_label": source_videos[0]["label"],
                        "source_video_path": source_videos[0]["source_video_path"],
                        "start": "00:00:00.000",
                        "end": "00:00:04.000",
                        "duration_seconds": 4.0,
                        "transition_after": "cut",
                        "zoom": "none",
                        "speed": "normal",
                        "score": 8,
                    }
                ],
                "warnings": ["fallback"],
            }

    repository = FakeRepository()
    agent = SceneSelectionAgent(
        repository=repository,
        audio_metadata_service=FakeAudioMetadataService(),
        video_metadata_service=FakeVideoMetadataService(),
        gemini_video_service=FailingGeminiService(),
        visual_scene_selection_service=FakeVisualFallbackService(),
    )

    result = agent.run_for_movie(movie_id=1)

    assert result["results"][0]["status"] == SCENE_COMPLETED
    assert any(
        "fallback" in warning.lower()
        for warning in repository.scene_payload["scene_data"]["warnings"]
    )


def test_gemini_upload_video_times_out(monkeypatch):
    class FakeState:
        name = "PROCESSING"

    class FakeUploaded:
        name = "files/test"
        state = FakeState()

    class FakeFiles:
        def upload(self, file):
            return FakeUploaded()

        def get(self, name):
            return FakeUploaded()

    service = object.__new__(GeminiVideoService)
    service.client = type("Client", (), {"files": FakeFiles()})()

    monkeypatch.setattr("app.services.gemini_video_service.settings.gemini_file_processing_timeout_seconds", 30)
    monkeypatch.setattr("app.services.gemini_video_service.time.sleep", lambda seconds: None)

    ticks = iter([0.0, 31.0])
    monkeypatch.setattr("app.services.gemini_video_service.time.monotonic", lambda: next(ticks))
    monkeypatch.setattr("app.services.gemini_video_service.PROJECT_ROOT", __import__("pathlib").Path("."))

    try:
        service._upload_video("storage/source_videos/test.mp4")
        assert False, "Expected timeout"
    except TimeoutError as exc:
        assert "Gemini file processing timed out" in str(exc)


def test_gemini_generate_response_text_times_out(monkeypatch):
    service = object.__new__(GeminiVideoService)
    service.model_name = "gemini-test"

    class FakeModels:
        @staticmethod
        def generate_content(*args, **kwargs):
            return None

    service.client = type("Client", (), {"models": FakeModels()})()

    class FakeFuture:
        def result(self, timeout=None):
            raise concurrent.futures.TimeoutError()

        def cancel(self):
            return True

    class FakeExecutor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, *args, **kwargs):
            return FakeFuture()

    monkeypatch.setattr("app.services.gemini_video_service.ThreadPoolExecutor", lambda max_workers=1: FakeExecutor())
    monkeypatch.setattr("app.services.gemini_video_service.settings.gemini_generate_timeout_seconds", 30)

    try:
        service._generate_response_text("hello", [])
        assert False, "Expected timeout"
    except TimeoutError as exc:
        assert "Gemini scene generation timed out" in str(exc)


def test_gemini_scene_plan_validation_uses_timestamp_duration_when_model_duration_is_invalid():
    service = object.__new__(GeminiVideoService)
    validation = service.validate_scene_plan(
        scene_plan={
            "scenes": [
                {
                    "order": 1,
                    "source_video_label": "official_trailer",
                    "source_video_path": "storage/source_videos/test.mp4",
                    "start": "00:00:00.000",
                    "end": "00:00:04.200",
                    "duration_seconds": 9.5,
                    "transition_after": "cut",
                    "zoom": "none",
                    "speed": "normal",
                    "score": 8,
                },
                {
                    "order": 2,
                    "source_video_label": "official_trailer",
                    "source_video_path": "storage/source_videos/test.mp4",
                    "start": "00:00:04.200",
                    "end": "00:00:08.400",
                    "duration_seconds": 9.5,
                    "transition_after": "cut",
                    "zoom": "none",
                    "speed": "normal",
                    "score": 8,
                },
                {
                    "order": 3,
                    "source_video_label": "official_trailer",
                    "source_video_path": "storage/source_videos/test.mp4",
                    "start": "00:00:08.400",
                    "end": "00:00:12.600",
                    "duration_seconds": 9.5,
                    "transition_after": "cut",
                    "zoom": "none",
                    "speed": "normal",
                    "score": 8,
                },
            ]
        },
        source_videos=[
            {
                "label": "official_trailer",
                "source_video_path": "storage/source_videos/test.mp4",
                "type": "trailer",
                "aspect_ratio": "16:9",
            }
        ],
        voice_duration_seconds=7.0,
        target_duration_seconds=12.0,
    )

    assert validation["valid"] is True
    assert validation["scene_plan"]["scenes"][0]["duration_seconds"] == 4.2


def test_gemini_validation_removes_intro_and_outro_card_ranges():
    service = object.__new__(GeminiVideoService)
    source = {
        "label": "official_trailer",
        "source_video_path": "storage/source_videos/action.mp4",
        "type": "trailer",
        "aspect_ratio": "16:9",
        "duration_seconds": 120.0,
    }
    scenes = []
    for index, start in enumerate((5, 25, 35, 45, 55, 65, 75, 85, 95, 110), start=1):
        scenes.append(
            {
                "order": index,
                "source_video_label": "official_trailer",
                "source_video_path": source["source_video_path"],
                "start": f"00:{start // 60:02d}:{start % 60:02d}.000",
                "end": f"00:{(start + 5) // 60:02d}:{(start + 5) % 60:02d}.000",
                "duration_seconds": 5.0,
            }
        )

    validation = service.validate_scene_plan(
        scene_plan={"scenes": scenes},
        source_videos=[source],
        voice_duration_seconds=30.0,
        target_duration_seconds=40.0,
    )

    assert validation["valid"] is True
    starts = [scene["start"] for scene in validation["scene_plan"]["scenes"]]
    assert "00:00:05.000" not in starts
    assert "00:01:50.000" not in starts


def test_gemini_validation_accepts_exact_selectable_boundaries():
    service = object.__new__(GeminiVideoService)
    source_path = "storage/source_videos/trailer.mp4"
    scenes = [
        {
            "order": index + 1,
            "source_video_label": "official_trailer",
            "source_video_path": source_path,
            "start": service._seconds_to_timestamp(start),
            "end": service._seconds_to_timestamp(start + 5),
            "duration_seconds": 5.0,
        }
        for index, start in enumerate((25, 35, 45, 55, 65, 75, 85, 95))
    ]

    validation = service.validate_scene_plan(
        scene_plan={"scenes": scenes},
        source_videos=[{"label": "official_trailer", "source_video_path": source_path, "duration_seconds": 144.0}],
        voice_duration_seconds=30.0,
        target_duration_seconds=37.0,
    )

    assert validation["valid"] is True
    assert validation["scene_plan"]["scenes"][0]["start"] == "00:00:25.000"


def test_gemini_overlap_cleanup_keeps_disjoint_scenes_in_story_order():
    service = object.__new__(GeminiVideoService)
    source_path = "storage/source_videos/trailer.mp4"
    scenes = [
        {"order": 1, "source_video_path": source_path, "start": "00:01:20.000", "end": "00:01:25.000"},
        {"order": 2, "source_video_path": source_path, "start": "00:00:30.000", "end": "00:00:35.000"},
        {"order": 3, "source_video_path": source_path, "start": "00:01:23.000", "end": "00:01:28.000"},
    ]

    filtered = service._trim_overlaps(scenes)

    assert [scene["start"] for scene in filtered] == ["00:01:20.000", "00:00:30.000"]


def test_gemini_validation_trims_oversized_timestamp_range():
    service = object.__new__(GeminiVideoService)
    source_path = "storage/source_videos/action.mp4"
    scenes = []
    for index in range(8):
        start = 25 + (index * 10)
        scenes.append(
            {
                "order": index + 1,
                "source_video_label": "official_trailer",
                "source_video_path": source_path,
                "start": service._seconds_to_timestamp(start),
                "end": service._seconds_to_timestamp(start + 8),
                "duration_seconds": 8.0,
            }
        )

    validation = service.validate_scene_plan(
        scene_plan={"scenes": scenes},
        source_videos=[{"label": "official_trailer", "source_video_path": source_path, "duration_seconds": 120.0}],
        voice_duration_seconds=30.0,
        target_duration_seconds=40.0,
    )

    assert validation["valid"] is True
    assert all(scene["duration_seconds"] == 5.0 for scene in validation["scene_plan"]["scenes"])


def test_gemini_validation_requires_multiple_sources_when_available():
    service = object.__new__(GeminiVideoService)
    sources = [
        {"label": "official_trailer", "source_video_path": "storage/source_videos/trailer.mp4"},
        {"label": "teaser", "source_video_path": "storage/source_videos/teaser.mp4"},
    ]
    scenes = [
        {
            "order": index + 1,
            "source_video_label": "official_trailer",
            "source_video_path": sources[0]["source_video_path"],
            "start": service._seconds_to_timestamp(index * 4),
            "end": service._seconds_to_timestamp((index + 1) * 4),
            "duration_seconds": 4.0,
        }
        for index in range(3)
    ]

    validation = service.validate_scene_plan(
        scene_plan={"scenes": scenes},
        source_videos=sources,
        voice_duration_seconds=7.0,
        target_duration_seconds=12.0,
        movie_context={"genres": ["Drama"], "overview": "A family story."},
    )

    assert validation["valid"] is False
    assert "at least two" in validation["retry_reason"]


def test_gemini_validation_requires_visible_dinosaur_scenes_for_dinosaur_story():
    service = object.__new__(GeminiVideoService)
    sources = [
        {"label": "official_trailer", "source_video_path": "storage/source_videos/trailer.mp4"},
        {"label": "teaser", "source_video_path": "storage/source_videos/teaser.mp4"},
    ]
    scenes = []
    for index in range(6):
        source = sources[index % 2]
        scenes.append(
            {
                "order": index + 1,
                "source_video_label": source["label"],
                "source_video_path": source["source_video_path"],
                "start": service._seconds_to_timestamp(index * 5),
                "end": service._seconds_to_timestamp(index * 5 + 4),
                "duration_seconds": 4.0,
                "scene_type": "story",
                "reason": "Family looks around the neighborhood",
                "content_tags": ["family"],
            }
        )
    scenes[0]["reason"] = "A dinosaur attacks the family"
    scenes[0]["content_tags"] = ["dinosaur", "attack"]

    validation = service.validate_scene_plan(
        scene_plan={"scenes": scenes},
        source_videos=sources,
        voice_duration_seconds=19.0,
        target_duration_seconds=24.0,
        movie_context={"genres": ["Science Fiction"], "overview": "A family must survive dinosaurs."},
    )

    assert validation["valid"] is False
    assert "dinosaur story" in validation["retry_reason"]


def test_named_creature_story_requires_semantic_selection():
    service = object.__new__(GeminiVideoService)

    assert service.requires_semantic_selection(
        {"overview": "A family must escape from dinosaurs after a cosmic event."}
    ) is True
    assert service.requires_semantic_selection(
        {"overview": "A family repairs its relationships over one quiet summer."}
    ) is False


def test_visual_fallback_prefers_more_action_scenes_for_action_movies():
    service = VisualSceneSelectionService()
    candidates = [
            {
                "id": 1,
                "start": 2.0,
                "end": 6.5,
                "duration": 4.5,
                "activity_score": 8.2,
                "timeline_position": 0.06,
                "source_video_label": "official_trailer",
                "source_video_path": "storage/source_videos/test.mp4",
            },
        {
            "id": 2,
            "start": 18.0,
            "end": 23.0,
            "duration": 5.0,
            "activity_score": 9.0,
            "timeline_position": 0.22,
            "source_video_label": "official_trailer",
            "source_video_path": "storage/source_videos/test.mp4",
        },
        {
            "id": 3,
            "start": 40.0,
            "end": 45.0,
            "duration": 5.0,
            "activity_score": 9.2,
            "timeline_position": 0.48,
            "source_video_label": "official_trailer",
            "source_video_path": "storage/source_videos/test.mp4",
        },
        {
            "id": 4,
            "start": 62.0,
            "end": 67.0,
            "duration": 5.0,
            "activity_score": 9.3,
            "timeline_position": 0.68,
            "source_video_label": "official_trailer",
            "source_video_path": "storage/source_videos/test.mp4",
        },
        {
            "id": 5,
            "start": 79.0,
            "end": 84.0,
            "duration": 5.0,
            "activity_score": 9.4,
            "timeline_position": 0.82,
            "source_video_label": "official_trailer",
            "source_video_path": "storage/source_videos/test.mp4",
        },
        {
            "id": 6,
            "start": 96.0,
            "end": 101.0,
            "duration": 5.0,
            "activity_score": 9.1,
            "timeline_position": 0.92,
            "source_video_label": "official_trailer",
            "source_video_path": "storage/source_videos/test.mp4",
        },
    ]

    selected = service._select_fallback_scenes(
        candidates=candidates,
        target_duration_seconds=28.0,
        min_scene_duration=4.0,
        max_scene_duration=5.0,
        action_mode=True,
    )

    action_count = sum(1 for scene in selected if scene["scene_type"] == "action")
    assert action_count >= 3
