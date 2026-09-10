from app.routes.movie_routes import _build_frontend_movie_payload, _cloudinary_attachment_url


def test_cloudinary_attachment_url_adds_download_flag():
    url = "https://res.cloudinary.com/demo/video/upload/v123/folder/short.mp4"

    assert _cloudinary_attachment_url(url) == (
        "https://res.cloudinary.com/demo/video/upload/fl_attachment/v123/folder/short.mp4"
    )


def test_frontend_payload_prefers_cloudinary_for_mobile_download():
    cloudinary_url = "https://res.cloudinary.com/demo/video/upload/v123/folder/short.mp4"
    payload = _build_frontend_movie_payload(
        {
            "id": 232,
            "movie_title": "Test movie",
            "voice_status": "COMPLETED",
            "video_download_status": "COMPLETED",
            "scene_status": "COMPLETED",
            "render_status": "COMPLETED",
            "shorts_status": "COMPLETED",
            "thumbnail_status": "COMPLETED",
            "draft_video_path": "storage/final_videos/movie_232/short.mp4",
            "shorts_data_json": {"cloudinary_video_url": cloudinary_url},
        }
    )

    expected = "https://res.cloudinary.com/demo/video/upload/fl_attachment/v123/folder/short.mp4"
    assert payload["assets"]["draft_video_file_url"] == expected
    assert payload["assets"]["cloudinary_video_download_url"] == expected
    assert payload["actions"]["download_final_video_url"] == expected
