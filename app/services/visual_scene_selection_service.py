from __future__ import annotations

import re
from pathlib import Path

from app.config import PROJECT_ROOT, settings


ROLE_FLOW = ["hook", "story", "tension", "action", "emotion", "climax"]
KINETIC_GENRES = {"action", "adventure", "science fiction", "sci-fi"}
ACTION_CONTEXT_KEYWORDS = {
    "action",
    "assassin",
    "battle",
    "combat",
    "explosion",
    "fight",
    "martial",
    "superhero",
    "war",
    "warrior",
}


class VisualSceneSelectionService:
    def build_scene_plan(
        self,
        source_videos: list[dict],
        movie_context: dict,
        voice_duration_seconds: float,
        target_duration_seconds: float,
        extra_visual_seconds_after_voice: float,
    ) -> dict:
        candidates: list[dict] = []
        scene_min_duration = 4.0
        scene_max_duration = 5.0
        genre_focus = [str(item).strip() for item in (movie_context.get("genres") or []) if str(item).strip()]
        action_mode = self._is_action_mode(movie_context)

        for source_video in source_videos:
            video_path = self._resolve_local_path(str(source_video["source_video_path"]))
            metadata = self._video_metadata(str(video_path))
            detected_scenes = self._detect_scenes(str(video_path), threshold=float(settings.scene_detection_threshold))
            windows = self._build_candidate_windows(
                detected_scenes=detected_scenes,
                video_duration=metadata["duration_seconds"],
                min_duration=scene_min_duration,
                max_duration=scene_max_duration,
            )
            ranked = self._rank_windows(
                str(video_path),
                windows,
                metadata["duration_seconds"],
                action_mode=action_mode,
                metadata=metadata,
            )
            for candidate in ranked:
                trimmed = self._trim_candidate(candidate, metadata["duration_seconds"], scene_min_duration, scene_max_duration)
                if not trimmed:
                    continue
                candidates.append(
                    {
                        **trimmed,
                        "source_video_path": source_video["source_video_path"],
                        "source_video_label": source_video["label"],
                        "source_video_type": source_video.get("type", "trailer"),
                        "aspect_ratio": source_video.get("aspect_ratio", "16:9"),
                    }
                )

        if not candidates:
            raise ValueError("Visual fallback could not build any candidate scenes.")

        selected = self._select_fallback_scenes(
            candidates,
            target_duration_seconds,
            min_scene_duration=scene_min_duration,
            max_scene_duration=scene_max_duration,
            action_mode=action_mode,
        )
        if not selected:
            raise ValueError("Visual fallback could not produce any valid scenes.")

        source_videos_used = []
        used_paths = {scene["source_video_path"] for scene in selected}
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

        estimated_total_duration_seconds = round(sum(scene["duration_seconds"] for scene in selected), 3)
        return {
            "agent": "SCENE_SELECTION_AGENT",
            "video_format_for_next_agent": settings.scene_output_format,
            "master_resolution": settings.scene_master_resolution,
            "voice_duration_seconds": round(float(voice_duration_seconds), 3),
            "extra_visual_seconds_after_voice": round(float(extra_visual_seconds_after_voice), 3),
            "target_duration_seconds": round(float(target_duration_seconds), 3),
            "estimated_total_duration_seconds": estimated_total_duration_seconds,
            "editing_style": "visual fallback movie trailer flow",
            "source_video_rule": "Only horizontal 16:9 trailer/teaser/promo videos are used.",
            "source_videos_used": source_videos_used,
            "genre_focus": genre_focus,
            "action_mode": action_mode,
            "content_guards": {
                "intro_cards_excluded": True,
                "outro_cards_excluded": True,
                "animated_title_cards_excluded": True,
            },
            "scene_strategy": "hook -> adventure setup -> tension -> action spike -> action payoff -> climax" if action_mode else "hook -> story -> tension -> action -> emotion -> climax",
            "scenes": selected,
            "post_voice_visual_plan": {
                "enabled": True,
                "duration_seconds": round(float(extra_visual_seconds_after_voice), 3),
                "purpose": "Keep final cinematic visual after voice ends while background music fades out",
                "preferred_scene_type": "climax",
            },
            "render_notes": {
                "cut_merge_output": "Create clean 16:9 master video from original trailer/teaser scenes",
                "audio_note": "Voice audio starts from 0 seconds. Video should continue after voice ends.",
            },
            "warnings": [
                "Gemini unavailable or invalid. Used CinemaCut-style visual fallback selection.",
                "Adventure/action-biased fallback selection was applied." if action_mode else "Standard fallback selection was applied.",
            ],
        }

    @staticmethod
    def _resolve_local_path(video_path: str) -> Path:
        path = Path(video_path)
        if path.is_absolute():
            return path
        return PROJECT_ROOT / path

    @staticmethod
    def _video_metadata(video_path: str) -> dict:
        try:
            import cv2
        except ModuleNotFoundError as exc:
            raise ValueError("opencv-python-headless package is not installed. Run pip install -r requirements.txt.") from exc

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")
        try:
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            frame_count = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        finally:
            cap.release()
        duration_seconds = round(frame_count / fps, 3) if fps > 0 and frame_count > 0 else 0.0
        return {
            "fps": fps,
            "frame_count": frame_count,
            "width": width,
            "height": height,
            "duration_seconds": duration_seconds,
        }

    def _detect_scenes(self, video_path: str, threshold: float) -> list[dict]:
        metadata = self._video_metadata(video_path)
        duration = metadata["duration_seconds"]
        chunk_size = 5.0
        scenes = []
        start = 0.0
        scene_id = 1
        while start < duration:
            end = min(start + chunk_size, duration)
            scenes.append({"id": scene_id, "start": start, "end": end, "duration": round(end - start, 3)})
            start = end
            scene_id += 1
        return scenes

    @staticmethod
    def _build_candidate_windows(detected_scenes: list[dict], video_duration: float, min_duration: float, max_duration: float) -> list[dict]:
        windows = []
        window_id = 1
        step = max_duration
        for scene in detected_scenes:
            start = max(0.0, float(scene["start"]))
            end = min(video_duration, float(scene["end"]))
            duration = end - start
            if duration < min_duration:
                continue
            if duration <= max_duration:
                windows.append({"id": window_id, "start": round(start, 3), "end": round(end, 3), "duration": round(duration, 3)})
                window_id += 1
                continue
            cursor = start
            while cursor + min_duration <= end:
                window_end = min(cursor + max_duration, end)
                if window_end - cursor < min_duration:
                    break
                windows.append({"id": window_id, "start": round(cursor, 3), "end": round(window_end, 3), "duration": round(window_end - cursor, 3)})
                window_id += 1
                if window_end >= end:
                    break
                cursor += step
        return windows

    def _rank_windows(
        self,
        video_path: str,
        windows: list[dict],
        video_duration: float,
        action_mode: bool,
        metadata: dict,
    ) -> list[dict]:
        try:
            import cv2
        except ModuleNotFoundError as exc:
            raise ValueError("opencv-python-headless package is not installed. Run pip install -r requirements.txt.") from exc

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")

        ranked = []
        intro_guard = min(float(settings.scene_trailer_intro_skip_seconds), video_duration * 0.18)
        outro_guard = min(float(settings.scene_trailer_outro_skip_seconds), video_duration * 0.12)
        try:
            for window in windows:
                if float(window["start"]) <= intro_guard:
                    continue
                if float(window["start"]) >= video_duration - outro_guard:
                    continue
                midpoint = ((window["start"] + window["end"]) / 2.0) / max(video_duration, 1.0)
                duration_score = min(float(window["duration"]), 5.0)
                center_bias = 1.0 - abs(0.5 - midpoint)
                late_sequence_bonus = max(0.0, midpoint - 0.30) * (5.8 if action_mode else 2.5)
                action_curve_bonus = (
                    max(0.0, 1.0 - abs(0.70 - midpoint) * 2.2) * 4.8 if action_mode else 0.0
                )
                early_hook_bonus = max(0.0, 1.0 - abs(0.18 - midpoint) * 3.0) * (2.2 if action_mode else 0.0)
                window_metrics = self._analyze_window(
                    cap=cap,
                    fps=float(metadata.get("fps") or 0.0),
                    window=window,
                )
                if window_metrics["reject"]:
                    continue

                motion_bonus = window_metrics["motion_score"] * (11.0 if action_mode else 7.5)
                richness_bonus = window_metrics["richness_score"] * 4.0
                central_focus_bonus = window_metrics["center_focus_score"] * (2.0 if action_mode else 1.0)
                text_penalty = window_metrics["text_penalty"] * 8.0
                static_penalty = window_metrics["static_penalty"] * 10.0
                title_card_penalty = 7.0 if window_metrics["looks_like_title_card"] else 0.0

                activity_score = (
                    (duration_score * (1.55 if action_mode else 1.2))
                    + (center_bias * 3.0)
                    + late_sequence_bonus
                    + action_curve_bonus
                    + early_hook_bonus
                    + motion_bonus
                    + richness_bonus
                    + central_focus_bonus
                    - text_penalty
                    - static_penalty
                    - title_card_penalty
                )
                ranked.append(
                    {
                        **window,
                        "motion_score": round(window_metrics["motion_score"], 4),
                        "text_penalty": round(window_metrics["text_penalty"], 4),
                        "static_penalty": round(window_metrics["static_penalty"], 4),
                        "looks_like_title_card": window_metrics["looks_like_title_card"],
                        "timeline_position": midpoint,
                        "activity_score": round(activity_score, 4),
                    }
                )
        finally:
            cap.release()
        return ranked

    def _analyze_window(self, cap, fps: float, window: dict) -> dict:
        try:
            import cv2
            import numpy as np
        except ModuleNotFoundError as exc:
            raise ValueError("opencv-python-headless package is not installed. Run pip install -r requirements.txt.") from exc

        start_time = float(window["start"])
        end_time = float(window["end"])
        duration = max(end_time - start_time, 0.01)
        midpoint = start_time + (duration / 2.0)
        offset = min(0.6, max(0.2, duration * 0.18))
        timestamps = [
            max(start_time + 0.1, midpoint - offset),
            midpoint,
            min(end_time - 0.1, midpoint + offset),
        ]

        frames = []
        for timestamp in timestamps:
            if fps > 0:
                cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)
            success, frame = cap.read()
            if not success or frame is None:
                continue
            frames.append(frame)

        if len(frames) < 2:
            return {
                "reject": True,
                "motion_score": 0.0,
                "richness_score": 0.0,
                "center_focus_score": 0.0,
                "text_penalty": 1.0,
                "static_penalty": 1.0,
                "looks_like_title_card": True,
            }

        motion_values: list[float] = []
        text_values: list[float] = []
        richness_values: list[float] = []
        center_values: list[float] = []
        prev_gray = None

        for frame in frames:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape[:2]
            center = gray[int(h * 0.18): int(h * 0.82), int(w * 0.12): int(w * 0.88)]
            edges = cv2.Canny(gray, 80, 180)
            center_edges = cv2.Canny(center, 80, 180)

            edge_density = float(edges.mean()) / 255.0
            center_edge_density = float(center_edges.mean()) / 255.0

            center_small = cv2.resize(center, (max(1, center.shape[1] // 2), max(1, center.shape[0] // 2)))
            _, binary = cv2.threshold(center_small, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
            small_components = 0
            text_component_area = 0
            for idx in range(1, num_labels):
                x, y, cw, ch, area = stats[idx]
                if area < 6:
                    continue
                if cw <= binary.shape[1] * 0.42 and ch <= binary.shape[0] * 0.22:
                    small_components += 1
                    text_component_area += int(area)

            text_component_density = min(1.0, small_components / 45.0)
            text_area_ratio = min(1.0, text_component_area / max(center.size, 1))
            brightness_std = float(gray.std()) / 255.0
            center_std = float(center.std()) / 255.0

            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            saturation_mean = float(hsv[:, :, 1].mean()) / 255.0
            richness_score = min(1.0, (brightness_std * 0.7) + (saturation_mean * 0.3))
            center_focus_score = min(1.0, center_std + (center_edge_density * 0.5))

            text_penalty = min(
                1.0,
                (center_edge_density * 0.35)
                + (text_component_density * 0.45)
                + (text_area_ratio * 1.8)
                + (max(0.0, 0.14 - brightness_std) * 1.4),
            )

            text_values.append(text_penalty)
            richness_values.append(richness_score)
            center_values.append(center_focus_score)

            if prev_gray is not None:
                diff = cv2.absdiff(gray, prev_gray)
                motion = float(diff.mean()) / 255.0
                motion_values.append(motion)
            prev_gray = gray

        avg_motion = sum(motion_values) / max(len(motion_values), 1)
        avg_text = sum(text_values) / max(len(text_values), 1)
        avg_richness = sum(richness_values) / max(len(richness_values), 1)
        avg_center = sum(center_values) / max(len(center_values), 1)

        static_title_card = avg_text >= 0.52 and avg_motion <= 0.028
        animated_title_card = avg_text >= 0.44 and avg_center >= 0.20 and avg_richness <= 0.30
        looks_like_title_card = static_title_card or animated_title_card
        too_static = avg_motion <= 0.02 and avg_richness <= 0.18
        reject = looks_like_title_card or too_static

        static_penalty = min(1.0, max(0.0, 0.05 - avg_motion) * 14.0)
        motion_score = min(1.0, avg_motion / 0.09)

        return {
            "reject": reject,
            "motion_score": motion_score,
            "richness_score": avg_richness,
            "center_focus_score": avg_center,
            "text_penalty": avg_text,
            "static_penalty": static_penalty,
            "looks_like_title_card": looks_like_title_card,
        }

    @staticmethod
    def _is_action_mode(movie_context: dict) -> bool:
        genres = {str(item).strip().lower() for item in (movie_context.get("genres") or []) if str(item).strip()}
        if genres.intersection(KINETIC_GENRES):
            return True

        context_text = " ".join(
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
        tokens = set(re.findall(r"[a-z]+", context_text))
        return bool(tokens.intersection(ACTION_CONTEXT_KEYWORDS))

    @staticmethod
    def _trim_candidate(scene: dict, video_duration: float, min_duration: float, max_duration: float) -> dict | None:
        start = max(0.0, float(scene["start"]))
        end = min(float(scene["end"]), video_duration)
        if end <= start:
            return None
        duration = end - start
        center = start + duration / 2.0
        target_duration = min(max(duration, min_duration), max_duration)
        half = target_duration / 2.0
        start = max(0.0, center - half)
        end = min(video_duration, center + half)
        if end - start < min_duration:
            return None
        return {**scene, "start": round(start, 3), "end": round(end, 3), "duration": round(end - start, 3)}

    def _select_fallback_scenes(
        self,
        candidates: list[dict],
        target_duration_seconds: float,
        min_scene_duration: float,
        max_scene_duration: float,
        action_mode: bool,
    ) -> list[dict]:
        selected: list[dict] = []
        target_scene_count = max(6, min(14, int(round(target_duration_seconds / max(min_scene_duration, 0.1)))))
        if action_mode:
            strategies = [
                ("hook", lambda item: item["timeline_position"] <= 0.35),
                ("action", lambda item: 0.10 <= item["timeline_position"] <= 0.55),
                ("tension", lambda item: 0.25 <= item["timeline_position"] <= 0.72),
                ("action", lambda item: 0.40 <= item["timeline_position"] <= 0.88),
                ("action", lambda item: 0.50 <= item["timeline_position"] <= 0.97),
                ("climax", lambda item: item["timeline_position"] >= 0.65),
            ]
        else:
            strategies = [
                ("hook", lambda item: item["timeline_position"] <= 0.45),
                ("story", lambda item: 0.05 <= item["timeline_position"] <= 0.40),
                ("tension", lambda item: 0.25 <= item["timeline_position"] <= 0.65),
                ("action", lambda item: 0.35 <= item["timeline_position"] <= 0.85),
                ("emotion", lambda item: 0.45 <= item["timeline_position"] <= 0.90),
                ("climax", lambda item: item["timeline_position"] >= 0.55),
            ]

        for order, (role, predicate) in enumerate(strategies, start=1):
            scene = self._pick_best_candidate(candidates, selected, predicate, role, order)
            if scene:
                selected.append(scene)

        total_duration = sum(float(scene["duration_seconds"]) for scene in selected)
        for candidate in sorted(
            candidates,
            key=lambda item: (
                1 if item["source_video_path"] not in {scene["source_video_path"] for scene in selected} else 0,
                item.get("activity_score", 0.0),
                item["duration"],
            ),
            reverse=True,
        ):
            if len(selected) >= target_scene_count and total_duration >= target_duration_seconds - min_scene_duration:
                break
            if self._is_duplicate(candidate, selected) or self._overlaps(candidate, selected):
                continue
            missing_roles = [role for role in ROLE_FLOW if role not in {scene["scene_type"] for scene in selected}]
            if action_mode and len(selected) >= 2:
                role = "action" if len(selected) < target_scene_count - 1 else "climax"
            else:
                role = missing_roles[0] if missing_roles else ROLE_FLOW[min(len(selected), len(ROLE_FLOW) - 1)]
            new_scene = self._to_scene(candidate, role, len(selected) + 1)
            selected.append(new_scene)
            total_duration += float(new_scene["duration_seconds"])

        selected = sorted(
            selected,
            key=lambda item: (
                self._scene_role_priority(item["scene_type"], action_mode=action_mode),
                item["start"],
            ),
        )
        final_scenes = []
        total_duration = 0.0
        for index, scene in enumerate(selected, start=1):
            next_duration = float(scene["duration_seconds"])
            if (
                len(final_scenes) >= 6
                and total_duration + next_duration > target_duration_seconds + max_scene_duration
            ):
                break
            if len(final_scenes) >= target_scene_count and total_duration >= target_duration_seconds - min_scene_duration:
                break
            scene_copy = dict(scene)
            scene_copy["order"] = index
            total_duration += float(scene_copy["duration_seconds"])
            final_scenes.append(scene_copy)
        return final_scenes

    def _pick_best_candidate(self, candidates: list[dict], used_scenes: list[dict], predicate, role: str, order: int) -> dict | None:
        filtered = [
            candidate
            for candidate in candidates
            if predicate(candidate) and not self._is_duplicate(candidate, used_scenes) and not self._overlaps(candidate, used_scenes)
        ]
        if not filtered:
            return None
        source_use_counts: dict[str, int] = {}
        for scene in used_scenes:
            path = str(scene["source_video_path"])
            source_use_counts[path] = source_use_counts.get(path, 0) + 1
        best = max(
            filtered,
            key=lambda item: (
                -source_use_counts.get(str(item["source_video_path"]), 0),
                item.get("activity_score", 0.0),
                item["duration"],
            ),
        )
        return self._to_scene(best, role, order)

    @staticmethod
    def _to_scene(candidate: dict, role: str, order: int) -> dict:
        transition_after = "flash_cut" if role in {"hook", "action"} else "cut"
        zoom = "punch_zoom" if role in {"hook", "action"} else "none"
        speed = "1.10x" if role == "action" else "normal"
        visual_energy = "high" if candidate.get("activity_score", 0.0) >= 8 else "medium"
        return {
            "order": order,
            "source_video_label": candidate["source_video_label"],
            "source_video_path": candidate["source_video_path"],
            "start": VisualSceneSelectionService._seconds_to_timestamp(candidate["start"]),
            "end": VisualSceneSelectionService._seconds_to_timestamp(candidate["end"]),
            "duration_seconds": round(float(candidate["duration"]), 3),
            "scene_type": role,
            "mood": "hype" if role in {"hook", "action"} else "cinematic",
            "visual_energy": visual_energy,
            "transition_after": transition_after,
            "transition_duration_seconds": 0.12,
            "zoom": zoom,
            "speed": speed,
            "text_overlay_suggestion": role.title(),
            "reason": f"Visual fallback selected {role} scene using motion/activity ranking",
            "score": min(10, max(6, int(round(candidate.get("activity_score", 0.0))))),
        }

    @staticmethod
    def _scene_role_priority(role: str, action_mode: bool) -> int:
        if action_mode:
            action_order = {
                "hook": 0,
                "action": 1,
                "tension": 2,
                "story": 3,
                "emotion": 4,
                "climax": 5,
            }
            return action_order.get(role, 9)
        return ROLE_FLOW.index(role) if role in ROLE_FLOW else 9

    @staticmethod
    def _seconds_to_timestamp(value: float) -> str:
        total = max(0.0, float(value))
        hours = int(total // 3600)
        minutes = int((total % 3600) // 60)
        seconds = total % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"

    @staticmethod
    def _overlaps(scene: dict, kept_scenes: list[dict], tolerance: float = 0.05) -> bool:
        for kept in kept_scenes:
            if scene["source_video_path"] != kept["source_video_path"]:
                continue
            overlap = min(scene["end"], VisualSceneSelectionService._timestamp_or_float(kept["end"])) - max(
                scene["start"], VisualSceneSelectionService._timestamp_or_float(kept["start"])
            )
            if overlap > tolerance:
                return True
        return False

    @staticmethod
    def _is_duplicate(scene: dict, kept_scenes: list[dict]) -> bool:
        for kept in kept_scenes:
            if scene["source_video_path"] != kept["source_video_path"]:
                continue
            kept_start = VisualSceneSelectionService._timestamp_or_float(kept["start"])
            kept_end = VisualSceneSelectionService._timestamp_or_float(kept["end"])
            if abs(scene["start"] - kept_start) < 1.5 and abs(scene["end"] - kept_end) < 1.5:
                return True
        return False

    @staticmethod
    def _timestamp_or_float(value) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        parts = str(value).split(":")
        if len(parts) != 3:
            return 0.0
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
