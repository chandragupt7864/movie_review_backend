from datetime import date, datetime, timezone

from app.routes.movie_routes import _build_frontend_movie_payload


def test_build_frontend_movie_payload_for_master_video():
    payload = _build_frontend_movie_payload(
        {
            "id": 115,
            "tmdb_id": 999,
            "movie_title": "Supergirl",
            "release_date": date(2026, 6, 28),
            "poster_url": "https://img.test/poster.jpg",
            "backdrop_url": "https://img.test/backdrop.jpg",
            "discovery_category": "released",
            "overall_status": "MASTER_VIDEO_READY",
            "current_agent": None,
            "next_agent": "SHORTS_COMPOSER_AGENT",
            "progress_percent": 80,
            "is_locked": False,
            "last_error_agent": None,
            "last_error_message": None,
            "updated_at": datetime(2026, 6, 28, 12, 0, tzinfo=timezone.utc),
            "trailer_status": "COMPLETED",
            "review_status": "COMPLETED",
            "script_status": "COMPLETED",
            "voice_status": "COMPLETED",
            "video_download_status": "COMPLETED",
            "scene_status": "COMPLETED",
            "render_status": "COMPLETED",
            "shorts_status": "COMPLETED",
            "trailer_url": "https://youtube.com/watch?v=abc",
            "voice_audio_path": "storage/audio/movie_115.mp3",
            "source_video_path": "storage/source_videos/movie_115/trailer.mp4",
            "source_videos_json": [
                {
                    "label": "official_trailer",
                    "type": "trailer",
                    "source_video_path": "storage/source_videos/movie_115/trailer.mp4",
                    "aspect_ratio": "16:9",
                    "duration_seconds": 120.4,
                }
            ],
            "master_video_path": "storage/final_videos/movie_115/movie_115_master.mp4",
            "final_video_path": None,
            "scene_data_json": {
                "target_duration_seconds": 52,
                "estimated_total_duration_seconds": 51.3,
                "video_format_for_next_agent": "16:9",
                "master_resolution": "1920x1080",
                "scenes": [{"order": 1}, {"order": 2}],
            },
            "render_data_json": {
                "clip_count": 2,
                "estimated_duration_seconds": 51.1,
                "transitions_used": ["flash_cut"],
                "warnings": [],
            },
            "shorts_data_json": {
                "duration_seconds": 52.3,
                "layout": {
                    "background": "blurred cropped video full screen",
                    "foreground": "cropped, zoomed, centered video",
                    "foreground_width": 1220,
                    "foreground_x_alignment": "center",
                    "foreground_y_alignment": "center",
                    "foreground_y_offset": 0,
                },
                "preprocessing": {
                    "black_bar_detection_enabled": True,
                    "has_black_bars": True,
                    "crop_applied": True,
                    "crop_method": "cropdetect",
                    "crop_area": {"crop_w": 1920, "crop_h": 800, "crop_x": 0, "crop_y": 140},
                    "foreground_zoom_base": 1.50,
                    "foreground_zoom_applied": 1.70,
                    "foreground_light_adjustment": {"brightness": 0.06, "contrast": 1.08, "saturation": 1.08},
                    "background_light_adjustment": {"brightness": -0.08, "contrast": 1.0, "saturation": 1.0},
                },
                "audio_mix": {"bgm_enabled": True},
                "warnings": [],
            },
            "draft_video_path": "storage/final_videos/movie_115/movie_115_draft_shorts.mp4",
            "process_timeline_json": [{"agent": "CUT_MERGE_AGENT", "status": "COMPLETED"}],
        }
    )

    assert payload["success"] is True
    assert payload["movie"]["id"] == 115
    assert payload["assets"]["master_video_file_url"] == "/movies/115/master-video-file"
    assert payload["assets"]["draft_video_file_url"] == "/movies/115/draft-video-file"
    assert payload["render"]["ready"] is True
    assert payload["shorts"]["ready"] is True
    assert payload["shorts"]["preprocessing"]["crop_applied"] is True
    assert payload["shorts"]["preprocessing"]["foreground_zoom_applied"] == 1.70
    assert payload["actions"]["can_run_cut_merge"] is True
    assert payload["actions"]["can_run_shorts_composer"] is True
    assert payload["messages"]["render"] == "16:9 master video is ready."
    assert payload["messages"]["shorts"] == "9:16 draft Shorts video is ready."
