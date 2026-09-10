import json
import shutil
import subprocess
from pathlib import Path

from app.config import settings


class MusicFingerprintService:
    def generate(self, file_path: str | Path) -> dict:
        binary = settings.fpcalc_binary or "fpcalc"
        if not shutil.which(binary):
            return {
                "enabled": False,
                "provider": "chromaprint",
                "status": "UNAVAILABLE",
                "fingerprint": None,
                "duration": None,
                "warning": "fpcalc unavailable",
            }

        command = [binary, "-json", str(Path(file_path))]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=120)
        except subprocess.CalledProcessError as exc:
            return {
                "enabled": True,
                "provider": "chromaprint",
                "status": "FAILED",
                "fingerprint": None,
                "duration": None,
                "warning": f"fpcalc failed: {exc}",
            }

        payload = json.loads(result.stdout or "{}")
        return {
            "enabled": True,
            "provider": "chromaprint",
            "status": "COMPLETED",
            "fingerprint": payload.get("fingerprint"),
            "duration": payload.get("duration"),
            "warning": None,
        }
