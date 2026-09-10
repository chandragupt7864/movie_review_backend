import subprocess

import pytest
from PIL import Image
from pydantic import ValidationError

from app.config import settings
from app.services.shorts_appearance import ShortsAppearance
from app.services.shorts_composer_service import ShortsComposerService


@pytest.mark.parametrize("payload", [{"brightness": 5}, {"gamma": 0}, {"sharpness": -1}, {"theme": "invalid"}, {"contrast": float("nan")}])
def test_appearance_rejects_invalid_values(payload):
    with pytest.raises(ValidationError):
        ShortsAppearance.model_validate(payload)


def test_render_applies_appearance_and_preserves_duration(tmp_path, monkeypatch):
    service = ShortsComposerService()
    for key, value in {"shorts_width": 180, "shorts_height": 320,
                       "shorts_foreground_width_with_crop": 180, "shorts_foreground_width_no_crop": 180,
                       "shorts_video_preset": "ultrafast", "bgm_enabled": False}.items():
        monkeypatch.setattr(settings, key, value)

    def ff(args):
        subprocess.run([service.ffmpeg_binary, "-y", "-loglevel", "error", *args], check=True, capture_output=True)

    master, voice, thumbnail = (tmp_path / name for name in ("master.mp4", "voice.wav", "thumbnail.png"))
    ff(["-f", "lavfi", "-i", "color=c=blue:s=320x180:r=30:d=1", "-c:v", "libx264", str(master)])
    ff(["-f", "lavfi", "-i", "sine=frequency=440:duration=1.5", str(voice)])
    Image.new("RGB", (300, 200), "red").save(thumbnail)
    colors = []
    for theme, look in [("original", {}), ("noir", {"theme": "noir", "saturation": 0, "brightness": 0.1, "sharpness": 0.5})]:
        output = tmp_path / f"{theme}.mp4"
        result = service.compose_shorts_draft(1, str(master), str(voice), str(output), thumbnail_path=str(thumbnail), appearance=look)
        assert abs(result["duration_seconds"] - 3.5) < 0.15
        assert result["appearance"]["theme"] == theme
        base_frame = tmp_path / f"{theme}_base.png"
        ff(["-ss", "3", "-i", str(service._resolve_local_path(result["preview_base_path"])), "-frames:v", "1", str(base_frame)])
        with Image.open(base_frame) as image:
            red, green, blue = image.convert("RGB").getpixel((90, 160))
            assert red > 200 and green < 40 and blue < 40
        frame = tmp_path / f"{theme}.png"
        ff(["-ss", "3", "-i", str(output), "-frames:v", "1", str(frame)])
        with Image.open(frame) as image:
            colors.append(image.convert("RGB").getpixel((90, 160)))
    r, g, b = colors[0]
    assert r > 200 and g < 40 and b < 40
    assert max(colors[1]) - min(colors[1]) < 5
