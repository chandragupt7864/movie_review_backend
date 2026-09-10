import hashlib
import re
from pathlib import Path

import requests

from app.config import PROJECT_ROOT, settings


class ElevenLabsTTSService:
    provider = "elevenlabs"
    emotion_tag_pattern = re.compile(
        r"\[(Excited|Whisper|Scared|Hyped|Funny|Emotional|Suspense|Dark|Fast|Slow)\]",
        flags=re.IGNORECASE,
    )

    def __init__(self) -> None:
        self.api_key = settings.elevenlabs_api_key
        self.voice_id = settings.elevenlabs_voice_id
        self.voice_name = settings.elevenlabs_voice_name
        self.model_id = settings.elevenlabs_model_id
        self.output_format = settings.elevenlabs_output_format

    def clean_voice_text(self, text: str) -> str:
        cleaned = self.emotion_tag_pattern.sub("", text or "")
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        cleaned = re.sub(r" *\n *", "\n", cleaned)
        return cleaned.strip()

    def get_script_hash(self, text: str, voice_id: str, model_id: str) -> str:
        payload = f"{text}|{self.provider}|{voice_id}|{model_id}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def generate_audio(self, text: str, output_path: str) -> dict:
        if not self.voice_id:
            raise ValueError("ELEVENLABS_VOICE_ID is not configured.")

        cleaned_text = self.clean_voice_text(text)
        script_hash = self.get_script_hash(
            text=cleaned_text,
            voice_id=self.voice_id,
            model_id=self.model_id,
        )
        path = Path(output_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)

        metadata = {
            "provider": self.provider,
            "voice_name": self.voice_name,
            "voice_id": self.voice_id,
            "model_id": self.model_id,
            "output_format": self.output_format,
            "audio_path": output_path,
            "script_hash": script_hash,
            "cached": path.exists(),
            "cleaned_text_length": len(cleaned_text),
        }
        if path.exists():
            return metadata

        if not self.api_key:
            raise ValueError("ELEVENLABS_API_KEY is not configured.")

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
        response = requests.post(
            url,
            headers={
                "xi-api-key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            params={"output_format": self.output_format},
            json={
                "text": cleaned_text,
                "model_id": self.model_id,
                "voice_settings": {
                    "stability": 0.45,
                    "similarity_boost": 0.85,
                    "style": 0.35,
                    "use_speaker_boost": True,
                },
            },
            timeout=120,
        )
        if response.status_code >= 400:
            raise ValueError(f"ElevenLabs TTS failed ({response.status_code}): {response.text[:500]}")

        path.write_bytes(response.content)
        metadata["cached"] = False
        return metadata
