import requests

from app.config import settings


class MusicRecognitionService:
    def identify(self, fingerprint: str | None, duration: float | None) -> dict:
        provider = settings.music_recognition_provider
        if not fingerprint or not duration:
            return {
                "status": "NOT_IDENTIFIED",
                "provider": provider,
                "title": None,
                "artist": None,
                "album": None,
                "release": None,
                "recording_id": None,
                "musicbrainz_id": None,
                "confidence": None,
                "raw_result": {},
                "warning": "Fingerprint or duration missing.",
            }
        if not settings.bgm_recognition_enabled:
            return {
                "status": "NOT_IDENTIFIED",
                "provider": provider,
                "title": None,
                "artist": None,
                "album": None,
                "release": None,
                "recording_id": None,
                "musicbrainz_id": None,
                "confidence": None,
                "raw_result": {},
                "warning": "Recognition disabled by configuration.",
            }
        if provider != "acoustid":
            return {
                "status": "NOT_IDENTIFIED",
                "provider": provider,
                "title": None,
                "artist": None,
                "album": None,
                "release": None,
                "recording_id": None,
                "musicbrainz_id": None,
                "confidence": None,
                "raw_result": {},
                "warning": f"Unsupported provider: {provider}",
            }
        if not settings.acoustid_api_key:
            return {
                "status": "NOT_IDENTIFIED",
                "provider": provider,
                "title": None,
                "artist": None,
                "album": None,
                "release": None,
                "recording_id": None,
                "musicbrainz_id": None,
                "confidence": None,
                "raw_result": {},
                "warning": "ACOUSTID_API_KEY is not configured.",
            }

        try:
            response = requests.get(
                "https://api.acoustid.org/v2/lookup",
                params={
                    "client": settings.acoustid_api_key,
                    "meta": "recordings+releasegroups+compress",
                    "duration": int(round(float(duration))),
                    "fingerprint": fingerprint,
                },
                timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            return {
                "status": "NOT_IDENTIFIED",
                "provider": provider,
                "title": None,
                "artist": None,
                "album": None,
                "release": None,
                "recording_id": None,
                "musicbrainz_id": None,
                "confidence": None,
                "raw_result": {},
                "warning": f"Recognition service unavailable: {exc}",
            }

        results = payload.get("results") or []
        if not results:
            return {
                "status": "NOT_IDENTIFIED",
                "provider": provider,
                "title": None,
                "artist": None,
                "album": None,
                "release": None,
                "recording_id": None,
                "musicbrainz_id": None,
                "confidence": None,
                "raw_result": payload,
                "warning": None,
            }

        top = max(results, key=lambda item: item.get("score") or 0)
        recording = (top.get("recordings") or [{}])[0]
        artists = recording.get("artists") or []
        releasegroups = recording.get("releasegroups") or []
        artist_name = ", ".join(artist.get("name") for artist in artists if artist.get("name")) or None
        release_name = releasegroups[0].get("title") if releasegroups else None
        return {
            "status": "IDENTIFIED",
            "provider": provider,
            "title": recording.get("title"),
            "artist": artist_name,
            "album": release_name,
            "release": release_name,
            "recording_id": recording.get("id"),
            "musicbrainz_id": recording.get("id"),
            "confidence": float(top.get("score")) if top.get("score") is not None else None,
            "raw_result": payload,
            "warning": None,
        }
