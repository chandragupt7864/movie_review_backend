from app.agents.voice_generator_agent.agent import VoiceGeneratorAgent
from app.config import settings
from app.services.elevenlabs_tts_service import ElevenLabsTTSService


def test_elevenlabs_service_removes_supported_emotion_tags_only():
    service = object.__new__(ElevenLabsTTSService)

    cleaned = service.clean_voice_text("[Excited] Ruko bhai... [Whisper] movie ka naam Matinee hai.")

    assert cleaned == "Ruko bhai... movie ka naam Matinee hai."


def test_elevenlabs_script_hash_changes_with_voice_or_model():
    service = object.__new__(ElevenLabsTTSService)

    first = service.get_script_hash("Ruko bhai...", "alex", "eleven_v3")
    second = service.get_script_hash("Ruko bhai...", "other", "eleven_v3")
    third = service.get_script_hash("Ruko bhai...", "alex", "other_model")

    assert first != second
    assert first != third
    assert len(first) == 64


def test_voice_agent_reuses_supabase_audio_without_calling_elevenlabs(monkeypatch):
    class FakeTTS:
        voice_name = "Alex"
        voice_id = "alex_voice"
        model_id = "eleven_v3"

        def generate_audio(self, text, output_path):
            raise AssertionError("ElevenLabs should not be called when storage cache exists.")

    class FakeStorage:
        def file_exists(self, storage_path):
            return True

    monkeypatch.setattr(settings, "upload_audio_to_supabase", True)
    monkeypatch.setattr(settings, "supabase_audio_bucket", "movie-audio")

    agent = VoiceGeneratorAgent(tts_service=FakeTTS(), repository=None, storage_service=FakeStorage())

    metadata = agent._generate_or_reuse_audio(
        text="Ruko bhai...",
        local_audio_path="storage/audio/movie_1_hash.mp3",
        storage_path="audio/movie_1_hash.mp3",
        script_hash="hash",
    )

    assert metadata["cached"] is True
    assert metadata["uploaded_to_supabase"] is True
    assert metadata["voice_audio_path"] == "movie-audio/audio/movie_1_hash.mp3"
    assert metadata["storage_path"] == "audio/movie_1_hash.mp3"
