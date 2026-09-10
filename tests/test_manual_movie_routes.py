from app.routes import movie_routes


def test_manual_list_only_requests_manual_dashboard_category(monkeypatch):
    calls = {}

    class FakeRepository:
        def list_movies_by_discovery_category(self, category: str, limit: int):
            calls["category"] = category
            calls["limit"] = limit
            return [{"id": 9, "movie_title": "Manual Movie"}]

    monkeypatch.setattr(movie_routes, "MoviePipelineRepository", FakeRepository)

    response = movie_routes.list_manual_movies(limit=25)

    assert calls == {"category": "manual_dashboard", "limit": 25}
    assert response["items"][0]["id"] == 9


def test_add_manual_movie_queues_with_dedicated_category(monkeypatch):
    calls = {"loads": 0}

    class FakeRepository:
        def get_movie_by_tmdb_id(self, tmdb_id: int):
            calls["loads"] += 1
            if calls["loads"] == 1:
                return None
            return {
                "id": 17,
                "tmdb_id": tmdb_id,
                "movie_title": "Fresh Pick",
                "discovery_category": "manual_dashboard",
                "next_agent": "TRAILER_AGENT",
            }

    class FakeTMDBService:
        def get_movie_details_for_selector(self, tmdb_id: int):
            return {"id": tmdb_id, "title": "Fresh Pick"}

    class FakeDiscoveryAgent:
        def queue_selected_movie(self, movie: dict, category: str):
            calls["movie"] = movie
            calls["category"] = category

    monkeypatch.setattr(movie_routes, "MoviePipelineRepository", FakeRepository)
    monkeypatch.setattr(movie_routes, "TMDBService", FakeTMDBService)
    monkeypatch.setattr(movie_routes, "build_movie_discovery_agent", lambda: FakeDiscoveryAgent())

    response = movie_routes.add_manual_movie({"tmdb_id": 501})

    assert calls["category"] == "manual_dashboard"
    assert calls["movie"]["id"] == 501
    assert response["already_exists"] is False
    assert response["pipeline_movie_id"] == 17


def test_manual_search_retries_trailing_year_as_filter(monkeypatch):
    calls = []

    class FakeRepository:
        def get_existing_tmdb_ids_by_discovery_category(self, tmdb_ids: list[int], category: str):
            assert tmdb_ids == [639720]
            assert category == "manual_dashboard"
            return set()

    class FakeTMDBService:
        def browse_movies_general(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return {
                    "page": 1,
                    "total_pages": 1,
                    "total_results": 0,
                    "results": [],
                    "genre_map": {},
                }
            return {
                "page": 1,
                "total_pages": 1,
                "total_results": 1,
                "results": [{"id": 639720, "title": "IF", "release_date": "2024-05-17"}],
                "genre_map": {},
            }

        def build_selector_movie_payload(self, movie: dict, genre_map: dict, selected_ids: set[int]):
            return {"tmdb_id": movie["id"], "title": movie["title"], "is_selected": movie["id"] in selected_ids}

    monkeypatch.setattr(movie_routes, "MoviePipelineRepository", FakeRepository)
    monkeypatch.setattr(movie_routes, "TMDBService", FakeTMDBService)

    response = movie_routes.search_manual_movies(query="IF 2024", page=1, language="en-US")

    assert calls[0]["query"] == "IF 2024"
    assert calls[0]["year"] is None
    assert calls[1]["query"] == "IF"
    assert calls[1]["year"] == 2024
    assert response["movies"][0]["title"] == "IF"
