from app.services.lyria_music_service import LyriaMusicService


def test_build_prompt_uses_movie_script_mood_and_timeline() -> None:
    movie = {
        "id": 230,
        "movie_title": "Lilo & Stitch",
        "target_genres_json": ["Family", "Adventure"],
        "movie_data_json": {"overview": "An unusual friendship becomes a chaotic family adventure."},
        "script_data_json": {"bgm_style": "Playful Hawaiian sci-fi wonder."},
    }

    prompt = LyriaMusicService.build_prompt(movie, 75)

    assert "Lilo & Stitch" in prompt
    assert "Playful Hawaiian sci-fi wonder" in prompt
    assert "Instrumental only" in prompt
    assert "1:15" in prompt
    assert "Hindi-Hinglish narration" in prompt
