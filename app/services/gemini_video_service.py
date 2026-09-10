import json
import math
from pathlib import Path
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from app.config import PROJECT_ROOT, settings


SCENE_SELECTION_PROMPT = """You are an expert movie trailer editor and YouTube Shorts video editor.

Analyze the provided one or more 16:9 horizontal trailer/teaser/promo videos for the same movie and select the best scenes for a high-retention Hindi Hinglish YouTube Shorts movie review.

Important:
You are NOT receiving Shorts/Reels/vertical clips.
Use only the uploaded 16:9 trailer/teaser source videos.
Do not select scenes from vertical Shorts/Reels.
Your output is for creating a clean 16:9 master video first.
A later Shorts Composer Agent will convert that 16:9 master into a 9:16 YouTube Shorts layout with blurred background.

Final pipeline:
Stage 1:
You select scenes from original 16:9 trailer/teaser videos.

Stage 2:
Cut Merge Agent will create a clean 16:9 master video from your selected scenes.

Stage 3:
Shorts Composer Agent will place the 16:9 master video inside a 9:16 canvas with blurred background, voiceover audio, and low background music.

Movie review style:

* Fast
* Punchy
* Suspenseful
* High energy
* Eye-catching
* Action / Adventure / Horror / Sci-Fi focused
* Suitable for Hindi Hinglish voiceover
* No boring dialogue-only scenes
* No repeated similar scenes
* Strong hook at the beginning
* Story setup after hook
* Twist / danger / mystery in the middle
* High visual peak near the end
* Final reveal / cinematic shot at the end

Voiceover audio duration:
{{VOICE_DURATION_SECONDS}} seconds

Target selected scene duration:
{{TARGET_DURATION_SECONDS}} seconds

Extra visual duration after voice:
{{EXTRA_VISUAL_SECONDS_AFTER_VOICE}} seconds

Minimum number of distinct scenes required:
{{MINIMUM_SCENE_COUNT}}

This means:

* The final selected scenes should be around voice duration + 5 to 10 seconds.
* Voice audio will start at 0 seconds in the final composer stage.
* After voiceover ends, keep 5 to 10 seconds of final cinematic visual so background music can fade out.

Source videos:
{{SOURCE_VIDEOS_CONTEXT}}

Movie context:
{{MOVIE_CONTEXT}}

Mandatory visual priorities inferred from the story/script:
{{VISUAL_PRIORITIES}}

Before choosing timestamps, inspect the full duration of every uploaded source and build an internal visual inventory.
The final JSON must favor what is visibly on screen, not merely what has high motion or dramatic audio.
If a priority names a creature, character, vehicle, location, weapon, disaster, or supernatural element, show that subject clearly in several distinct shots.
For creature/dinosaur movies, include at least four distinct shots where the creature/dinosaur is visibly present; use a creature reveal or attack for the hook and another strong creature/action shot near the climax when the footage permits.
Do not call a scene "action" only because the camera moves quickly. The reason and content_tags must describe the visible subject and physical action.
When two or more valid source videos are provided, use at least two sources and normally select at least two scenes from each source.

Scene order:

1. Hook scene:
   The most visually eye-catching scene.
   It should grab attention within the first 1 to 3 seconds.

2. Story setup:
   Scene that quickly shows what the movie is about.

3. Twist / danger / mystery:
   Scene that creates suspense or curiosity.

4. Action / horror / sci-fi peak:
   Strong visual scene with high energy.

5. Final reveal / climax:
   Cinematic scene suitable for ending and post-voice visual continuation.

Scene rules:

* Select scenes from all provided 16:9 trailers/teasers.
* Every scene must include which source video it comes from.
* Every scene must include source_video_path.
* Every scene must include source_video_label.
* Do not pick duplicate-looking scenes from different videos.
* Prefer strong visual energy.
* Avoid dialogue-only/static scenes.
* NEVER select studio logos, production-company logos, distributor logos, ratings/approval cards, title cards, release-date cards, social handles, website cards, or end-credit screens.
* Animated brand/logo reveals are forbidden even when they contain motion, light flashes, particles, or dramatic music.
* Avoid black screen.
* Avoid long slow scenes.
* Each scene should be 2 to 5 seconds.
* Return at least {{MINIMUM_SCENE_COUNT}} distinct scenes.
* Total selected scene duration MUST be at least {{MINIMUM_TOTAL_SECONDS}} seconds and should be close to the target selected scene duration.
* For every source, stay inside its selectable_start_seconds and selectable_end_seconds range so intro logos and outro cards are not removed later.
* Final scene should be strong enough to continue after voiceover ends.
* Use timestamps accurately.
* Return only valid JSON.
* Do not include markdown.
* Do not include explanation outside JSON.

Allowed transition_after values:

* cut
* flash_cut
* crossfade
* black_flash
* zoom_cut
* glitch
* whip_pan

Allowed zoom values:

* none
* slow_zoom_in
* slow_zoom_out
* punch_zoom

Allowed speed values:

* normal
* 1.10x
* 1.25x
* slow_motion

Genre behavior:
If movie is Action or Adventure:

* Prefer fight, chase, explosion, jump, crash, impact, weapon, running, flying, high movement scenes.
* The hook must itself be a strong action/impact/creature shot, never a logo, title, dialogue close-up, or brand reveal.
* At least 70% of selected duration should show physical action, combat, pursuit, destruction, supernatural attack, creature movement, or immediate danger.
* For Adventure, also prefer ocean travel, jungle, mountain, escape, discovery, creature, storm, large-scale movement, and wonder shots with motion.
* Use flash_cut, whip_pan, zoom_cut.
* Select noticeably more action/excited scenes than normal calm scenes.
* Keep dialogue-only or emotional pause scenes to a minimum unless needed for story clarity.
* After hook, keep the pacing aggressive and visually kinetic.

If movie is Horror:

* Prefer dark room, creepy face, fear reaction, monster reveal, jump-scare buildup, silence before danger.
* Use black_flash, glitch, slow_zoom_in.

If movie is Science Fiction:

* Prefer spaceship, alien, futuristic tech, experiment, portal, space, robot, city destruction, mind-bending visuals.
* Use glitch, crossfade, zoom_cut.

Return this exact JSON schema only:

{
"agent": "SCENE_SELECTION_AGENT",
"video_format_for_next_agent": "16:9",
"master_resolution": "1920x1080",
"voice_duration_seconds": 0,
"extra_visual_seconds_after_voice": 7,
"target_duration_seconds": 0,
"estimated_total_duration_seconds": 0,
"editing_style": "fast cinematic movie review shorts",
"source_video_rule": "Only horizontal 16:9 trailer/teaser/promo videos are used. Shorts/Reels/vertical videos are not allowed.",
"source_videos_used": [
{
"label": "official_trailer",
"source_video_path": "storage/source_videos/movie_1_trailer.mp4",
"type": "trailer",
"aspect_ratio": "16:9"
}
],
"genre_focus": ["Action", "Horror", "Science Fiction"],
"scene_strategy": "hook -> story setup -> twist -> visual peak -> final reveal",
"scenes": [
{
"order": 1,
"source_video_label": "official_trailer",
"source_video_path": "storage/source_videos/movie_1_trailer.mp4",
"start": "00:00:00.000",
"end": "00:00:04.000",
"duration_seconds": 4.0,
"scene_type": "hook",
"mood": "hype",
"visual_energy": "high",
"transition_after": "flash_cut",
"transition_duration_seconds": 0.12,
"zoom": "slow_zoom_in",
"speed": "normal",
"text_overlay_suggestion": "Ruko ruko bhai...",
"reason": "Most eye-catching opening scene from trailer",
"content_tags": ["visible subject", "physical action"],
"score": 9
}
],
"post_voice_visual_plan": {
"enabled": true,
"duration_seconds": 7,
"purpose": "Keep final cinematic visual after voice ends while background music fades out",
"preferred_scene_type": "final reveal or cinematic climax"
},
"render_notes": {
"cut_merge_output": "Create clean 16:9 master video from original 16:9 trailer/teaser scenes",
"source_video_rule": "Only horizontal 16:9 trailer/teaser videos are allowed. Do not use Shorts/Reels source videos.",
"shorts_composer_note": "Later composer will place this 16:9 master video into a 9:16 Shorts canvas with blurred background",
"audio_note": "Voice audio starts from 0 seconds. Video should continue 5 to 10 seconds after voice ends.",
"bgm_note": "Background music should be low volume around 8% to 15% and fade out in the final extra seconds."
},
"warnings": []
}"""

