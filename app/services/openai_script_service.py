import json
import re
from datetime import date

from app.config import settings


SCRIPT_PROMPT = """You are an expert viral YouTube Shorts movie reviewer and script writer.

Your job is to convert movie/series details into a high-retention Hindi Hinglish Shorts script in my exact style.

STRICT STYLE RULES:

1. Start with a story-specific hook:

* The very first line must come from this movie's central conflict, unusual world,
  danger, mystery, or emotional stakes.
* Make the viewer imagine the situation immediately, without revealing the movie
  name in the first line.
* Never start with generic attention commands such as "Ruko ruko bhai", "Are bhai
  ruk", "Ruk ja", or a generic "Soch bhai" that is not tied to the story.
* Do not invent a plot point that is missing from the supplied movie details.

2. Writing style:

* Hinglish only (Hindi + simple English mix)
* Sound like a friend recommending a movie
* Very natural and human-like
* Use short sentences
* Use conversational flow
* Keep transitions smooth
* No robotic writing

3. Tone:

* Fast
* Punchy
* High energy
* Suspenseful
* Emotional when needed
* Funny when possible
* Hype driven

4. Structure:
   (STORY-SPECIFIC HOOK)
   -> Create curiosity
   -> Explain concept fast
   -> Introduce twist
   -> Increase suspense
   -> Add emotional/comedy/action hype
   -> Reveal movie/series name at end
   -> Strong recommendation

5. Important:

* Script must feel like spoken content
* Optimize for ElevenLabs voice generation
* Do not ask viewers to watch the trailer in the description
* Do not include lines like "Watch the trailer in description"
* Add natural pauses (...)
* Read `release_context.release_status` before writing any line of the script.
* If it is `released`, speak about the movie as already available/released and end
  with a natural recommendation like "agar abhi tak nahi dekhi, dekh lo". Never
  describe it as an upcoming or aane wali movie.
* If it is `upcoming`, clearly describe it as "aane wali" or "upcoming", mention
  the supplied release date naturally when useful, and build anticipation. Do not
  pretend that you have already watched it or give a post-release verdict.
* If it is `unknown`, do not guess whether the movie has released.
* Add emotion cues like:
  [Excited]
  [Whisper]
  [Scared]
  [Hyped]
  [Funny]
  [Emotional]
  [Suspense]
  [Dark]
  [Fast]
  [Slow]

6. Retention tricks:

* Use "Aur bhai..."
* Use "Lekin twist..."
* Use "Par asli game..."
* Use "Soch..."
* Use "Aur sabse dangerous baat..."
* Use "Sach bolu..."
* Use "Trust me..."

7. Keep script:

* 35-60 seconds
* High retention
* No unnecessary long explanation
* Focus only on strongest points

8. If movie has:
   Action -> make it aggressive
   Horror -> make it creepy and suspenseful
   Comedy -> make it funny and relatable
   Sci-fi -> make it mysterious and mind-blowing
   Emotional -> make it heart-touching

9. Output format:

Return JSON:

{
"script": "normal shorts script",
"elevenlabs_script": "same script with emotion tags",
"title": "viral title",
"description": "youtube shorts description",
"tags": ["tag1","tag2"],
"keywords": ["keyword1","keyword2"],
"hashtags": ["#tag1","#tag2"],
"thumbnail_text": "best thumbnail hook",
"bgm_style": "Suno AI music prompt"
}

Movie details:
{{MOVIE_DETAILS}}"""


REQUIRED_KEYS = {
    "script",
    "elevenlabs_script",
    "title",
    "description",
    "tags",
    "keywords",
    "hashtags",
    "thumbnail_text",
    "bgm_style",
}


TRAILER_CTA_PATTERN = re.compile(
    r"(?:\[(?:Emotional|Excited|Whisper|Scared|Hyped|Funny|Suspense|Dark|Fast|Slow)\]\s*)*"
    r"watch\s+the\s+trailer\s+in\s+description!?"
    r"(?:\s*\[(?:Emotional|Excited|Whisper|Scared|Hyped|Funny|Suspense|Dark|Fast|Slow)\])*",
    flags=re.IGNORECASE,
)

GENERIC_OPENING_PATTERN = re.compile(
    r"^\s*(?:\[(?:Emotional|Excited|Whisper|Scared|Hyped|Funny|Suspense|Dark|Fast|Slow)\]\s*)*"
    r"(?:ruko(?:\s+ruko)?(?:\s+bhai)?|are\s+bhai\s+ruk|ruk\s+ja|soch\s+bhai)\b",
    flags=re.IGNORECASE,
)

RELEASED_RECOMMENDATION_PATTERN = re.compile(
    r"abhi\s+tak.{0,40}nahi.{0,20}dekh",
    flags=re.IGNORECASE | re.DOTALL,
)

UPCOMING_FRAMING_PATTERN = re.compile(
    r"(?:aane\s+wal[ai]|upcoming|aa\s+rah[ai]|release\s+hog[ai])",
    flags=re.IGNORECASE,
)


