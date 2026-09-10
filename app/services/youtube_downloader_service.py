import os
import shutil
import socket
import subprocess
import time
from glob import glob
from pathlib import Path
from app.config import PROJECT_ROOT, settings


class _YtDlpLogCollector:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def debug(self, message: str) -> None:
        return None

    def warning(self, message: str) -> None:
        return None

    def error(self, message: str) -> None:
        text = str(message).strip()
        if text:
            self.errors.append(text)


class YoutubeDownloaderService:
    def __init__(self) -> None:
        try:
            import yt_dlp
        except ModuleNotFoundError as exc:
            raise ValueError("yt-dlp package is not installed. Run pip install -r requirements.txt.") from exc
        self._yt_dlp = yt_dlp
        self.format_opt = settings.yt_dlp_format
        self.ffmpeg_location = self._resolve_ffmpeg_location()
        self.node_location = shutil.which("node")
        self._ensure_pot_provider()

    def download_video(self, youtube_url: str, output_path: str) -> str:
        """
        Downloads a YouTube video to the output_path.
        Returns the path of the downloaded file relative to PROJECT_ROOT.
        """
        out_path = Path(output_path)
        if not out_path.is_absolute():
            out_path = PROJECT_ROOT / out_path

        out_path.parent.mkdir(parents=True, exist_ok=True)

        outtmpl = str(out_path.parent / f"{out_path.stem}.%(ext)s")

        client_attempts = self._player_client_attempts()
        attempts = max(1, int(settings.yt_dlp_retry_attempts), len(client_attempts))
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            logger = _YtDlpLogCollector()
            player_clients = client_attempts[min(attempt - 1, len(client_attempts) - 1)]
            ydl_opts = self._build_ydl_options(
                outtmpl=outtmpl,
                logger=logger,
                player_clients=player_clients,
            )
            try:
                with self._yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([youtube_url])
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                collected_error = self._pick_relevant_error(logger.errors)
                error_text = collected_error or str(exc)
                if attempt >= attempts or not self.is_retryable_with_another_client(error_text):
                    raise ValueError(error_text) from exc
                if not self.is_transient_error(error_text):
                    self._remove_partial_outputs(out_path)
                time.sleep(min(2.0, float(attempt)))

        if last_error is not None:
            raise last_error

        # Prefer the exact requested MP4 and never mistake partial/backup files
        # for a completed media download.
        media_extensions = {".mp4", ".mkv", ".webm", ".mov"}
        candidates = [out_path] if out_path.is_file() else []
        candidates.extend(
            p
            for p in out_path.parent.iterdir()
            if p.stem == out_path.stem and p.suffix.lower() in media_extensions and p not in candidates
        )
        for p in candidates:
            if p.is_file():
                try:
                    return str(p.relative_to(PROJECT_ROOT)).replace("\\", "/")
                except ValueError:
                    return str(p).replace("\\", "/")

        collected_error = self._pick_relevant_error(logger.errors)
        if collected_error:
            raise FileNotFoundError(collected_error)
        raise FileNotFoundError(f"Could not locate downloaded video for {youtube_url} with base name {out_path.name}")

    def _build_ydl_options(
        self,
        outtmpl: str,
        logger: _YtDlpLogCollector,
        player_clients: list[str] | None = None,
    ) -> dict:
        options = {
            "format": self.format_opt,
            "outtmpl": outtmpl,
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
            "logger": logger,
            "retries": 10,
            "fragment_retries": 10,
            "extractor_retries": 3,
            "socket_timeout": int(settings.yt_dlp_socket_timeout_seconds),
        }
        if self.ffmpeg_location:
            options["ffmpeg_location"] = self.ffmpeg_location
        if self.node_location:
            options["js_runtimes"] = {"node": {"path": self.node_location}}
        selected_clients = list(player_clients if player_clients is not None else settings.yt_dlp_player_clients)
        if selected_clients:
            options["extractor_args"] = {
                "youtube": {"player_client": selected_clients},
            }
        cookie_file = self._resolve_cookie_file()
        if cookie_file:
            options["cookiefile"] = cookie_file
        elif settings.yt_dlp_cookies_from_browser:
            options["cookiesfrombrowser"] = (settings.yt_dlp_cookies_from_browser,)
        return options

    def _ensure_pot_provider(self) -> None:
        if not settings.yt_dlp_pot_provider_enabled or self._is_port_open(settings.yt_dlp_pot_provider_port):
            return
        if not self.node_location:
            return

        server_dir = Path(settings.yt_dlp_pot_provider_server_dir)
        if not server_dir.is_absolute():
            server_dir = PROJECT_ROOT / server_dir
        entrypoint = server_dir / "build" / "main.js"
        if not entrypoint.is_file():
            return

        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        subprocess.Popen(
            [self.node_location, str(entrypoint), "--port", str(settings.yt_dlp_pot_provider_port)],
            cwd=str(server_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
        for _ in range(60):
            if self._is_port_open(settings.yt_dlp_pot_provider_port):
                return
            time.sleep(0.5)
        # The provider is optional because token-free clients (for example
        # visionOS) can still download videos when the helper cannot start.
        return

    @staticmethod
    def _is_port_open(port: int) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", int(port)), timeout=0.25):
                return True
        except OSError:
            return False

    @staticmethod
    def _resolve_cookie_file() -> str | None:
        configured = str(settings.yt_dlp_cookie_file or "").strip()
        if not configured:
            return None
        path = Path(configured)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return str(path) if path.is_file() else None

    @staticmethod
    def _remove_partial_outputs(out_path: Path) -> None:
        for candidate in out_path.parent.glob(f"{out_path.stem}.*"):
            name = candidate.name.lower()
            is_partial = name.endswith(".part") or name.endswith(".ytdl") or ".part-frag" in name
            if candidate.is_file() and is_partial:
                candidate.unlink(missing_ok=True)

    @staticmethod
    def is_transient_error(error: object) -> bool:
        text = str(error).lower()
        return any(
            marker in text
            for marker in (
                "http error 403",
                "http error 429",
                "timed out",
                "timeout",
                "connection reset",
                "connection aborted",
                "temporary failure",
                "remote end closed",
                "sign in to confirm you're not a bot",
                "sign in to confirm you’re not a bot",
            )
        )

    @classmethod
    def is_retryable_with_another_client(cls, error: object) -> bool:
        text = str(error).lower()
        return cls.is_transient_error(error) or any(
            marker in text
            for marker in (
                "failed to extract any player response",
                "no player response",
                "can't be played on your mobile browser",
                "cannot be played on your mobile browser",
                "requested format is not available",
                "the page needs to be reloaded",
            )
        )

    @staticmethod
    def _player_client_attempts() -> list[list[str]]:
        configured = [str(client).strip() for client in settings.yt_dlp_player_clients if str(client).strip()]
        candidates = [configured, ["visionos"], ["visionos"], ["android_vr"], ["web"], ["ios"]]
        attempts: list[list[str]] = []
        for clients in candidates:
            if clients:
                attempts.append(clients)
        return attempts or [["android_vr"]]

    @staticmethod
    def _resolve_ffmpeg_location() -> str | None:
        if settings.ffmpeg_binary_path:
            configured = Path(settings.ffmpeg_binary_path)
            if configured.is_file():
                return str(configured.parent)
            if configured.is_dir():
                return str(configured)

        winget_pattern = (
            Path.home()
            / "AppData"
            / "Local"
            / "Microsoft"
            / "WinGet"
            / "Packages"
            / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
            / "*"
            / "bin"
            / "ffmpeg.exe"
        )
        matches = glob(str(winget_pattern))
        if matches:
            return str(Path(matches[0]).parent)
        return None

    @staticmethod
    def _pick_relevant_error(errors: list[str]) -> str | None:
        if not errors:
            return None
        for message in reversed(errors):
            normalized = message.strip()
            if normalized.lower().startswith("error:"):
                normalized = normalized[6:].strip()
            if normalized:
                return normalized
        return None
