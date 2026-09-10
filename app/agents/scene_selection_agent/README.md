# Scene Selection Agent

Selects the best horizontal 16:9 scenes from uploaded trailer, teaser, clip, or promo videos and stores an edit plan in `scene_data_json`.

What it does:

- Validates uploaded source videos are horizontal 16:9 MP4 files.
- Reads uploaded voice audio duration.
- Targets total scene duration as `voice duration + configured extra seconds`.
- Uses Gemini video analysis to select scenes and transition suggestions.
- Saves a validated edit plan for `CUT_MERGE_AGENT`.

What it does not do:

- No FFmpeg cutting
- No merge output
- No 9:16 Shorts composition
- No blurred background
- No audio attachment