ALLOWED_TRANSITIONS = {"cut", "flash_cut", "crossfade", "black_flash", "zoom_cut", "glitch", "whip_pan"}
ALLOWED_ZOOMS = {"none", "slow_zoom_in", "slow_zoom_out", "punch_zoom"}
ALLOWED_SPEEDS = {"normal", "1.10x", "1.25x", "slow_motion"}


class GeminiVideoService:
    MAX_SCENE_PLAN_ATTEMPTS = 3

    def __init__(self) -> None:
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not configured.")
        self.model_name = settings.gemini_model

        try:
            from google import genai
        except ModuleNotFoundError as exc:
            raise ValueError("google-genai package is not installed. Run pip install -r requirements.txt.") from exc

        self._genai = genai
        self.client = genai.Client(api_key=settings.gemini_api_key)

    def analyze_video_for_scenes(
        self,
        source_videos: list[dict],
        movie_context: dict,
        voice_duration_seconds: float,
        target_duration_seconds: float,
        extra_visual_seconds_after_voice: float,
    ) -> dict:
        prompt = self._build_prompt(
            source_videos=source_videos,
            movie_context=movie_context,
            voice_duration_seconds=voice_duration_seconds,
            target_duration_seconds=target_duration_seconds,
            extra_visual_seconds_after_voice=extra_visual_seconds_after_voice,
        )
        upload_handles = [self._upload_video(video["source_video_path"]) for video in source_videos]
        attempt_prompt = prompt
        last_error = "Gemini returned an invalid scene plan."

        for attempt in range(self.MAX_SCENE_PLAN_ATTEMPTS):
            response_text = self._generate_response_text(prompt=attempt_prompt, uploaded_files=upload_handles)
            try:
                raw_plan = json.loads(response_text)
            except json.JSONDecodeError:
                validation = {
                    "valid": False,
                    "retry_reason": "The previous answer was not valid JSON. Return only JSON matching the schema.",
                    "error": "Gemini returned invalid JSON.",
                }
            else:
                validation = self.validate_scene_plan(
                    scene_plan=raw_plan,
                    source_videos=source_videos,
                    voice_duration_seconds=voice_duration_seconds,
                    target_duration_seconds=target_duration_seconds,
                    movie_context=movie_context,
                )
                if validation["valid"]:
                    return validation["scene_plan"]

            last_error = str(validation.get("error") or last_error)
            if attempt + 1 >= self.MAX_SCENE_PLAN_ATTEMPTS:
                break
            issue = str(validation.get("retry_reason") or validation.get("error") or last_error)
            attempt_prompt = (
                prompt
                + "\n\nThe previous scene plan failed validation. Fix the exact issue below and rebuild the complete plan."
                + "\nDo not shorten or omit otherwise valid semantic/action scenes. Return corrected JSON only."
                + f"\nValidation issue: {issue}"
                + f"\nPrevious answer:\n{response_text}"
            )

        raise ValueError(f"{last_error} Gemini scene plan remained invalid after {self.MAX_SCENE_PLAN_ATTEMPTS} attempts.")

    def validate_scene_plan(
        self,
        scene_plan: dict,
        source_videos: list[dict],
        voice_duration_seconds: float,
        target_duration_seconds: float,
        movie_context: dict | None = None,
    ) -> dict:
        if not isinstance(scene_plan, dict):
            return {"valid": False, "error": "Scene plan must be a JSON object."}

        source_by_path = {str(item["source_video_path"]): item for item in source_videos}
        raw_scenes = scene_plan.get("scenes")
        if not isinstance(raw_scenes, list) or not raw_scenes:
            return {"valid": False, "error": "Scene plan must include at least one scene."}

        warnings = list(scene_plan.get("warnings") or [])
        validated_scenes: list[dict] = []
        seen_ranges: set[tuple[str, str, str]] = set()
        card_range_rejections = 0

        for index, raw_scene in enumerate(raw_scenes, start=1):
            if not isinstance(raw_scene, dict):
                continue

            source_video_path = str(raw_scene.get("source_video_path") or "").strip()
            source_video_label = str(raw_scene.get("source_video_label") or "").strip()
            start = str(raw_scene.get("start") or "").strip()
            end = str(raw_scene.get("end") or "").strip()

            if not source_video_path or source_video_path not in source_by_path:
                return {"valid": False, "error": f"Invalid source_video_path in scene {index}."}
            if not source_video_label:
                return {"valid": False, "error": f"Missing source_video_label in scene {index}."}
            if not start or not end:
                return {"valid": False, "error": f"Scene {index} must include start and end timestamps."}
            start_seconds = self._timestamp_to_seconds(start)
            end_seconds = self._timestamp_to_seconds(end)
            if start_seconds >= end_seconds:
                return {"valid": False, "error": f"Scene {index} start timestamp must be before end timestamp."}
            source_duration = float(source_by_path[source_video_path].get("duration_seconds") or 0.0)
            if source_duration > 0:
                intro_guard = min(float(settings.scene_trailer_intro_skip_seconds), source_duration * 0.18)
                outro_guard = min(float(settings.scene_trailer_outro_skip_seconds), source_duration * 0.12)
                # The prompt advertises these values as inclusive selectable boundaries.
                # Accept an exact-boundary scene and reject only footage that crosses
                # into the guarded intro/outro range.
                if start_seconds < intro_guard or end_seconds > source_duration - outro_guard:
                    card_range_rejections += 1
                    continue
            timestamp_duration_seconds = round(end_seconds - start_seconds, 3)
            raw_duration_seconds = float(raw_scene.get("duration_seconds") or 0.0)
            if timestamp_duration_seconds > 6.0:
                duration_seconds = raw_duration_seconds if 1.5 <= raw_duration_seconds <= 5.0 else 5.0
                end_seconds = start_seconds + duration_seconds
                end = self._seconds_to_timestamp(end_seconds)
                timestamp_duration_seconds = round(duration_seconds, 3)
                warnings.append(f"Scene {index} was trimmed to {duration_seconds:.1f} seconds.")
            else:
                duration_seconds = timestamp_duration_seconds
            if not 1.5 <= duration_seconds <= 6.0:
                return {"valid": False, "error": f"Scene {index} duration must be between 1.5 and 6 seconds."}

            signature = (source_video_path, start, end)
            if signature in seen_ranges:
                continue
            seen_ranges.add(signature)

            scene = {
                "order": len(validated_scenes) + 1,
                "source_video_label": source_video_label,
                "source_video_path": source_video_path,
                "start": start,
                "end": end,
                "duration_seconds": round(duration_seconds, 3),
                "scene_type": str(raw_scene.get("scene_type") or "scene"),
                "mood": str(raw_scene.get("mood") or "cinematic"),
                "visual_energy": str(raw_scene.get("visual_energy") or "medium"),
                "transition_after": self._allowed_or_default(str(raw_scene.get("transition_after") or ""), ALLOWED_TRANSITIONS, "cut"),
                "transition_duration_seconds": float(raw_scene.get("transition_duration_seconds") or 0.12),
                "zoom": self._allowed_or_default(str(raw_scene.get("zoom") or ""), ALLOWED_ZOOMS, "none"),
                "speed": self._allowed_or_default(str(raw_scene.get("speed") or ""), ALLOWED_SPEEDS, "normal"),
                "text_overlay_suggestion": str(raw_scene.get("text_overlay_suggestion") or ""),
                "reason": str(raw_scene.get("reason") or ""),
                "content_tags": [
                    str(tag).strip().lower()
                    for tag in (raw_scene.get("content_tags") or [])
                    if str(tag).strip()
                ],
                "score": int(raw_scene.get("score") or 5),
            }
            validated_scenes.append(scene)

        if not validated_scenes:
            return {"valid": False, "error": "No valid scenes remained after validation."}

        if card_range_rejections:
            warnings.append(
                f"Removed {card_range_rejections} scene(s) from trailer intro/outro card ranges."
            )

        validated_scenes.sort(key=lambda scene: int(scene["order"]))
        validated_scenes = self._trim_overlaps(validated_scenes)
        estimated_total_duration_seconds = round(sum(float(scene["duration_seconds"]) for scene in validated_scenes), 3)

        if estimated_total_duration_seconds < max(target_duration_seconds - 5.0, voice_duration_seconds):
            return {
                "valid": False,
                "retry_reason": (
                    f"Selected scenes total only {estimated_total_duration_seconds} seconds, "
                    f"but target duration is about {target_duration_seconds} seconds. Add more scenes."
                ),
                "error": "Scene plan duration is too short.",
            }

        trimmed_scenes = validated_scenes[:]
        if estimated_total_duration_seconds > target_duration_seconds + 5.0:
            trimmed_scenes = self._trim_to_target(trimmed_scenes, target_duration_seconds)
            estimated_total_duration_seconds = round(sum(float(scene["duration_seconds"]) for scene in trimmed_scenes), 3)
            warnings.append("Selected scenes were trimmed in Python to stay closer to target duration.")

        semantic_retry_reason = self._semantic_retry_reason(
            scenes=trimmed_scenes,
            source_videos=source_videos,
            movie_context=movie_context or {},
        )
        if semantic_retry_reason:
            return {
                "valid": False,
                "retry_reason": semantic_retry_reason,
                "error": "Scene plan does not satisfy story-specific visual requirements.",
            }

        source_videos_used = []
        used_paths = {scene["source_video_path"] for scene in trimmed_scenes}
        for source_video in source_videos:
            if source_video["source_video_path"] in used_paths:
                source_videos_used.append(
                    {
                        "label": source_video["label"],
                        "source_video_path": source_video["source_video_path"],
                        "type": source_video.get("type", "trailer"),
                        "aspect_ratio": source_video.get("aspect_ratio", "16:9"),
                    }
                )

        normalized_plan = {
            "agent": "SCENE_SELECTION_AGENT",
            "video_format_for_next_agent": scene_plan.get("video_format_for_next_agent") or settings.scene_output_format,
            "master_resolution": scene_plan.get("master_resolution") or settings.scene_master_resolution,
            "voice_duration_seconds": round(float(voice_duration_seconds), 3),
            "extra_visual_seconds_after_voice": round(max(target_duration_seconds - voice_duration_seconds, 0.0), 3),
            "target_duration_seconds": round(float(target_duration_seconds), 3),
            "estimated_total_duration_seconds": estimated_total_duration_seconds,
            "editing_style": scene_plan.get("editing_style") or "fast cinematic movie review shorts",
            "source_video_rule": scene_plan.get("source_video_rule")
            or "Only horizontal 16:9 trailer/teaser/promo videos are used. Shorts/Reels/vertical videos are not allowed.",
            "source_videos_used": source_videos_used,
            "genre_focus": scene_plan.get("genre_focus") or [],
            "scene_strategy": scene_plan.get("scene_strategy") or "hook -> story setup -> twist -> visual peak -> final reveal",
            "scenes": trimmed_scenes,
            "post_voice_visual_plan": scene_plan.get("post_voice_visual_plan")
            or {
                "enabled": True,
                "duration_seconds": round(max(target_duration_seconds - voice_duration_seconds, 0.0), 3),
                "purpose": "Keep final cinematic visual after voice ends while background music fades out",
                "preferred_scene_type": "final reveal or cinematic climax",
            },
            "render_notes": scene_plan.get("render_notes")
            or {
                "cut_merge_output": "Create clean 16:9 master video from original 16:9 trailer/teaser scenes",
                "source_video_rule": "Only horizontal 16:9 trailer/teaser videos are allowed. Do not use Shorts/Reels source videos.",
                "shorts_composer_note": "Later composer will place this 16:9 master video into a 9:16 Shorts canvas with blurred background",
                "audio_note": "Voice audio starts from 0 seconds. Video should continue 5 to 10 seconds after voice ends.",
                "bgm_note": "Background music should be low volume around 8% to 15% and fade out in the final extra seconds.",
            },
            "warnings": warnings,
        }

        if abs(estimated_total_duration_seconds - target_duration_seconds) > 5.0:
            normalized_plan["warnings"].append(
                "Target duration could not be matched exactly, but the closest validated scene plan was saved."
            )

        return {"valid": True, "scene_plan": normalized_plan}

    def _generate_response_text(self, prompt: str, uploaded_files: list[object]) -> str:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                self.client.models.generate_content,
                model=self.model_name,
                contents=[prompt, *uploaded_files],
                config={"response_mime_type": "application/json"},
            )
            try:
                response = future.result(timeout=max(30, int(settings.gemini_generate_timeout_seconds)))
            except FuturesTimeoutError as exc:
                future.cancel()
                raise TimeoutError(
                    f"Gemini scene generation timed out after {int(settings.gemini_generate_timeout_seconds)} seconds."
                ) from exc
        text = getattr(response, "text", None)
        if text:
            return str(text)
        raise ValueError("Gemini returned an empty response.")

    def _upload_video(self, source_video_path: str):
        path = Path(source_video_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        uploaded = self.client.files.upload(file=str(path))
        file_name = getattr(uploaded, "name", None)
        if not file_name:
            return uploaded

        state = getattr(uploaded, "state", None)
        started_at = time.monotonic()
        while getattr(state, "name", None) == "PROCESSING":
            if time.monotonic() - started_at > max(30, int(settings.gemini_file_processing_timeout_seconds)):
                raise TimeoutError(
                    f"Gemini file processing timed out after {int(settings.gemini_file_processing_timeout_seconds)} "
                    f"seconds for {source_video_path}."
                )
            time.sleep(1)
            uploaded = self.client.files.get(name=file_name)
            state = getattr(uploaded, "state", None)

        if getattr(state, "name", None) == "FAILED":
            raise ValueError(f"Gemini file processing failed for {source_video_path}.")
        return uploaded

    @staticmethod
    def _build_prompt(
        source_videos: list[dict],
        movie_context: dict,
        voice_duration_seconds: float,
        target_duration_seconds: float,
        extra_visual_seconds_after_voice: float,
    ) -> str:
        visual_priorities = GeminiVideoService._derive_visual_priorities(movie_context)
        minimum_scene_count = max(5, math.ceil(target_duration_seconds / 4.0))
        minimum_total_seconds = max(target_duration_seconds - 5.0, voice_duration_seconds)
        prompt_sources = []
        for source_video in source_videos:
            prompt_source = dict(source_video)
            source_duration = float(source_video.get("duration_seconds") or 0.0)
            if source_duration > 0:
                prompt_source["selectable_start_seconds"] = round(
                    min(float(settings.scene_trailer_intro_skip_seconds), source_duration * 0.18), 3
                )
                prompt_source["selectable_end_seconds"] = round(
                    source_duration
                    - min(float(settings.scene_trailer_outro_skip_seconds), source_duration * 0.12),
                    3,
                )
            prompt_sources.append(prompt_source)
        return (
            SCENE_SELECTION_PROMPT.replace("{{VOICE_DURATION_SECONDS}}", f"{voice_duration_seconds:.3f}")
            .replace("{{TARGET_DURATION_SECONDS}}", f"{target_duration_seconds:.3f}")
            .replace("{{EXTRA_VISUAL_SECONDS_AFTER_VOICE}}", f"{extra_visual_seconds_after_voice:.3f}")
            .replace("{{MINIMUM_SCENE_COUNT}}", str(minimum_scene_count))
            .replace("{{MINIMUM_TOTAL_SECONDS}}", f"{minimum_total_seconds:.3f}")
            .replace("{{SOURCE_VIDEOS_CONTEXT}}", json.dumps(prompt_sources, indent=2))
            .replace("{{MOVIE_CONTEXT}}", json.dumps(movie_context, indent=2))
            .replace("{{VISUAL_PRIORITIES}}", json.dumps(visual_priorities, indent=2))
        )

    @staticmethod
    def _context_text(movie_context: dict) -> str:
        return " ".join(
            str(movie_context.get(key) or "")
            for key in (
                "movie_title",
                "overview",
                "final_script",
                "elevenlabs_script",
                "script_title",
                "script_description",
            )
        ).lower()

    @staticmethod
    def _derive_visual_priorities(movie_context: dict) -> list[str]:
        context = GeminiVideoService._context_text(movie_context)
        genres = {str(item).strip().lower() for item in (movie_context.get("genres") or [])}
        priorities: list[str] = []
        if any(word in context for word in ("dinosaur", "dinosaurs", "prehistoric", "t-rex", "raptor")):
            priorities.extend(
                [
                    "dinosaurs or prehistoric creatures clearly visible on screen",
                    "distinct dinosaur reveal, attack, chase, roar, or human escape shots",
                    "family survival and immediate danger caused by dinosaurs",
                ]
            )
        if any(word in context for word in ("monster", "creature", "beast", "dragon")):
            priorities.append("the central creature/monster visibly moving, attacking, or threatening characters")
        if any(word in context for word in ("alien", "spaceship", "robot", "portal")):
            priorities.append("the central sci-fi subject such as alien, spaceship, robot, or portal clearly visible")
        if genres.intersection({"action", "adventure", "science fiction", "sci-fi", "horror"}):
            priorities.append("physical action, pursuit, destruction, impact, or immediate danger instead of static dialogue")
        return list(dict.fromkeys(priorities))

    @staticmethod
    def requires_semantic_selection(movie_context: dict) -> bool:
        context = GeminiVideoService._context_text(movie_context)
        return any(
            word in context
            for word in (
                "dinosaur",
                "dinosaurs",
                "prehistoric",
                "t-rex",
                "raptor",
                "monster",
                "creature",
                "beast",
                "dragon",
                "alien",
                "spaceship",
                "robot",
                "portal",
            )
        )

    @staticmethod
    def _semantic_retry_reason(scenes: list[dict], source_videos: list[dict], movie_context: dict) -> str | None:
        if len(source_videos) >= 2:
            used_paths = {str(scene.get("source_video_path") or "") for scene in scenes}
            if len(used_paths) < 2:
                return "Use scenes from at least two different uploaded source videos; do not rely on only one trailer."

        context = GeminiVideoService._context_text(movie_context)
        dinosaur_context = any(
            word in context for word in ("dinosaur", "dinosaurs", "prehistoric", "t-rex", "raptor")
        )
        if dinosaur_context:
            dinosaur_terms = {"dinosaur", "dinosaurs", "prehistoric", "t-rex", "trex", "raptor", "creature"}
            matching = 0
            for scene in scenes:
                evidence = " ".join(
                    [
                        str(scene.get("scene_type") or ""),
                        str(scene.get("reason") or ""),
                        " ".join(str(tag) for tag in (scene.get("content_tags") or [])),
                    ]
                ).lower()
                if any(term in evidence for term in dinosaur_terms):
                    matching += 1
            required = min(4, max(2, int(math.ceil(len(scenes) * 0.35))))
            if matching < required:
                return (
                    f"This is a dinosaur story. At least {required} selected scenes must visibly show dinosaurs/"
                    "prehistoric creatures. Describe that visible evidence in content_tags and reason."
                )
        return None

    @staticmethod
    def _allowed_or_default(value: str, allowed: set[str], default: str) -> str:
        return value if value in allowed else default

    @staticmethod
    def _timestamp_to_seconds(value: str) -> float:
        parts = value.split(":")
        if len(parts) != 3:
            raise ValueError(f"Invalid timestamp: {value}")
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return (hours * 3600) + (minutes * 60) + seconds

    @staticmethod
    def _seconds_to_timestamp(value: float) -> str:
        total = max(0.0, float(value))
        hours = int(total // 3600)
        minutes = int((total % 3600) // 60)
        seconds = total % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"

    @staticmethod
    def _trim_overlaps(scenes: list[dict]) -> list[dict]:
        filtered: list[dict] = []
        accepted_ranges: dict[str, list[tuple[float, float]]] = {}
        for scene in scenes:
            path = scene["source_video_path"]
            start = GeminiVideoService._timestamp_to_seconds(scene["start"])
            end = GeminiVideoService._timestamp_to_seconds(scene["end"])
            ranges_for_source = accepted_ranges.setdefault(path, [])
            if any(start < existing_end and end > existing_start for existing_start, existing_end in ranges_for_source):
                continue
            filtered.append(scene)
            ranges_for_source.append((start, end))
        for order, scene in enumerate(filtered, start=1):
            scene["order"] = order
        return filtered

    @staticmethod
    def _trim_to_target(scenes: list[dict], target_duration_seconds: float) -> list[dict]:
        trimmed = sorted(scenes, key=lambda scene: (scene.get("score", 0), scene.get("order", 0)))
        kept = scenes[:]
        total_duration = sum(float(scene["duration_seconds"]) for scene in kept)
        for candidate in trimmed:
            if total_duration <= target_duration_seconds + 5.0 or len(kept) <= 1:
                break
            kept = [scene for scene in kept if scene is not candidate]
            total_duration = sum(float(scene["duration_seconds"]) for scene in kept)
        kept.sort(key=lambda scene: int(scene["order"]))
        for order, scene in enumerate(kept, start=1):
            scene["order"] = order
        return kept
