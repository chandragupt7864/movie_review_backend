# Thumbnail Generator Agent

`THUMBNAIL_METADATA_AGENT` downloads the movie poster, backdrop, and extracts video frames from the compiled draft/final video. It then generates a YouTube Shorts styled vertical (or landscape) high-contrast poster thumbnail using PIL and OpenCV. Finally, it uploads the image to Supabase Storage and updates the database row.

## Workflow

1. Run cut-merge (creates master video):
   `POST /agents/cut-merge/run/{id}?force=true`
2. Run shorts-composer (creates vertical video):
   `POST /agents/shorts-composer/run/{id}?force=true`
3. Generate Thumbnail:
   `POST /agents/thumbnail/run/{id}?force=true`
4. Check final movie details:
   `GET /movies/{id}`

## Expected Outcomes

* `thumbnail_status = COMPLETED`
* `thumbnail_path` points to the uploaded/generated image.
* `overall_status = THUMBNAIL_READY`
* `next_agent = DONE`
