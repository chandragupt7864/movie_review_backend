from pathlib import Path

from app.services.shorts_composer_service import ShortsComposerService


def test_build_video_filter_uses_crop_and_centered_zoom():
    service = ShortsComposerService(storage_service=None)

    filter_graph = service.build_video_filter(
        crop_info={
            "has_black_bars": True,
            "crop_applied": True,
            "crop_method": "cropdetect",
            "crop_w": 1920,
            "crop_h": 800,
            "crop_x": 0,
            "crop_y": 140,
        },
        shorts_width=1080,
        shorts_height=1920,
        foreground_width=1220,
        foreground_zoom=1.70,
        background_blur=24,
        background_darkness=-0.08,
        foreground_y_offset=0,
        stop_pad_duration=0.0,
    )

    assert "crop=1920:800:0:140" in filter_graph
    assert "[bg][fg]overlay=(W-w)/2:" in filter_graph
    assert "brightness=0.06:contrast=1.08:saturation=1.08" in filter_graph
    assert "brightness=-0.08:contrast=1.0:saturation=1.0" in filter_graph
    assert "scale=2074:-2[fg]" in filter_graph


def test_detect_crop_area_falls_back_when_cropdetect_is_unavailable(tmp_path, monkeypatch):
    service = ShortsComposerService(storage_service=None)
    master_path = tmp_path / "master.mp4"
    master_path.write_bytes(b"fake")

    monkeypatch.setattr(service, "_probe_video_stream", lambda path: {"width": 1920, "height": 1080})
    monkeypatch.setattr(service, "_probe_duration_seconds", lambda path: 10.0)

    class Result:
        returncode = 1
        stderr = "cropdetect unavailable"
        stdout = ""

    monkeypatch.setattr("app.services.shorts_composer_service.subprocess.run", lambda *args, **kwargs: Result())

    crop_info = service.detect_crop_area(str(master_path))

    assert crop_info["detected"] is True
    assert crop_info["has_black_bars"] is True
    assert crop_info["crop_applied"] is True
    assert crop_info["crop_method"] == "fallback"
    assert "warning" in crop_info
