# Movie Discovery Agent

This agent fetches Hollywood English-language movies from TMDB for the supported categories:

- `released`
- `upcoming`
- `trending`

It filters the movies to these genres only:

- Action
- Horror
- Science Fiction

The agent upserts each movie into the `movie_review_pipeline` table and prepares the row for the next agent.

