# Video Downloader Agent

The **Video Downloader Agent** is responsible for automatically fetching and saving trailer/teaser source videos from YouTube for movies in the pipeline.

## Functionality
- Runs after the script and voiceover generation is completed.
- Reads the video's YouTube URL/ID from the pipeline row.
- Downloads the video using `yt-dlp` via `YoutubeDownloaderService`.
- Places the downloaded trailer under `storage/source_videos/movie_{movie_id}/` inside the project root, keeping directories organized per movie.
- Validates the aspect ratio and metadata via `VideoMetadataService` to ensure a 16:9 widescreen format is saved.
- Registers the source video in the database, transitioning the `next_agent` to `SCENE_SELECTION_AGENT`.
