# Movie Review Agent System

This project is the backend foundation for a multi-agent movie review pipeline. It currently implements movie discovery, trailer finding, review/script writing, voice generation, scene selection, source-video handling, cut-merge rendering for a clean 16:9 master video, and draft 9:16 Shorts composition.

## Current scope

- FastAPI backend
- TMDB movie discovery
- Hollywood-only filtering
- English-language filtering
- Supported genres: Action, Adventure, Horror, Science Fiction
- Supported categories: `released`, `upcoming`, `trending`
- PostgreSQL or Supabase persistence with `psycopg2`
- ElevenLabs MP3 voice generation from completed scripts
- FFmpeg-based 16:9 master video rendering from selected scenes
- FFmpeg-based 9:16 Shorts draft composition with blurred background and mixed audio

## Project structure

Each agent lives in its own folder inside `app/agents/`. `movie_discovery_agent` discovers movies from TMDB. `trailer_finder_agent` finds TMDB YouTube trailer or teaser metadata and saves it back to the same pipeline row. `review_reaction_agent` collects TMDB/Wikipedia research and generates a Hindi Hinglish Shorts script with OpenAI. `voice_generator_agent` turns the approved script into cached ElevenLabs MP3 audio.

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and fill in:

- `TMDB_BEARER_TOKEN`
- `DATABASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `ELEVENLABS_API_KEY`
- `ELEVENLABS_VOICE_ID`
- `ELEVENLABS_VOICE_NAME=Alex`
- `ELEVENLABS_MODEL_ID=eleven_v3`
- `ELEVENLABS_OUTPUT_FORMAT=mp3_44100_128`
- `AUDIO_OUTPUT_DIR=storage/audio`
- `VOICE_REQUIRE_APPROVAL=true`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_AUDIO_BUCKET=movie-audio`
- `UPLOAD_AUDIO_TO_SUPABASE=true`
- `SUPABASE_AUDIO_KEEP_LAST=20`
- `AUDIO_CLEANUP_ENABLED=true`
- `DELETE_LOCAL_AUDIO_AFTER_UPLOAD=false`
- `GEMINI_API_KEY`
- `GEMINI_MODEL=gemini-2.5-flash`
- `SCRIPT_PROVIDER=gemini` uses Gemini for review-script generation; set it to `openai` to use OpenAI.
- `VIDEO_SOURCE_DIR=storage/source_videos`
- `VIDEO_RENDER_DIR=storage/final_videos`
- `TEMP_CLIP_DIR=storage/temp_clips`
- `MASTER_VIDEO_RESOLUTION=1920x1080`
- `MASTER_VIDEO_FPS=30`
- `MASTER_VIDEO_CRF=20`
- `MASTER_VIDEO_PRESET=veryfast`
- `RENDER_KEEP_TEMP_CLIPS=false`
- `FFMPEG_BINARY=ffmpeg`
- `FFPROBE_BINARY=ffprobe`
- `SHORTS_OUTPUT_DIR=storage/final_videos`
- `SHORTS_TEMP_DIR=storage/temp_shorts`
- `SHORTS_WIDTH=1080`
- `SHORTS_HEIGHT=1920`
- `SHORTS_FPS=30`
- `SHORTS_FOREGROUND_ZOOM=1.50`
- `SHORTS_FOREGROUND_WIDTH=1020`
- `SHORTS_FOREGROUND_Y_OFFSET=0`
- `SHORTS_FOREGROUND_X_CENTER=true`
- `SHORTS_FOREGROUND_Y_CENTER=true`
- `SHORTS_BACKGROUND_BLUR=24`
- `SHORTS_BACKGROUND_DARKNESS=-0.08`
- `SHORTS_FOREGROUND_BRIGHTNESS=0.06`
- `SHORTS_FOREGROUND_CONTRAST=1.08`
- `SHORTS_FOREGROUND_SATURATION=1.08`
- `SHORTS_BACKGROUND_CONTRAST=1.00`
- `SHORTS_BACKGROUND_SATURATION=1.00`
- `SHORTS_VIDEO_CRF=20`
- `SHORTS_VIDEO_PRESET=veryfast`
- `BGM_ENABLED=true`
- `BGM_DEFAULT_PATH=storage/bgm/default_bgm.mp3`
- `BGM_VOLUME=0.10`
- `VOICE_VOLUME=1.0`
- `BGM_FADE_OUT_SECONDS=3`
- `SHORTS_SET_FINAL_VIDEO_PATH=true`
- `SCENE_EXTRA_SECONDS_AFTER_VOICE=7`
- `SCENE_EXTRA_SECONDS_MIN=5`
- `SCENE_EXTRA_SECONDS_MAX=10`
- `SCENE_OUTPUT_FORMAT=16:9`
- `SCENE_MASTER_RESOLUTION=1920x1080`
- `SOURCE_VIDEO_MAX_SIZE_MB=500`
- `SOURCE_VIDEO_MIN_ASPECT_RATIO=1.70`
- `SOURCE_VIDEO_MAX_ASPECT_RATIO=1.85`
- `GEMINI_SSL_VERIFY=true`
- Optional SSL settings for networks that intercept HTTPS:
  - `TMDB_SSL_VERIFY=true`
  - `TMDB_CA_BUNDLE=`
  - `TMDB_USE_ENV_PROXY=true`
  - `TMDB_RETRY_COUNT=3`
  - `TMDB_TIMEOUT_SECONDS=30`
  - `INTERNET_SSL_VERIFY=true`

