import base64
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
from pathlib import Path

from app.config import PROJECT_ROOT, settings


class LyriaMusicService:
    def __init__(self) -> None:
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not configured.")
        try:
            from google import genai
        except ModuleNotFoundError as exc:
            raise ValueError("google-genai package is not installed. Run pip install -r requirements.txt.") from exc
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.lyria_model

    def generate_for_movie(self, movie: dict, duration_seconds: float) -> dict:
        duration = max(20.0, min(float(duration_seconds), 180.0))
        prompt = self.build_prompt(movie=movie, duration_seconds=duration)
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                self.client.interactions.create,
                model=self.model,
                input=prompt,
            )
            try:
                interaction = future.result(timeout=max(30, int(settings.lyria_timeout_seconds)))
            except FuturesTimeoutError as exc:
                future.cancel()
                raise TimeoutError(f"Lyria music generation timed out after {settings.lyria_timeout_seconds} seconds.") from exc
            except Exception as exc:
                error_text = str(exc)
                if "429" in error_text and ("quota" in error_text.lower() or "rate" in error_text.lower()):
                    raise ValueError(
                        "Google Lyria quota is unavailable for this API key. Enable paid Gemini API billing/access, then retry."
                    ) from exc
                raise

        output_audio = getattr(interaction, "output_audio", None)
        raw_audio = getattr(output_audio, "data", None) if output_audio else None
        if not raw_audio:
            raise ValueError("Lyria returned no audio data.")
        audio_bytes = base64.b64decode(raw_audio) if isinstance(raw_audio, str) else bytes(raw_audio)
        if len(audio_bytes) < 1024:
            raise ValueError("Lyria returned an invalid or empty audio file.")

        movie_id = int(movie["id"])
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_dir = PROJECT_ROOT / settings.lyria_output_dir / f"movie_{movie_id}"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"movie_{movie_id}_lyria_{timestamp}.mp3"
        output_path.write_bytes(audio_bytes)
        relative_path = str(output_path.relative_to(PROJECT_ROOT)).replace("\\", "/")
        return {
            "provider": "google_lyria",
            "model": self.model,
            "prompt": prompt,
            "requested_duration_seconds": round(duration, 3),
            "bgm_audio_path": relative_path,
            "file_size_bytes": len(audio_bytes),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def build_prompt(movie: dict, duration_seconds: float) -> str:
        script_data = movie.get("script_data_json") or {}
        if not isinstance(script_data, dict):
            script_data = {}
        movie_data = movie.get("movie_data_json") or {}
        if not isinstance(movie_data, dict):
            movie_data = {}
        title = str(movie.get("movie_title") or "movie")
        genres = ", ".join(str(item) for item in (movie.get("target_genres_json") or [])) or "cinematic"
        suggested_style = str(script_data.get("bgm_style") or "cinematic instrumental underscore")
        overview = str(movie_data.get("overview") or "")[:500]
        duration = int(round(duration_seconds))
        hook_end = max(3, round(duration * 0.08))
        setup_end = max(hook_end + 5, round(duration * 0.38))
        tension_end = max(setup_end + 5, round(duration * 0.72))
        timestamp = lambda seconds: f"{seconds // 60}:{seconds % 60:02d}"
        return (
            f"Create an original {duration}-second background score for a YouTube Shorts movie review of {title}.\n"
            f"Movie genres: {genres}.\nStory context: {overview}\nPreferred style: {suggested_style}\n"
            "Instrumental only. No vocals, speech, chants, lyrics, or recognizable copyrighted melodies. "
            "Keep the arrangement spacious under Hindi-Hinglish narration; avoid overpowering lead instruments.\n"
            f"[0:00 - {timestamp(hook_end)}] Immediate story hook with a short attention accent, then leave room for voice.\n"
            f"[{timestamp(hook_end)} - {timestamp(setup_end)}] Establish the movie's main playful/emotional world at medium-low intensity.\n"
            f"[{timestamp(setup_end)} - {timestamp(tension_end)}] Build tension and energy for the twist without becoming loud.\n"
            f"[{timestamp(tension_end)} - {timestamp(duration)}] Warm cinematic payoff, final reveal, and a clean 3-second fade-out.\n"
            "Consistent tempo, clean loop-friendly edit points, stereo MP3, narration-safe background mix."
        )
