import hashlib
import mimetypes
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import UploadFile

from app.config import PROJECT_ROOT, settings
from app.repositories.bgm_library_repository import BGMLibraryRepository
from app.services.bgm_audio_analysis_service import BGMAudioAnalysisService
from app.services.music_copyright_assessment_service import MusicCopyrightAssessmentService
from app.services.music_fingerprint_service import MusicFingerprintService
from app.services.music_recognition_service import MusicRecognitionService
from app.services.supabase_storage_service import SupabaseStorageService
from app.services.cloudinary_video_storage_service import CloudinaryVideoStorageService


class BGMLibraryService:
    def __init__(
        self,
        repository: BGMLibraryRepository | None = None,
        analysis_service: BGMAudioAnalysisService | None = None,
        fingerprint_service: MusicFingerprintService | None = None,
        recognition_service: MusicRecognitionService | None = None,
        copyright_service: MusicCopyrightAssessmentService | None = None,
        storage_service: SupabaseStorageService | None = None,
    ) -> None:
        self.repository = repository or BGMLibraryRepository()
        self.analysis_service = analysis_service or BGMAudioAnalysisService()
        self.fingerprint_service = fingerprint_service or MusicFingerprintService()
        self.recognition_service = recognition_service or MusicRecognitionService()
        self.copyright_service = copyright_service or MusicCopyrightAssessmentService()
        self.storage_service = storage_service

    def upload_track(self, file: UploadFile) -> dict:
        original_filename = Path(file.filename or "").name
        extension = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else ""
        if extension not in settings.bgm_allowed_extensions:
            raise ValueError(f"Unsupported file type. Allowed: {', '.join(settings.bgm_allowed_extensions)}")

        temp_path = self._save_temp_upload(file=file, suffix=f".{extension}" if extension else "")
        try:
            sha256_hash = self._sha256(temp_path)
            existing = self.repository.get_bgm_by_sha256(sha256_hash)
            if existing:
                return {"success": True, "already_exists": True, "track": existing}

            self.analysis_service.validate_audio(temp_path)
            analysis_result = self.analysis_service.analyze(temp_path)
            fingerprint_result = self._fingerprint(temp_path)
            trusted_track = self.repository.get_verified_track_by_fingerprint(fingerprint_result.get("fingerprint") or "")
            recognition_result = self._recognize(fingerprint_result)
            assessment = self.copyright_service.assess(
                technical_metadata=analysis_result,
                embedded_metadata=analysis_result.get("embedded_metadata") or {},
                recognition_result=recognition_result,
                trusted_track=trusted_track,
            )
            analysis_status, analysis_warning = self._analysis_status(analysis_result, fingerprint_result, recognition_result)

            track_code = self.repository.get_next_track_code()
            display_name = self._display_name(original_filename, analysis_result, recognition_result)
            payload = {
                "track_code": track_code,
                "original_filename": original_filename,
                "display_name": display_name,
                "storage_bucket": None,
                "storage_path": None,
                "mime_type": file.content_type or mimetypes.guess_type(original_filename)[0] or "application/octet-stream",
                "file_extension": extension or None,
                "file_size_bytes": analysis_result.get("file_size_bytes"),
                "sha256_hash": sha256_hash,
                "duration_seconds": analysis_result.get("duration_seconds"),
                "codec": analysis_result.get("codec"),
                "bit_rate": analysis_result.get("bit_rate"),
                "sample_rate": analysis_result.get("sample_rate"),
                "channels": analysis_result.get("channels"),
                "audio_format": analysis_result.get("audio_format"),
                "bpm": analysis_result.get("bpm"),
                "tempo_category": analysis_result.get("tempo_category"),
                "energy_level": analysis_result.get("energy_level"),
                "loudness_lufs": analysis_result.get("loudness_lufs"),
                "peak_db": analysis_result.get("peak_db"),
                "is_instrumental": analysis_result.get("is_instrumental"),
                "technical_data_json": analysis_result.get("technical_data") or {},
                "embedded_metadata_json": analysis_result.get("embedded_metadata") or {},
                "fingerprint": fingerprint_result.get("fingerprint"),
                "fingerprint_provider": fingerprint_result.get("provider"),
                "recognition_provider": recognition_result.get("provider"),
                "recognition_status": recognition_result.get("status"),
                "recognized_title": recognition_result.get("title"),
                "recognized_artist": recognition_result.get("artist"),
                "recognized_album": recognition_result.get("album"),
                "recognized_release": recognition_result.get("release"),
                "recognized_recording_id": recognition_result.get("recording_id"),
                "recognized_musicbrainz_id": recognition_result.get("musicbrainz_id"),
                "recognition_confidence": recognition_result.get("confidence"),
                "recognition_data_json": recognition_result.get("raw_result") or {},
                "copyright_status": assessment.get("copyright_status"),
                "copyright_risk_level": assessment.get("copyright_risk_level"),
                "license_type": assessment.get("license_type"),
                "attribution_required": assessment.get("attribution_required"),
                "attribution_text": assessment.get("attribution_text"),
                "copyright_reason": assessment.get("reason"),
                "source_type": assessment.get("source_type"),
                "source_reference": assessment.get("source_reference"),
                "mood_tags_json": analysis_result.get("mood_tags") or [],
                "genre_tags_json": analysis_result.get("genre_tags") or [],
                "analysis_status": analysis_status,
                "analysis_warning": analysis_warning,
                "analysis_data_json": {
                    "fingerprint_warning": fingerprint_result.get("warning"),
                    "recognition_warning": recognition_result.get("warning"),
                    **(assessment.get("analysis_data") or {}),
                },
                "is_active": True,
            }
            created = self.repository.create_bgm_track(payload)
            storage_path = f"tracks/{track_code}/{sha256_hash}.{extension}"
            try:
                if settings.cloudinary_bgm_upload_enabled:
                    cloudinary_result = CloudinaryVideoStorageService().upload_library_bgm(
                        track_code=track_code,
                        local_file_path=str(temp_path),
                    )
                    updated = self.repository.update_bgm_storage(
                        created["id"],
                        "cloudinary",
                        cloudinary_result["secure_url"],
                    )
                else:
                    self._upload_to_supabase(temp_path, storage_path, payload["mime_type"])
                    updated = self.repository.update_bgm_storage(created["id"], settings.supabase_bgm_bucket, storage_path)
            except Exception:
                self.repository.delete_bgm_track(int(created["id"]))
                raise
            return {"success": True, "already_exists": False, "track": updated or created}
        finally:
            temp_path.unlink(missing_ok=True)

    def reanalyze_track(self, track_id: int) -> dict:
        track = self.repository.get_bgm_by_id(track_id)
        if not track:
            raise ValueError("Track not found.")
        if not track.get("storage_path"):
            raise ValueError("Stored audio path not found for reanalysis.")

        suffix = f".{track.get('file_extension')}" if track.get("file_extension") else ".tmp"
        with NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            temp_path = Path(handle.name)
        try:
            if track.get("storage_bucket") == "cloudinary" or str(track["storage_path"]).startswith("https://"):
                CloudinaryVideoStorageService().download_asset(
                    secure_url=str(track["storage_path"]),
                    local_file_path=str(temp_path),
                )
            else:
                self._get_storage_service().download_file(
                    storage_path=str(track["storage_path"]),
                    local_file_path=str(temp_path),
                    bucket=str(track.get("storage_bucket") or settings.supabase_bgm_bucket),
                )
            analysis_result = self.analysis_service.analyze(temp_path)
            fingerprint_result = self._fingerprint(temp_path)
            trusted_track = self.repository.get_verified_track_by_fingerprint(fingerprint_result.get("fingerprint") or "")
            recognition_result = self._recognize(fingerprint_result)
            assessment = self.copyright_service.assess(
                technical_metadata=analysis_result,
                embedded_metadata=analysis_result.get("embedded_metadata") or {},
                recognition_result=recognition_result,
                trusted_track=trusted_track,
            )
            analysis_status, analysis_warning = self._analysis_status(analysis_result, fingerprint_result, recognition_result)
            return self.repository.update_bgm_analysis(
                track_id,
                {
                    "display_name": self._display_name(track.get("original_filename") or "", analysis_result, recognition_result),
                    "mime_type": track.get("mime_type"),
                    "file_extension": track.get("file_extension"),
                    "file_size_bytes": analysis_result.get("file_size_bytes"),
                    "duration_seconds": analysis_result.get("duration_seconds"),
                    "codec": analysis_result.get("codec"),
                    "bit_rate": analysis_result.get("bit_rate"),
                    "sample_rate": analysis_result.get("sample_rate"),
                    "channels": analysis_result.get("channels"),
                    "audio_format": analysis_result.get("audio_format"),
                    "bpm": analysis_result.get("bpm"),
                    "tempo_category": analysis_result.get("tempo_category"),
                    "energy_level": analysis_result.get("energy_level"),
                    "loudness_lufs": analysis_result.get("loudness_lufs"),
                    "peak_db": analysis_result.get("peak_db"),
                    "is_instrumental": analysis_result.get("is_instrumental"),
                    "technical_data_json": analysis_result.get("technical_data") or {},
                    "embedded_metadata_json": analysis_result.get("embedded_metadata") or {},
                    "fingerprint": fingerprint_result.get("fingerprint"),
                    "fingerprint_provider": fingerprint_result.get("provider"),
                    "recognition_provider": recognition_result.get("provider"),
                    "recognition_status": recognition_result.get("status"),
                    "recognized_title": recognition_result.get("title"),
                    "recognized_artist": recognition_result.get("artist"),
                    "recognized_album": recognition_result.get("album"),
                    "recognized_release": recognition_result.get("release"),
                    "recognized_recording_id": recognition_result.get("recording_id"),
                    "recognized_musicbrainz_id": recognition_result.get("musicbrainz_id"),
                    "recognition_confidence": recognition_result.get("confidence"),
                    "recognition_data_json": recognition_result.get("raw_result") or {},
                    "copyright_status": assessment.get("copyright_status"),
                    "copyright_risk_level": assessment.get("copyright_risk_level"),
                    "license_type": assessment.get("license_type"),
                    "attribution_required": assessment.get("attribution_required"),
                    "attribution_text": assessment.get("attribution_text"),
                    "copyright_reason": assessment.get("reason"),
                    "source_type": assessment.get("source_type"),
                    "source_reference": assessment.get("source_reference"),
                    "mood_tags_json": analysis_result.get("mood_tags") or [],
                    "genre_tags_json": analysis_result.get("genre_tags") or [],
                    "analysis_status": analysis_status,
                    "analysis_warning": analysis_warning,
                    "analysis_data_json": {
                        "fingerprint_warning": fingerprint_result.get("warning"),
                        "recognition_warning": recognition_result.get("warning"),
                        **(assessment.get("analysis_data") or {}),
                    },
                },
            )
        finally:
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def serialize_track(row: dict) -> dict:
        if not row:
            return {}
        track_id = int(row["id"])
        return {
            "id": track_id,
            "track_code": row.get("track_code"),
            "original_filename": row.get("original_filename"),
            "display_name": row.get("display_name"),
            "duration_seconds": row.get("duration_seconds"),
            "codec": row.get("codec"),
            "bit_rate": row.get("bit_rate"),
            "bpm": row.get("bpm"),
            "tempo_category": row.get("tempo_category"),
            "energy_level": row.get("energy_level"),
            "recognized_title": row.get("recognized_title"),
            "recognized_artist": row.get("recognized_artist"),
            "recognition_confidence": row.get("recognition_confidence"),
            "copyright_status": row.get("copyright_status"),
            "copyright_risk_level": row.get("copyright_risk_level"),
            "license_type": row.get("license_type"),
            "attribution_required": row.get("attribution_required"),
            "analysis_status": row.get("analysis_status"),
            "created_at": BGMLibraryService._serialize_value(row.get("created_at")),
            "play_url_endpoint": f"/bgm/api/{track_id}/play-url",
        }

    @staticmethod
    def serialize_detail(row: dict) -> dict:
        detail = dict(row)
        for key in ("created_at", "updated_at"):
            detail[key] = BGMLibraryService._serialize_value(detail.get(key))
        return detail

    @staticmethod
    def _save_temp_upload(file: UploadFile, suffix: str) -> Path:
        temp_dir = PROJECT_ROOT / settings.bgm_temp_dir
        temp_dir.mkdir(parents=True, exist_ok=True)
        file.file.seek(0)
        with NamedTemporaryFile(delete=False, suffix=suffix, dir=temp_dir) as handle:
            temp_path = Path(handle.name)
            try:
                total_size = 0
                limit = settings.bgm_max_file_size_mb * 1024 * 1024
                while chunk := file.file.read(1024 * 1024):
                    total_size += len(chunk)
                    if total_size > limit:
                        raise ValueError(f"File too large. Max allowed size is {settings.bgm_max_file_size_mb} MB.")
                    handle.write(chunk)
            except Exception:
                temp_path.unlink(missing_ok=True)
                raise
        return temp_path

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _fingerprint(self, path: Path) -> dict:
        if not settings.bgm_fingerprint_enabled:
            return {"provider": "chromaprint", "fingerprint": None, "duration": None, "warning": "Fingerprinting disabled."}
        return self.fingerprint_service.generate(path)

    def _recognize(self, fingerprint_result: dict) -> dict:
        return self.recognition_service.identify(
            fingerprint=fingerprint_result.get("fingerprint"),
            duration=fingerprint_result.get("duration"),
        )

    def _upload_to_supabase(self, temp_path: Path, storage_path: str, content_type: str) -> None:
        try:
            self._get_storage_service().upload_audio(
                local_file_path=str(temp_path),
                storage_path=storage_path,
                bucket=settings.supabase_bgm_bucket,
                content_type=content_type,
            )
        except Exception as exc:
            raise ValueError(
                f"Supabase upload failed for bucket '{settings.supabase_bgm_bucket}'. Confirm the private bucket exists and service credentials are valid."
            ) from exc

    def _get_storage_service(self) -> SupabaseStorageService:
        if self.storage_service is None:
            self.storage_service = SupabaseStorageService()
        return self.storage_service

    @staticmethod
    def _display_name(original_filename: str, analysis_result: dict, recognition_result: dict) -> str:
        title = (analysis_result.get("embedded_metadata") or {}).get("title")
        if title:
            return str(title)
        if recognition_result.get("title"):
            artist = recognition_result.get("artist")
            return f"{recognition_result['title']} - {artist}" if artist else str(recognition_result["title"])
        return Path(original_filename).stem or "Untitled Track"

    @staticmethod
    def _analysis_status(analysis_result: dict, fingerprint_result: dict, recognition_result: dict) -> tuple[str, str | None]:
        warnings = []
        technical = analysis_result.get("technical_data") or {}
        for section in ("rhythm_analysis", "loudness_analysis"):
            warning = (technical.get(section) or {}).get("warning")
            if warning:
                warnings.append(str(warning))
        if fingerprint_result.get("warning"):
            warnings.append(str(fingerprint_result["warning"]))
        if recognition_result.get("warning"):
            warnings.append(str(recognition_result["warning"]))
        if warnings:
            return "COMPLETED_WITH_WARNINGS", "; ".join(dict.fromkeys(warnings))
        return "COMPLETED", None

    @staticmethod
    def _serialize_value(value):
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return value