4. Run the SQL in [sql/create_tables.sql](/G:/Chandra_Reserch/Automation_projects/Video_automate/movie-review-agent-system/sql/create_tables.sql) against your Supabase PostgreSQL database.

FFmpeg and FFprobe must be installed and available in your system `PATH`, or configured explicitly through `FFMPEG_BINARY` and `FFPROBE_BINARY`. The Shorts Composer agent uses Python `subprocess` with FFmpeg/FFprobe directly and does not require MoviePy for rendering.

## Run the API

```bash
uvicorn app.main:app --reload
```

You should run that command from the `movie-review-agent-system/` directory.

## API endpoints

- `GET /`
- `POST /agents/movie-discovery/run?category=released&pages=1`
- `POST /agents/movie-discovery/run?category=upcoming&pages=1`
- `POST /agents/movie-discovery/run?category=trending&pages=1`
- `POST /agents/trailer-finder/run?limit=5`
- `POST /agents/trailer-finder/run/1`
- `POST /agents/review-script/run?limit=3`
- `POST /agents/review-script/run/1`
- `POST /agents/voice-generator/run?limit=1`
- `POST /agents/voice-generator/run/1`
- `POST /agents/voice-generator/run/1?force=true`
- `POST /agents/scene-selection/run?limit=1`
- `POST /agents/scene-selection/run/1?force=true`
- `POST /agents/audio-cleanup/run?keep_last=20&safe_only=true`
- `POST /agents/cut-merge/run?limit=1`
- `POST /agents/cut-merge/run/1?force=true`
- `POST /agents/shorts-composer/run?limit=1`
- `POST /agents/shorts-composer/run/1?force=true`
- `GET /movies?limit=20`
- `GET /movies/{id}`
- `GET /movies/{id}/master-video-file`
- `GET /movies/{id}/draft-video-file`
- `POST /movies/{id}/approve-processing`
- `POST /movies/{id}/source-video-upload`
- `GET /movies/{id}/voice-text`
- `POST /movies/{id}/voice-upload`
- `GET /movies/{id}/voice-signed-url`

## Trailer Finder Agent

Run discovery first so movies are queued with `next_agent = TRAILER_FINDER_AGENT`:

```bash
curl -X POST "http://127.0.0.1:8000/agents/movie-discovery/run?category=released&pages=1"
```

Then run the trailer finder:

```bash
curl -X POST "http://127.0.0.1:8000/agents/trailer-finder/run?limit=5"
```

Manual single-movie test:

```bash
curl -X POST "http://127.0.0.1:8000/agents/trailer-finder/run/1"
```

Check the movie:

```bash
curl "http://127.0.0.1:8000/movies/1"
```

Successful processed rows should have `trailer_status = COMPLETED`, a non-empty `trailer_url`, a non-empty `trailer_youtube_id`, `overall_status = TRAILER_FOUND`, and `next_agent = REVIEW_REACTION_AGENT`.

## Review + Script Writer Agent

Run it after trailers are found:

```bash
curl -X POST "http://127.0.0.1:8000/agents/review-script/run?limit=3"
```

Manual single-movie test:

```bash
curl -X POST "http://127.0.0.1:8000/agents/review-script/run/1"
```

Response example:

```json
{
  "success": true,
  "agent": "REVIEW_REACTION_AGENT",
  "processed": 3,
  "completed": 2,
  "failed": 1,
  "results": []
}
```

Check the movie:

```bash
curl "http://127.0.0.1:8000/movies/1"
```

Successful rows should have `review_status = COMPLETED`, `script_status = COMPLETED`, non-empty `final_script`, `script_data_json` with title/description/tags/keywords/hashtags/thumbnail text/BGM style, `overall_status = SCRIPT_READY`, and `next_agent = VOICE_GENERATOR_AGENT`.

## Voice Generator Agent

