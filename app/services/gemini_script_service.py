from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from app.config import settings
from app.services.openai_script_service import OpenAIScriptService


class GeminiScriptService(OpenAIScriptService):
    """Generate review scripts with Gemini while reusing shared prompt and validation."""

    def __init__(self) -> None:
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not configured.")
        try:
            from google import genai
        except ModuleNotFoundError as exc:
            raise ValueError("google-genai package is not installed. Run pip install -r requirements.txt.") from exc

        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model = settings.gemini_model

    def _chat_json(self, prompt: str) -> str:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                self.client.models.generate_content,
                model=self.model,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "temperature": 0.8,
                },
            )
            try:
                response = future.result(timeout=max(30, int(settings.gemini_generate_timeout_seconds)))
            except FuturesTimeoutError as exc:
                future.cancel()
                raise TimeoutError(
                    f"Gemini script generation timed out after "
                    f"{int(settings.gemini_generate_timeout_seconds)} seconds."
                ) from exc

        content = getattr(response, "text", None)
        if not content:
            raise ValueError("Gemini returned an empty script response.")
        return str(content)
