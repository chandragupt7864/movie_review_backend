# Review + Script Writer Agent

Collects research and generates a Hindi Hinglish YouTube Shorts script for movies already discovered and trailer-processed.

The text model is selected with `SCRIPT_PROVIDER`: `gemini` uses the configured
Gemini model and `openai` uses the configured OpenAI model.

## Input

Reads rows from `movie_review_pipeline` where:

- `is_active = true`
- `is_locked = false`
- `next_agent = 'REVIEW_REACTION_AGENT'`
- `trailer_status = 'COMPLETED'`
- `review_status = 'PENDING'`
- `script_status = 'PENDING'`

Manual runs by movie id can process any unlocked active movie.

## Research Sources

- TMDB movie details with credits, keywords, and external ids
- TMDB reviews, summarized to short snippets only
- Wikipedia search and page summary when available

The agent stores source URLs and short summaries in `review_data_json`.

Before script generation, the script service compares the TMDB release date with
the current date (falling back to TMDB status when needed). Released titles use an
"agar abhi tak nahi dekhi, dekh lo" recommendation style; upcoming titles are
clearly framed as aane wali/upcoming without pretending they have been watched.
The opening hook must come from the movie's actual story or central conflict;
generic "Ruko ruko" attention hooks are rejected and regenerated.

## Output

Updates the same `movie_review_pipeline` row with:

- `review_status = COMPLETED`
- `script_status = COMPLETED`
- `review_data_json`
- `script_data_json`
- `final_script`
- `overall_status = SCRIPT_READY`
- `next_agent = VOICE_GENERATOR_AGENT`

No video is downloaded. No cut/merge work is performed.
