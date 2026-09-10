from fastapi import HTTPException

from app.routes import movie_routes


def test_delete_movie_removes_row_after_cleanup(monkeypatch):
    calls = {"cleanup_movie_id": None, "delete_movie_id": None}

    class FakeRepository:
        def get_movie_by_id(self, movie_id: int):
            assert movie_id == 115
            return {"id": 115, "movie_title": "Supergirl"}

        def delete_movie(self, movie_id: int):
            calls["delete_movie_id"] = movie_id
            return True

    def fake_cleanup(movie: dict):
        calls["cleanup_movie_id"] = movie["id"]
        return []

    monkeypatch.setattr(movie_routes, "MoviePipelineRepository", FakeRepository)
    monkeypatch.setattr(movie_routes, "_delete_movie_assets", fake_cleanup)

    response = movie_routes.delete_movie(115)

    assert calls["cleanup_movie_id"] == 115
    assert calls["delete_movie_id"] == 115
    assert response == {
        "success": True,
        "movie_id": 115,
        "movie_title": "Supergirl",
        "cleanup_warnings": [],
    }


def test_delete_movie_returns_404_when_missing(monkeypatch):
    class FakeRepository:
        def get_movie_by_id(self, movie_id: int):
            assert movie_id == 404
            return None

    monkeypatch.setattr(movie_routes, "MoviePipelineRepository", FakeRepository)

    try:
        movie_routes.delete_movie(404)
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail == "Movie not found."
    else:
        raise AssertionError("Expected HTTPException for missing movie")
