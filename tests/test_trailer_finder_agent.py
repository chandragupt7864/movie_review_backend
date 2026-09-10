from app.agents.trailer_finder_agent.agent import TrailerFinderAgent


def test_trailer_finder_prefers_official_youtube_trailer():
    agent = TrailerFinderAgent(tmdb_service=None, repository=None)

    selected = agent._select_best_video(
        [
            {"site": "YouTube", "type": "Teaser", "official": True, "key": "teaser", "name": "Official Teaser"},
            {"site": "YouTube", "type": "Trailer", "official": True, "key": "trailer", "name": "Official Trailer"},
        ],
    )

    assert selected["key"] == "trailer"


def test_trailer_finder_falls_back_to_youtube_teaser():
    agent = TrailerFinderAgent(tmdb_service=None, repository=None)

    selected = agent._select_best_video(
        [
            {"site": "Vimeo", "type": "Trailer", "official": True, "key": "vimeo", "name": "Trailer"},
            {"site": "YouTube", "type": "Teaser", "official": False, "key": "teaser", "name": "Teaser"},
        ],
    )

    assert selected["key"] == "teaser"


def test_trailer_finder_selects_multiple_unique_candidates_in_priority_order():
    agent = TrailerFinderAgent(tmdb_service=None, repository=None)

    selected = agent._select_best_videos(
        [
            {"site": "YouTube", "type": "Teaser", "official": True, "key": "teaser-1", "name": "Official Teaser"},
            {"site": "YouTube", "type": "Trailer", "official": True, "key": "trailer-1", "name": "Official Trailer"},
            {"site": "YouTube", "type": "Trailer", "official": False, "key": "trailer-2", "name": "Trailer 2"},
            {"site": "YouTube", "type": "Teaser", "official": False, "key": "teaser-2", "name": "Teaser 2"},
        ],
    )

    assert [item["key"] for item in selected] == ["trailer-1", "teaser-1", "trailer-2", "teaser-2"]


def test_trailer_finder_filters_out_non_trailer_teaser_videos():
    agent = TrailerFinderAgent(tmdb_service=None, repository=None)

    supported = agent._filter_supported_videos(
        [
            {"site": "YouTube", "type": "Clip", "official": True, "key": "clip-1"},
            {"site": "YouTube", "type": "Featurette", "official": True, "key": "featurette-1"},
            {"site": "Vimeo", "type": "Trailer", "official": True, "key": "vimeo-1"},
            {"site": "YouTube", "type": "Trailer", "official": True, "key": "trailer-1"},
            {"site": "YouTube", "type": "Teaser", "official": False, "key": "teaser-1"},
        ],
    )

    assert [item["key"] for item in supported] == ["trailer-1", "teaser-1"]


def test_trailer_finder_excludes_promos_shorts_and_accessibility_versions():
    agent = TrailerFinderAgent(tmdb_service=None, repository=None)

    selected = agent._select_best_videos(
        [
            {"site": "YouTube", "type": "Trailer", "official": True, "key": "real", "name": "Official Trailer"},
            {"site": "YouTube", "type": "Trailer", "official": True, "key": "asl", "name": "Official American Sign Language Trailer"},
            {"site": "YouTube", "type": "Teaser", "official": True, "key": "bts", "name": "Soar BTS 16x9 Own Now"},
            {"site": "YouTube", "type": "Teaser", "official": True, "key": "short", "name": "Look Up"},
            {"site": "YouTube", "type": "Trailer", "official": True, "key": "spot", "name": "Official Trailer TV Spot"},
            {"site": "YouTube", "type": "Teaser", "official": True, "key": "soon", "name": "Teaser Trailer Tomorrow"},
            {"site": "YouTube", "type": "Teaser", "official": True, "key": "animation", "name": "Animation Teaser Dark Knight"},
            {"site": "YouTube", "type": "Trailer", "official": True, "key": "shorts", "name": "Official Trailer #shorts"},
        ]
    )

    assert [item["key"] for item in selected] == ["real"]
