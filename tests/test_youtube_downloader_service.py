from pathlib import Path

import pytest

from app.services.youtube_downloader_service import YoutubeDownloaderService


@pytest.fixture(autouse=True)
def disable_pot_provider(monkeypatch):
    monkeypatch.setattr("app.services.youtube_downloader_service.settings.yt_dlp_pot_provider_enabled", False)


def test_resolve_ffmpeg_location_from_file_path(monkeypatch, tmp_path):
    ffmpeg_dir = tmp_path / "bin"
    ffmpeg_dir.mkdir()
    ffmpeg_file = ffmpeg_dir / "ffmpeg.exe"
    ffmpeg_file.write_text("stub")

    monkeypatch.setattr("app.services.youtube_downloader_service.settings.ffmpeg_binary_path", str(ffmpeg_file))

    resolved = YoutubeDownloaderService._resolve_ffmpeg_location()

    assert resolved == str(ffmpeg_dir)


def test_resolve_ffmpeg_location_from_directory_path(monkeypatch, tmp_path):
    ffmpeg_dir = tmp_path / "bin"
    ffmpeg_dir.mkdir()

    monkeypatch.setattr("app.services.youtube_downloader_service.settings.ffmpeg_binary_path", str(ffmpeg_dir))

    resolved = YoutubeDownloaderService._resolve_ffmpeg_location()

    assert resolved == str(ffmpeg_dir)


def test_build_options_uses_cookie_file_and_node(monkeypatch, tmp_path):
    cookie_file = tmp_path / "youtube_cookies.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n")
    monkeypatch.setattr("app.services.youtube_downloader_service.settings.yt_dlp_cookie_file", str(cookie_file))
    monkeypatch.setattr("app.services.youtube_downloader_service.settings.yt_dlp_cookies_from_browser", "")
    monkeypatch.setattr("app.services.youtube_downloader_service.settings.yt_dlp_player_clients", ["android_vr"])

    service = YoutubeDownloaderService()
    service.node_location = "C:/node/node.exe"
    options = service._build_ydl_options("video.%(ext)s", logger=object())

    assert options["cookiefile"] == str(cookie_file)
    assert options["js_runtimes"] == {"node": {"path": "C:/node/node.exe"}}
    assert options["extractor_args"] == {"youtube": {"player_client": ["android_vr"]}}


def test_transient_youtube_errors_are_detected():
    assert YoutubeDownloaderService.is_transient_error("HTTP Error 403: Forbidden") is True
    assert YoutubeDownloaderService.is_transient_error("HTTP Error 429: Too Many Requests") is True
    assert YoutubeDownloaderService.is_transient_error("Sign in to confirm you're not a bot") is True
    assert YoutubeDownloaderService.is_transient_error("Video is private") is False


def test_mobile_browser_restriction_retries_with_alternate_client():
    assert YoutubeDownloaderService.is_retryable_with_another_client(
        "This content can't be played on your mobile browser. Get the YouTube app."
    ) is True


def test_missing_player_response_retries_with_alternate_client():
    assert YoutubeDownloaderService.is_retryable_with_another_client(
        "Failed to extract any player response"
    ) is True


def test_player_client_attempts_add_android_vr_fallback(monkeypatch):
    monkeypatch.setattr("app.services.youtube_downloader_service.settings.yt_dlp_player_clients", ["mweb"])

    assert YoutubeDownloaderService._player_client_attempts()[:4] == [
        ["mweb"],
        ["visionos"],
        ["visionos"],
        ["android_vr"],
    ]
