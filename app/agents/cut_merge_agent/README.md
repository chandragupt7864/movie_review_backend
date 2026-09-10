# Cut Merge Agent

`CUT_MERGE_AGENT` reads `scene_data_json`, cuts approved scenes from local 16:9 MP4 source files, inserts safe flash-style transitions when requested, and renders a clean 16:9 master video.

It does not create the final 9:16 Shorts layout, does not add voiceover, does not add background music, and does not touch `final_video_path`. On success it saves `master_video_path`, updates `render_data_json`, sets `overall_status = MASTER_VIDEO_READY`, and queues `next_agent = SHORTS_COMPOSER_AGENT`.

