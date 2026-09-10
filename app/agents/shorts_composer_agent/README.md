# Shorts Composer Agent

`SHORTS_COMPOSER_AGENT` converts the clean 16:9 `master_video_path` into a draft 9:16 YouTube Shorts video with a blurred full-screen background, a sharp centered foreground, voice audio from `voice_audio_path`, and optional low-volume BGM.

Workflow:

1. Run Cut Merge:
   `POST /agents/cut-merge/run/{id}?force=true`
2. Run Shorts Composer:
   `POST /agents/shorts-composer/run/{id}?force=true`
3. Check:
   `GET /movies/{id}`

Expected after success:

- `shorts_status = COMPLETED`
- `draft_video_path` is not null
- `final_video_path` is set to draft path when `SHORTS_SET_FINAL_VIDEO_PATH=true`
- `shorts_data_json` contains layout, audio mix, duration, and warnings
- `overall_status = DRAFT_VIDEO_READY`
- `next_agent = THUMBNAIL_METADATA_AGENT`