Approve a completed script before spending ElevenLabs credits:

```bash
curl -X POST "http://127.0.0.1:8000/movies/1/approve-processing"
```

Generate voice for one movie:

```bash
curl -X POST "http://127.0.0.1:8000/agents/voice-generator/run/1"
```

For local testing without approval:

```bash
curl -X POST "http://127.0.0.1:8000/agents/voice-generator/run/1?force=true"
```

Batch run:

```bash
curl -X POST "http://127.0.0.1:8000/agents/voice-generator/run?limit=1"
```

The agent uses `script_data_json.elevenlabs_script` when present, otherwise `final_script`. It removes supported emotion tags such as `[Excited]` and `[Whisper]`, keeps Hinglish text unchanged, and saves MP3 files locally to `storage/audio/movie_{movie_id}_{script_hash}.mp3`.

When `UPLOAD_AUDIO_TO_SUPABASE=true`, the local MP3 is uploaded to Supabase Storage at `audio/movie_{movie_id}_{script_hash}.mp3`, and `voice_audio_path` is saved as `movie-audio/audio/movie_{movie_id}_{script_hash}.mp3`. If the local file or Supabase storage path already exists for the same cleaned script, provider, voice id, and model id, ElevenLabs is not called again.

Create a private Supabase Storage bucket named:

```text
movie-audio
```

Keep the bucket private and put `SUPABASE_SERVICE_ROLE_KEY` only in the backend `.env`, never in frontend code.

Run safe cleanup after rendered videos exist:

```bash
curl -X POST "http://127.0.0.1:8000/agents/audio-cleanup/run?keep_last=20&safe_only=true"
```

With `safe_only=true`, cleanup keeps the latest `keep_last` audio rows and only deletes older storage files for movies where `final_video_path` is not null. It marks `voice_data_json.audio_deleted_from_storage` and `voice_data_json.audio_deleted_at` without changing script data or voice status.

Successful rows should have `voice_status = COMPLETED`, non-empty `voice_audio_path`, `voice_data_json.provider = elevenlabs`, `voice_data_json.storage_provider = supabase`, `overall_status = VOICE_READY`, and `next_agent = SCENE_SELECTION_AGENT`.

## Scene Selection Agent

Upload a 16:9 trailer first:

```bash
curl -X POST "http://127.0.0.1:8000/movies/1/source-video-upload" \
  -F "file=@official_trailer.mp4" \
  -F "label=official_trailer" \
  -F "type=trailer"
```

Optional teaser upload:

```bash
curl -X POST "http://127.0.0.1:8000/movies/1/source-video-upload" \
  -F "file=@official_teaser.mp4" \
  -F "label=official_teaser" \
  -F "type=teaser"
```

Then run scene selection:

```bash
curl -X POST "http://127.0.0.1:8000/agents/scene-selection/run/1?force=true"
```

The agent only analyzes horizontal 16:9 source videos and writes an edit plan into `scene_data_json`. It does not cut video, merge clips, render output, create 9:16 Shorts, add blurred background, or attach audio. Voice duration is detected from `voice_audio_path`, then target scene duration is calculated as voice duration plus the configured extra seconds.

Successful rows should have `scene_status = COMPLETED`, `scene_data_json.voice_duration_seconds`, `scene_data_json.target_duration_seconds`, `scene_data_json.source_videos_used`, `overall_status = SCENES_READY`, and `next_agent = CUT_MERGE_AGENT`.

## Cut Merge Agent

Run cut merge after scene selection:

```bash
curl -X POST "http://127.0.0.1:8000/agents/cut-merge/run/1?force=true"
```

Batch run:

```bash
curl -X POST "http://127.0.0.1:8000/agents/cut-merge/run?limit=1"
```

Check the movie row:

```bash
curl "http://127.0.0.1:8000/movies/1"
```

Preview the rendered 16:9 master file:

```bash
curl "http://127.0.0.1:8000/movies/1/master-video-file" --output master.mp4
```

This agent only creates a clean 16:9 master video. It does not create the 9:16 Shorts layout, does not add blurred background, does not attach voiceover, and does not add background music. Those steps are reserved for `SHORTS_COMPOSER_AGENT`.

Expected after success:

- `render_status = COMPLETED`
- `master_video_path` is not null
- `render_data_json.clip_count`, `render_data_json.transitions_used`, and `render_data_json.estimated_duration_seconds` are present
- `overall_status = MASTER_VIDEO_READY`
- `next_agent = SHORTS_COMPOSER_AGENT`

## Shorts Composer Agent

Run Shorts Composer after Cut Merge:

```bash
curl -X POST "http://127.0.0.1:8000/agents/shorts-composer/run/1?force=true"
```

