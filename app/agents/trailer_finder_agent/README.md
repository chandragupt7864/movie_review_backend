# Trailer Finder Agent

Finds a trailer or teaser for movies discovered by the Movie Discovery Agent.

## Input

Reads rows from `movie_review_pipeline` where:

- `is_active = true`
- `is_locked = false`
- `next_agent = 'TRAILER_FINDER_AGENT'`
- `trailer_status = 'PENDING'`

Manual runs by movie id can process any unlocked active movie.

## Output

Updates the same `movie_review_pipeline` row with:

- `trailer_status`
- `trailer_youtube_id`
- `trailer_url`
- `trailer_title`
- `trailer_type`
- `trailer_official`
- `trailer_data_json`
- pipeline status fields and timeline events

The agent uses TMDB `/movie/{tmdb_id}/videos` only. It does not download YouTube videos and does not perform cut/merge work.
