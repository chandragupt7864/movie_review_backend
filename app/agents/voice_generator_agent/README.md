# Voice Generator Agent

Generates MP3 voice audio from an already completed script using ElevenLabs only.

## Queue rules

The agent processes rows in `movie_review_pipeline` where:

- `next_agent = VOICE_GENERATOR_AGENT`
- `script_status = COMPLETED`
- `voice_status = PENDING`
- `final_script IS NOT NULL`
- `is_locked = FALSE`
- `is_active = TRUE`
- `is_approved_for_processing = TRUE` when `VOICE_REQUIRE_APPROVAL=true`

Manual endpoints can pass `force=true` to skip only the approval requirement.

## Audio caching

The agent cleans emotion tags, hashes the cleaned text with the provider, voice id, and model id, then saves:

```text
storage/audio/movie_{movie_id}_{script_hash}.mp3
```

If that file already exists, ElevenLabs is not called again and `voice_data_json.cached` is set to `true`.

When `UPLOAD_AUDIO_TO_SUPABASE=true`, the MP3 is uploaded to the private Supabase bucket configured by `SUPABASE_AUDIO_BUCKET`:

```text
audio/movie_{movie_id}_{script_hash}.mp3
```

The database `voice_audio_path` is saved as:

```text
movie-audio/audio/movie_{movie_id}_{script_hash}.mp3
```

If the Supabase storage path already exists, the agent reuses it and does not call ElevenLabs.

## Endpoints

```bash
curl -X POST "http://127.0.0.1:8000/agents/voice-generator/run?limit=1"
curl -X POST "http://127.0.0.1:8000/agents/voice-generator/run/1"
curl -X POST "http://127.0.0.1:8000/agents/voice-generator/run/1?force=true"
curl -X POST "http://127.0.0.1:8000/agents/audio-cleanup/run?keep_last=20&safe_only=true"
```

## Cleanup

Safe cleanup keeps the latest `keep_last` audio rows and deletes only older Supabase files for movies where `final_video_path` is not null. Deleted rows are marked in `voice_data_json` with `audio_deleted_from_storage` and `audio_deleted_at`; script fields and `voice_status` are not cleared.