Batch run:

```bash
curl -X POST "http://127.0.0.1:8000/agents/shorts-composer/run?limit=1"
```

Check the movie row:

```bash
curl "http://127.0.0.1:8000/movies/1"
```

Preview the draft 9:16 video:

```bash
curl "http://127.0.0.1:8000/movies/1/draft-video-file" --output draft-shorts.mp4
```

This agent creates only the draft 9:16 Shorts composition from the existing 16:9 master video and voice audio. It auto-detects top and bottom black bars, crops them out when present, uses that cropped clean frame for both the blurred background and the foreground layer, applies a stronger foreground zoom, brightens the foreground, keeps the background only slightly dark, and centers the foreground cleanly in the 9:16 canvas. Voice still starts at 0 seconds, optional low-volume BGM is still mixed, and BGM still fades near the end. It does not generate thumbnails or publishing metadata.

Expected after success:

- `shorts_status = COMPLETED`
- `draft_video_path` is not null
- `final_video_path` is set to the draft path for now when `SHORTS_SET_FINAL_VIDEO_PATH=true`
- `shorts_data_json` contains layout, audio mix, duration, and warnings
- `overall_status = DRAFT_VIDEO_READY`
- `next_agent = THUMBNAIL_METADATA_AGENT`

## Thumbnail Generator Agent

Run Thumbnail Generator after Shorts Composer:

```bash
curl -X POST "http://127.0.0.1:8000/agents/thumbnail/run/1?force=true"
```

Batch run:

```bash
curl -X POST "http://127.0.0.1:8000/agents/thumbnail/run?limit=1"
```

Check the movie row:

```bash
curl "http://127.0.0.1:8000/movies/1"
```

Preview the generated thumbnail:

```bash
curl "http://127.0.0.1:8000/movies/1/thumbnail-file" --output thumbnail.jpg
```

This agent generates high-contrast vertical YouTube Shorts styled thumbnails locally using Pillow and OpenCV (enhancing poster, creating a blurred background layer, applying shadows, drawing text banners with strokes, badges, etc.) and uploads the output to Supabase Storage.

Expected after success:

- `thumbnail_status = COMPLETED`
- `thumbnail_path` is set to the generated thumbnail location
- `overall_status = THUMBNAIL_READY`
- `next_agent = DONE`

## Notes

- The discovery agent uses TMDB `discover/movie` for `released` and `upcoming`.
- The discovery agent uses TMDB `trending/movie/week` for `trending`, then filters the results in Python.
- The trailer finder uses TMDB `/movie/{tmdb_id}/videos` and saves YouTube metadata only. It does not download videos.
- The review script agent uses TMDB details/reviews, a conservative Wikipedia summary lookup, and OpenAI JSON output. It stores review summaries and source URLs without copying long review text.
- Each movie is upserted by `tmdb_id`.
- A failed movie record does not stop the full discovery run.
- If your office proxy or antivirus breaks TMDB SSL verification, first try `TMDB_CA_BUNDLE` with your organization's CA file. For local testing only, you can temporarily set `TMDB_SSL_VERIFY=false`.
- If TMDB requests disconnect or time out, try toggling `TMDB_USE_ENV_PROXY` depending on whether your network requires a proxy.

## BGM Library APIs

Upload a music track:

```bash
curl -X POST "http://127.0.0.1:8000/bgm/api/upload" \
  -F "file=@sample.mp3"
```

List tracks:

```bash
curl "http://127.0.0.1:8000/bgm/api/list?page=1&page_size=20"
curl "http://127.0.0.1:8000/bgm/api/list?copyright_status=VERIFIED_SAFE"
curl "http://127.0.0.1:8000/bgm/api/list?bpm_min=100&bpm_max=150"
```

Fetch details, filter options, stats, and playback URL:

```bash
curl "http://127.0.0.1:8000/bgm/api/1"
curl "http://127.0.0.1:8000/bgm/api/filter-options"
curl "http://127.0.0.1:8000/bgm/api/stats"
curl "http://127.0.0.1:8000/bgm/api/1/play-url"
```

Reanalyze an existing stored track:

```bash
curl -X POST "http://127.0.0.1:8000/bgm/api/1/reanalyze"
```

BGM upload behavior:

- The backend accepts only the audio file and computes metadata, SHA-256, fingerprint, recognition, and cautious copyright status automatically.
- Duplicate uploads are prevented by `sha256_hash`; the existing row is returned with `already_exists=true`.
- Recognition failure does not reject a valid upload. The track is still stored and defaults to `copyright_status=UNKNOWN`.
- Playback uses temporary signed Supabase URLs from the private `bgm-library` bucket. Permanent public URLs are not stored.
