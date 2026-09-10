from requests.exceptions import ConnectionError as RequestsConnectionError

from app.services import tmdb_service as tmdb_module
from app.services.tmdb_service import TMDBService


def test_normalize_date_accepts_iso_date_only():
    assert TMDBService._normalize_date("2026-07-01") == "2026-07-01"
    assert TMDBService._normalize_date("2026-7-1") is None
    assert TMDBService._normalize_date("2026/07/01") is None
    assert TMDBService._normalize_date("") is None


def test_resolve_date_range_uses_month_precedence():
    assert TMDBService.resolve_date_range(year=2024, month=2, date_from=None, date_to=None) == (
        "2024-02-01",
        "2024-02-29",
    )


def test_build_selector_movie_payload_marks_selected():
    payload = TMDBService.build_selector_movie_payload(
        movie={
            "id": 123,
            "title": "Example Movie",
            "original_title": "Example Movie Original",
            "overview": "Overview",
            "release_date": "2025-07-10",
            "original_language": "en",
            "genre_ids": [28, 878],
            "poster_path": "/poster.jpg",
            "backdrop_path": "/backdrop.jpg",
            "vote_average": 7.8,
            "vote_count": 1200,
            "popularity": 350.5,
            "adult": False,
            "video": False,
        },
        genre_map={28: "Action", 878: "Science Fiction"},
        selected_ids={123},
    )

    assert payload["tmdb_id"] == 123
    assert payload["genre_names"] == ["Action", "Science Fiction"]
    assert payload["is_selected"] is True


def test_get_rebuilds_session_after_connection_reset(monkeypatch):
    class FailingSession:
        trust_env = False

        def get(self, *args, **kwargs):
            raise RequestsConnectionError("connection reset")

        def close(self):
            return None

    class SuccessfulResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": [{"id": 1}]}

    class SuccessfulSession:
        trust_env = False

        def get(self, *args, **kwargs):
            return SuccessfulResponse()

        def close(self):
            return None

    service = object.__new__(TMDBService)
    service.base_url = "https://api.themoviedb.org/3"
    service.headers = {}
    service.timeout = 5
    service.verify = False
    service.session = FailingSession()

    monkeypatch.setattr(tmdb_module.settings, "tmdb_api_key", "test-key")
    monkeypatch.setattr(tmdb_module.settings, "tmdb_retry_count", 3)
    monkeypatch.setattr(tmdb_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(service, "_build_session", lambda: SuccessfulSession())

    payload = service._get(endpoint="/search/movie", params={"query": "spider man"})

    assert payload["results"][0]["id"] == 1
    assert isinstance(service.session, SuccessfulSession)
