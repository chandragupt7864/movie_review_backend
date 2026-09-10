from datetime import date

import pytest

from app.agents.review_reaction_agent.agent import ReviewReactionAgent
from app.services.openai_script_service import OpenAIScriptService
from app.services.gemini_script_service import GeminiScriptService


def test_review_reaction_agent_summarizes_reviews_without_long_content():
    reviews = {
        "results": [
            {
                "author": "critic",
                "author_details": {"rating": 8},
                "created_at": "2026-01-01T00:00:00Z",
                "content": "x" * 500,
                "url": "https://example.com/review",
            }
        ]
    }

    summaries = ReviewReactionAgent._summarize_reviews(reviews)

    assert summaries[0]["author"] == "critic"
    assert summaries[0]["rating"] == 8
    assert len(summaries[0]["summary"]) == 300
    assert summaries[0]["url"] == "https://example.com/review"


def test_openai_script_service_validates_required_json_shape():
    payload = OpenAIScriptService._parse_and_validate(
        """
        {
          "script": "Ek khilona agar tumhare bina zinda ho jaye to?",
          "elevenlabs_script": "[Suspense] Ek khilona agar tumhare bina zinda ho jaye to?",
          "title": "Viral Movie",
          "description": "Shorts description",
          "tags": ["movie"],
          "keywords": ["movie"],
          "hashtags": ["#movie"],
          "thumbnail_text": "Must Watch",
          "bgm_style": "dark cinematic beat"
        }
        """
    )

    assert payload["script"].startswith("Ek khilona")


def test_openai_script_service_removes_trailer_description_cta():
    payload = OpenAIScriptService._parse_and_validate(
        """
        {
          "script": "Ek shehar jahan koi safe nahi... Watch the trailer in description! Movie ka naam X hai.",
          "elevenlabs_script": "[Excited] Ek shehar jahan koi safe nahi... [Emotional] Watch the trailer in description! [Excited] Movie ka naam X hai.",
          "title": "Viral Movie",
          "description": "Shorts description",
          "tags": ["movie"],
          "keywords": ["movie"],
          "hashtags": ["#movie"],
          "thumbnail_text": "Must Watch",
          "bgm_style": "dark cinematic beat"
        }
        """
    )

    assert "Watch the trailer in description" not in payload["script"]
    assert "Watch the trailer in description" not in payload["elevenlabs_script"]
    assert "Movie ka naam X hai." in payload["elevenlabs_script"]


@pytest.mark.parametrize(
    ("movie_details", "expected_status", "expected_source"),
    [
        ({"release_date": "2026-08-01", "status": "Released"}, "released", "release_date"),
        ({"release_date": "2026-10-01", "status": "Planned"}, "upcoming", "release_date"),
        ({"release_date": "", "status": "Released"}, "released", "tmdb_status"),
        ({"release_date": None, "status": "Post Production"}, "upcoming", "tmdb_status"),
    ],
)
def test_openai_script_service_checks_release_state_before_generation(
    movie_details, expected_status, expected_source
):
    context = OpenAIScriptService._build_release_context(movie_details, today=date(2026, 9, 7))

    assert context["release_status"] == expected_status
    assert context["decision_source"] == expected_source
    assert context["checked_on"] == "2026-09-07"


def test_openai_script_service_rejects_generic_wait_hook():
    with pytest.raises(ValueError, match="generic wait/attention hook"):
        OpenAIScriptService._parse_and_validate(
            """
            {
              "script": "Ruko ruko bhai... yeh kahani alag hai.",
              "elevenlabs_script": "[Excited] Ruko ruko bhai... yeh kahani alag hai.",
              "title": "Viral Movie",
              "description": "Shorts description",
              "tags": ["movie"],
              "keywords": ["movie"],
              "hashtags": ["#movie"],
              "thumbnail_text": "Must Watch",
              "bgm_style": "dark cinematic beat"
            }
            """
        )


def test_openai_script_service_requires_released_recommendation():
    payload = {"script": "Ek anjaan darwaza poori duniya badal deta hai."}

    with pytest.raises(ValueError, match="Released movie script"):
        OpenAIScriptService._validate_release_framing(payload, {"release_status": "released"})

    payload["script"] += " Agar abhi tak nahi dekhi, dekh lo."
    OpenAIScriptService._validate_release_framing(payload, {"release_status": "released"})


def test_openai_script_service_requires_upcoming_framing():
    payload = {"script": "Ek anjaan darwaza poori duniya badal deta hai."}

    with pytest.raises(ValueError, match="Upcoming movie script"):
        OpenAIScriptService._validate_release_framing(payload, {"release_status": "upcoming"})

    payload["script"] += " Yeh aane wali movie kaafi dangerous lag rahi hai."
    OpenAIScriptService._validate_release_framing(payload, {"release_status": "upcoming"})


def test_gemini_script_service_reuses_release_and_hook_validation():
    assert GeminiScriptService._build_release_context(
        {"release_date": "2026-10-01"}, today=date(2026, 9, 7)
    )["release_status"] == "upcoming"
    assert GeminiScriptService._validate_release_framing(
        {"script": "Yeh aane wali movie ek alien ki kahani hai."},
        {"release_status": "upcoming"},
    ) is None
