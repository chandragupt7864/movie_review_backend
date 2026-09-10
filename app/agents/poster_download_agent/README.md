# Poster Download Agent

`POSTER_DOWNLOAD_AGENT` downloads movie poster and backdrop images from database URLs, saves them locally under `storage/posters/movie_{movie_id}/`, and registers local paths in the database.

## REST Endpoints

1. Batch run:
   `POST /agents/poster-download/run?limit=10`

2. Single movie trigger:
   `POST /agents/poster-download/run/{movie_id}?force=true`
