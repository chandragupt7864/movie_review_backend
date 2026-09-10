from pathlib import Path

from app.services.audio_metadata_service import AudioMetadataService


def test_read_duration_from_supabase_uses_reopenable_temp_file(monkeypatch):
    class FakeResponse:
        content = b"fake-mp3-bytes"

        @staticmethod
        def raise_for_status():
            return None

    monkeypatch.setattr(
        "app.services.audio_metadata_service.SupabaseStorageService.create_signed_url",
        lambda self, storage_path, expires_in=900: "https://example.com/audio.mp3",
    )
    monkeypatch.setattr(
        "app.services.audio_metadata_service.requests.get",
        lambda url, timeout=60: FakeResponse(),
    )

    captured_path: dict[str, Path] = {}

    def fake_read_duration(self, file_path: Path) -> float:
        captured_path["path"] = file_path
        assert file_path.exists()
        return 12.5

    monkeypatch.setattr(AudioMetadataService, "_read_duration_from_file", fake_read_duration)

    service = AudioMetadataService()
    duration = service._read_duration_from_supabase("audio/sample.mp3")

    assert duration == 12.5
    assert "path" in captured_path
    assert not captured_path["path"].exists()
