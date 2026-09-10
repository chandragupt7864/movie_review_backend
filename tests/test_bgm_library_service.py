from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import UploadFile

from app.services.bgm_library_service import BGMLibraryService
from app.services.music_copyright_assessment_service import MusicCopyrightAssessmentService


def test_upload_returns_existing_track_for_duplicate(monkeypatch):
    existing_track = {"id": 7, "track_code": "BGM-000007", "display_name": "Existing", "created_at": None}

    class FakeRepository:
        def get_bgm_by_sha256(self, sha256_hash):
            return existing_track

    temp_holder: dict[str, Path] = {}

    def fake_save_temp(file, suffix):
        with NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            temp_path = Path(handle.name)
            handle.write(b"duplicate-audio")
        temp_holder["path"] = temp_path
        return temp_path

    monkeypatch.setattr(BGMLibraryService, "_save_temp_upload", staticmethod(fake_save_temp))

    service = BGMLibraryService(repository=FakeRepository())
    upload = UploadFile(filename="duplicate.mp3", file=BytesIO(b"ignored"))

    result = service.upload_track(upload)

    assert result["already_exists"] is True
    assert result["track"] == existing_track
    assert not temp_holder["path"].exists()


def test_copyright_assessment_defaults_to_unknown_on_no_match():
    service = MusicCopyrightAssessmentService()

    result = service.assess(
        technical_metadata={},
        embedded_metadata={},
        recognition_result={"status": "NOT_IDENTIFIED", "warning": "Recognition service unavailable"},
        trusted_track=None,
    )

    assert result["copyright_status"] == "UNKNOWN"
    assert result["copyright_risk_level"] == "UNKNOWN"
    assert result["analysis_data"]["recognition_warning"] == "Recognition service unavailable"
