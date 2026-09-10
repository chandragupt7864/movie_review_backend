from collections.abc import Iterable


ALLOWED_VIDEO_TYPES = {"trailer", "teaser"}
_REJECTED_TITLE_MARKERS = {
    "american sign language",
    "animation teaser",
    "behind the scenes",
    " bts ",
    " clip",
    "featurette",
    "first look",
    "own now",
    " promo",
    "sneak peek",
    "#shorts",
    " short video",
    "tickets on sale",
    "tv spot",
    "vertical",
}
_ANNOUNCEMENT_MARKERS = {
    "trailer monday",
    "trailer tuesday",
    "trailer wednesday",
    "trailer thursday",
    "trailer friday",
    "trailer saturday",
    "trailer sunday",
    "trailer tomorrow",
}


def is_supported_trailer_video(video: object) -> bool:
    if not isinstance(video, dict):
        return False
    return (
        str(video.get("site") or "").strip().lower() == "youtube"
        and str(video.get("type") or "").strip().lower() in ALLOWED_VIDEO_TYPES
        and bool(str(video.get("key") or "").strip())
    )


def select_preferred_trailer_videos(videos: Iterable[object], max_results: int = 4) -> list[dict]:
    """Return a small, deterministic list of genuine trailer/teaser uploads."""
    candidates: list[tuple[int, int, dict]] = []
    seen_keys: set[str] = set()

    for position, video in enumerate(videos):
        if not is_supported_trailer_video(video):
            continue

        key = str(video.get("key") or "").strip()
        if key in seen_keys:
            continue
        seen_keys.add(key)

        title = str(video.get("name") or video.get("title") or "").strip().lower()
        padded_title = f" {title} "
        video_type = str(video.get("type") or "").strip().lower()
        if (
            video_type not in title
            or any(marker in padded_title for marker in _REJECTED_TITLE_MARKERS)
            or any(marker in title for marker in _ANNOUNCEMENT_MARKERS)
        ):
            continue

        official = video.get("official") is True
        priority = {
            ("trailer", True): 0,
            ("teaser", True): 1,
            ("trailer", False): 2,
            ("teaser", False): 3,
        }[(video_type, official)]
        candidates.append((priority, position, video))

    candidates.sort(key=lambda item: (item[0], item[1]))
    return [video for _, _, video in candidates[:max_results]]


def video_label(video: object) -> str:
    if not isinstance(video, dict):
        return "invalid item"
    return str(video.get("name") or video.get("title") or video.get("key") or "unknown")