class OpenAIScriptService:
    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not configured.")
        try:
            from openai import OpenAI
        except ModuleNotFoundError as exc:
            raise ValueError("openai package is not installed. Run pip install -r requirements.txt.") from exc

        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model

    def generate_script(self, movie_details: dict) -> dict:
        prepared_details = dict(movie_details)
        prepared_details["release_context"] = self._build_release_context(movie_details)
        prompt = SCRIPT_PROMPT.replace(
            "{{MOVIE_DETAILS}}",
            json.dumps(prepared_details, ensure_ascii=False, indent=2),
        )
        content = self._chat_json(prompt)
        try:
            payload = self._parse_and_validate(content)
            self._validate_release_framing(payload, prepared_details["release_context"])
            return payload
        except ValueError as exc:
            correction_prompt = (
                "Return only valid JSON using the exact requested schema. "
                "Do not add markdown, comments, or extra keys. Preserve the correct "
                "released/upcoming framing from the original instructions. The first line "
                "must be a hook based on this movie's actual story and must not start with "
                "Ruko, Are bhai ruk, Ruk ja, or generic Soch bhai. "
                f"Validation error: {exc}\n\nOriginal instructions and movie details:\n{prompt}\n\n"
                "Fix this invalid output:\n"
                f"{content}"
            )
            corrected = self._chat_json(correction_prompt)
            payload = self._parse_and_validate(corrected)
            self._validate_release_framing(payload, prepared_details["release_context"])
            return payload

    @staticmethod
    def _build_release_context(movie_details: dict, today: date | None = None) -> dict:
        """Turn TMDB release metadata into an explicit pre-generation decision."""
        checked_on = today or date.today()
        raw_release_date = str(movie_details.get("release_date") or "").strip()
        parsed_release_date = None
        if raw_release_date:
            try:
                parsed_release_date = date.fromisoformat(raw_release_date[:10])
            except ValueError:
                parsed_release_date = None

        tmdb_status = str(movie_details.get("status") or "").strip()
        normalized_tmdb_status = tmdb_status.casefold()
        if parsed_release_date is not None:
            release_status = "upcoming" if parsed_release_date > checked_on else "released"
            decision_source = "release_date"
        elif normalized_tmdb_status == "released":
            release_status = "released"
            decision_source = "tmdb_status"
        elif normalized_tmdb_status in {"planned", "in production", "post production"}:
            release_status = "upcoming"
            decision_source = "tmdb_status"
        else:
            release_status = "unknown"
            decision_source = "insufficient_metadata"

        return {
            "checked_on": checked_on.isoformat(),
            "release_status": release_status,
            "release_date": raw_release_date or None,
            "tmdb_status": tmdb_status or None,
            "decision_source": decision_source,
        }

    @staticmethod
    def _validate_release_framing(payload: dict, release_context: dict) -> None:
        script = str(payload.get("script") or "")
        release_status = release_context.get("release_status")
        if release_status == "released" and not RELEASED_RECOMMENDATION_PATTERN.search(script):
            raise ValueError(
                "Released movie script must include an 'abhi tak nahi dekhi/dekha, dekh lo' style recommendation."
            )
        if release_status == "upcoming" and not UPCOMING_FRAMING_PATTERN.search(script):
            raise ValueError("Upcoming movie script must clearly say that it is aane wali/upcoming.")

    def _chat_json(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
        )
        return response.choices[0].message.content or ""

    @staticmethod
    def _parse_and_validate(content: str) -> dict:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"OpenAI returned invalid JSON: {exc}") from exc

        missing = REQUIRED_KEYS - set(payload)
        if missing:
            raise ValueError(f"OpenAI JSON missing keys: {sorted(missing)}")

        if not isinstance(payload.get("script"), str) or not payload["script"].strip():
            raise ValueError("OpenAI JSON script is empty.")

        if GENERIC_OPENING_PATTERN.search(payload["script"]):
            raise ValueError("Script starts with a generic wait/attention hook.")

        elevenlabs_script = payload.get("elevenlabs_script")
        if not isinstance(elevenlabs_script, str) or not elevenlabs_script.strip():
            raise ValueError("OpenAI JSON elevenlabs_script is empty.")
        if GENERIC_OPENING_PATTERN.search(elevenlabs_script):
            raise ValueError("ElevenLabs script starts with a generic wait/attention hook.")

        for key in ["tags", "keywords", "hashtags"]:
            if not isinstance(payload.get(key), list):
                raise ValueError(f"OpenAI JSON {key} must be a list.")

        payload["script"] = OpenAIScriptService._remove_trailer_cta(payload["script"])
        if isinstance(payload.get("elevenlabs_script"), str):
            payload["elevenlabs_script"] = OpenAIScriptService._remove_trailer_cta(payload["elevenlabs_script"])

        return payload

    @staticmethod
    def _remove_trailer_cta(text: str) -> str:
        cleaned = TRAILER_CTA_PATTERN.sub("", text or "")
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()
