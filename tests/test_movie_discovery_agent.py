from app.agents.movie_discovery_agent.agent import MovieDiscoveryAgent


class DummyTMDBService:
    def fetch_movies(self, category: str, page: int) -> list[dict]:
        return [
            {
                "id": 101,
                "title": "Test Action Adventure Movie",
                "original_title": "Test Action Adventure Movie",
                "genre_ids": [28, 12],
                "original_language": "en",
                "release_date": "2026-01-01",
                "poster_path": "/poster.jpg",
                "backdrop_path": "/backdrop.jpg",
                "vote_average": 7.2,
                "vote_count": 100,
                "popularity": 25,
            },
            {
                "id": 202,
                "title": "Skip Me",
                "genre_ids": [35],
                "original_language": "en",
                "release_date": "2026-02-01",
            },
        ]


class DummyRepository:
    def __init__(self) -> None:
        self.items = []

    def upsert_movie(self, payload: dict) -> str:
        self.items.append(payload)
        return "inserted"


def test_movie_discovery_agent_filters_and_counts():
    agent = MovieDiscoveryAgent(
        tmdb_service=DummyTMDBService(),
        repository=DummyRepository(),
    )

    result = agent.run(category="released", pages=1)

    assert result["fetched"] == 2
    assert result["inserted"] == 1
    assert result["updated"] == 0
    assert result["skipped"] == 1
    assert result["errors"] == 0


def test_queue_selected_movie_accepts_tmdb_details_genres_shape():
    repository = DummyRepository()
    agent = MovieDiscoveryAgent(
        tmdb_service=DummyTMDBService(),
        repository=repository,
    )

    result = agent.queue_selected_movie(
        movie={
            "id": 303,
            "title": "Manual Pick",
            "original_title": "Manual Pick",
            "genres": [{"id": 28, "name": "Action"}, {"id": 878, "name": "Science Fiction"}],
            "original_language": "en",
            "release_date": "2026-07-04",
            "poster_path": "/manual-poster.jpg",
            "backdrop_path": "/manual-backdrop.jpg",
            "overview": "Selected manually from the dashboard.",
        },
        category="selected",
    )

    assert result["success"] is True
    assert result["tmdb_id"] == 303
    assert result["matched_genres"] == ["Action", "Science Fiction"]
    assert repository.items[0]["discovery_category"] == "selected"

