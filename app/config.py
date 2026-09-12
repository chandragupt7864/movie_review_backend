import os
import shutil
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

load_dotenv(dotenv_path=ENV_PATH)


class Settings:
    def __init__(self) -> None:
        self.app_name = "Movie Review Agent System"
        self.tmdb_api_key = os.getenv("TMDB_API_KEY", "").strip()
        self.tmdb_bearer_token = os.getenv("TMDB_BEARER_TOKEN", "").strip()
        self.tmdb_region = os.getenv("TMDB_REGION", "US").strip() or "US"
        self.database_url = os.getenv("DATABASE_URL", "").strip()
        self.tmdb_ssl_verify = self._get_bool("TMDB_SSL_VERIFY", default=True)
        self.tmdb_ca_bundle = os.getenv("TMDB_CA_BUNDLE", "").strip()
        self.tmdb_use_env_proxy = self._get_bool("TMDB_USE_ENV_PROXY", default=True)
        self.tmdb_retry_count = self._get_int("TMDB_RETRY_COUNT", default=3)
        self.tmdb_timeout_seconds = self._get_int("TMDB_TIMEOUT_SECONDS", default=30)
        self.tmdb_force_ipv4 = self._get_bool("TMDB_FORCE_IPV4", default=False)
        self.tmdb_upcoming_start_date = os.getenv("TMDB_UPCOMING_START_DATE", "").strip()
        self.tmdb_upcoming_end_date = os.getenv("TMDB_UPCOMING_END_DATE", "").strip()
        self.tmdb_released_start_date = os.getenv("TMDB_RELEASED_START_DATE", "").strip()
        self.tmdb_released_end_date = os.getenv("TMDB_RELEASED_END_DATE", "").strip()
        self.tmdb_min_vote_average = self._get_float("TMDB_MIN_VOTE_AVERAGE", default=6.0)
        self.tmdb_min_vote_count = self._get_int("TMDB_MIN_VOTE_COUNT", default=50)
        self.tmdb_min_upcoming_popularity = self._get_float("TMDB_MIN_UPCOMING_POPULARITY", default=20.0)
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
        self.script_provider = self._get_choice("SCRIPT_PROVIDER", default="openai", allowed={"openai", "gemini"})
        self.internet_ssl_verify = self._get_bool("INTERNET_SSL_VERIFY", default=True)
        self.elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
        self.elevenlabs_voice_id = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
        self.elevenlabs_voice_name = os.getenv("ELEVENLABS_VOICE_NAME", "Alex").strip() or "Alex"
        self.elevenlabs_model_id = os.getenv("ELEVENLABS_MODEL_ID", "eleven_v3").strip() or "eleven_v3"
        self.elevenlabs_output_format = os.getenv("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128").strip() or "mp3_44100_128"
        self.audio_output_dir = os.getenv("AUDIO_OUTPUT_DIR", "storage/audio").strip() or "storage/audio"
        self.voice_require_approval = self._get_bool("VOICE_REQUIRE_APPROVAL", default=True)
        self.supabase_url = os.getenv("SUPABASE_URL", "").strip()
        self.supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        self.supabase_audio_bucket = os.getenv("SUPABASE_AUDIO_BUCKET", "movie-audio").strip() or "movie-audio"
        self.supabase_bgm_bucket = os.getenv("SUPABASE_BGM_BUCKET", "bgm-library").strip() or "bgm-library"
        self.upload_audio_to_supabase = self._get_bool("UPLOAD_AUDIO_TO_SUPABASE", default=True)
        self.supabase_audio_keep_last = self._get_int("SUPABASE_AUDIO_KEEP_LAST", default=20)
        self.audio_cleanup_enabled = self._get_bool("AUDIO_CLEANUP_ENABLED", default=True)
        self.delete_local_audio_after_upload = self._get_bool("DELETE_LOCAL_AUDIO_AFTER_UPLOAD", default=False)
        self.pipeline_auto_run = self._get_bool("PIPELINE_AUTO_RUN", default=True)
        self.worker_poll_interval_seconds = self._get_float("WORKER_POLL_INTERVAL_SECONDS", default=5.0)
        self.worker_batch_size = self._get_int("WORKER_BATCH_SIZE", default=1)
        self.watchdog_interval_seconds = self._get_float("WATCHDOG_INTERVAL_SECONDS", default=300.0)
        self.voice_mode = self._get_choice("VOICE_MODE", default="auto", allowed={"auto", "manual"})
        self.source_video_mode = self._get_choice("SOURCE_VIDEO_MODE", default="auto", allowed={"auto", "manual", "hybrid"})
        self.thumbnail_mode = self._get_choice("THUMBNAIL_MODE", default="manual", allowed={"auto", "manual"})
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
        self.gemini_ssl_verify = self._get_bool("GEMINI_SSL_VERIFY", default=True)
        self.gemini_generate_timeout_seconds = self._get_int("GEMINI_GENERATE_TIMEOUT_SECONDS", default=480)
        self.gemini_file_processing_timeout_seconds = self._get_int("GEMINI_FILE_PROCESSING_TIMEOUT_SECONDS", default=180)
        self.gemini_scene_max_videos = self._get_int("GEMINI_SCENE_MAX_VIDEOS", default=1)
        self.lyria_model = os.getenv("LYRIA_MODEL", "lyria-3.5").strip() or "lyria-3.5"
        self.lyria_timeout_seconds = self._get_int("LYRIA_TIMEOUT_SECONDS", default=300)
        self.lyria_output_dir = os.getenv("LYRIA_OUTPUT_DIR", "storage/bgm/generated").strip() or "storage/bgm/generated"
        self.video_source_dir = os.getenv("VIDEO_SOURCE_DIR", "storage/source_videos").strip() or "storage/source_videos"
        self.final_video_dir = (
            os.getenv("VIDEO_RENDER_DIR", "").strip()
            or os.getenv("FINAL_VIDEO_DIR", "storage/final_videos").strip()
            or "storage/final_videos"
        )
        self.temp_clip_dir = os.getenv("TEMP_CLIP_DIR", "storage/temp_clips").strip() or "storage/temp_clips"
        self.scene_extra_seconds_after_voice = self._get_float("SCENE_EXTRA_SECONDS_AFTER_VOICE", default=7.0)
        self.scene_extra_seconds_min = self._get_float("SCENE_EXTRA_SECONDS_MIN", default=5.0)
        self.scene_extra_seconds_max = self._get_float("SCENE_EXTRA_SECONDS_MAX", default=10.0)
        self.scene_selection_prefer_visual_fallback = self._get_bool("SCENE_SELECTION_PREFER_VISUAL_FALLBACK", default=False)
        self.scene_allow_visual_fallback_on_gemini_error = self._get_bool(
            "SCENE_ALLOW_VISUAL_FALLBACK_ON_GEMINI_ERROR",
            default=True,
        )
        self.scene_output_format = os.getenv("SCENE_OUTPUT_FORMAT", "16:9").strip() or "16:9"
        self.scene_master_resolution = os.getenv("SCENE_MASTER_RESOLUTION", "1920x1080").strip() or "1920x1080"
        self.scene_detection_threshold = self._get_float("SCENE_DETECTION_THRESHOLD", default=27.0)
        self.scene_trailer_intro_skip_seconds = self._get_float("SCENE_TRAILER_INTRO_SKIP_SECONDS", default=25.0)
        self.scene_trailer_outro_skip_seconds = self._get_float("SCENE_TRAILER_OUTRO_SKIP_SECONDS", default=15.0)
        self.master_video_resolution = os.getenv("MASTER_VIDEO_RESOLUTION", "1920x1080").strip() or "1920x1080"
        self.master_video_fps = self._get_int("MASTER_VIDEO_FPS", default=30)
        self.master_video_crf = self._get_int("MASTER_VIDEO_CRF", default=20)
        self.master_video_preset = os.getenv("MASTER_VIDEO_PRESET", "veryfast").strip() or "veryfast"
        self.cut_merge_target_fps = self._get_int("CUT_MERGE_TARGET_FPS", default=self.master_video_fps)
        self.render_keep_temp_clips = self._get_bool("RENDER_KEEP_TEMP_CLIPS", default=False)
        self.source_video_max_size_mb = self._get_int("SOURCE_VIDEO_MAX_SIZE_MB", default=500)
        self.source_video_min_aspect_ratio = self._get_float("SOURCE_VIDEO_MIN_ASPECT_RATIO", default=1.70)
        self.source_video_max_aspect_ratio = self._get_float("SOURCE_VIDEO_MAX_ASPECT_RATIO", default=1.85)
        self.download_trailer_automatically = self._get_bool("DOWNLOAD_TRAILER_AUTOMATICALLY", default=True)
        self.video_downloader_max_videos = self._get_int("VIDEO_DOWNLOADER_MAX_VIDEOS", default=3)
        self.video_downloader_max_attempts = self._get_int("VIDEO_DOWNLOADER_MAX_ATTEMPTS", default=3)
        self.yt_dlp_format = (
            os.getenv(
                "YT_DLP_FORMAT",
                "bestvideo[vcodec^=avc1][height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[vcodec^=avc1][height<=1080][ext=mp4]/bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]/best",
            ).strip()
            or "bestvideo[vcodec^=avc1][height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[vcodec^=avc1][height<=1080][ext=mp4]/bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]/best"
        )
        self.yt_dlp_retry_attempts = self._get_int("YT_DLP_RETRY_ATTEMPTS", default=3)
        self.yt_dlp_socket_timeout_seconds = self._get_int("YT_DLP_SOCKET_TIMEOUT_SECONDS", default=30)
        self.yt_dlp_cookie_file = os.getenv(
            "YT_DLP_COOKIE_FILE",
            "storage/private/youtube_cookies.txt",
        ).strip()
        self.yt_dlp_cookies_from_browser = os.getenv("YT_DLP_COOKIES_FROM_BROWSER", "").strip().lower()
        self.yt_dlp_player_clients = self._get_csv("YT_DLP_PLAYER_CLIENTS", default=["mweb"])
        self.yt_dlp_pot_provider_enabled = self._get_bool("YT_DLP_POT_PROVIDER_ENABLED", default=False)
        self.yt_dlp_pot_provider_server_dir = os.getenv(
            "YT_DLP_POT_PROVIDER_SERVER_DIR",
            "tools/bgutil-ytdlp-pot-provider/server",
        ).strip()
        self.yt_dlp_pot_provider_port = self._get_int("YT_DLP_POT_PROVIDER_PORT", default=4416)
        self.ffmpeg_binary = (
            os.getenv("FFMPEG_BINARY", "").strip()
            or os.getenv("FFMPEG_BINARY_PATH", "").strip()
            or shutil.which("ffmpeg")
            or ""
        )
        self.ffprobe_binary = os.getenv("FFPROBE_BINARY", "").strip() or shutil.which("ffprobe") or ""
        self.shorts_output_dir = os.getenv("SHORTS_OUTPUT_DIR", "storage/final_videos").strip() or "storage/final_videos"
        self.shorts_temp_dir = os.getenv("SHORTS_TEMP_DIR", "storage/temp_shorts").strip() or "storage/temp_shorts"
        self.shorts_width = self._get_int("SHORTS_WIDTH", default=1080)
        self.shorts_height = self._get_int("SHORTS_HEIGHT", default=1920)
        self.shorts_fps = self._get_int("SHORTS_FPS", default=30)
        self.shorts_foreground_width_no_crop = self._get_int("SHORTS_FOREGROUND_WIDTH_NO_CROP", default=1020)
        self.shorts_foreground_width_with_crop = self._get_int("SHORTS_FOREGROUND_WIDTH_WITH_CROP", default=1220)
        self.shorts_foreground_zoom_base = self._get_float("SHORTS_FOREGROUND_ZOOM_BASE", default=1.50)
        self.shorts_foreground_zoom_with_crop = self._get_float("SHORTS_FOREGROUND_ZOOM_WITH_CROP", default=1.70)
        self.shorts_foreground_y_offset = self._get_int("SHORTS_FOREGROUND_Y_OFFSET", default=0)
        self.shorts_foreground_x_center = self._get_bool("SHORTS_FOREGROUND_X_CENTER", default=True)
        self.shorts_foreground_y_center = self._get_bool("SHORTS_FOREGROUND_Y_CENTER", default=True)
        self.shorts_background_blur = self._get_int("SHORTS_BACKGROUND_BLUR", default=24)
        self.shorts_background_darkness = self._get_float("SHORTS_BACKGROUND_DARKNESS", default=-0.08)
        self.shorts_foreground_brightness = self._get_float("SHORTS_FOREGROUND_BRIGHTNESS", default=0.06)
        self.shorts_foreground_contrast = self._get_float("SHORTS_FOREGROUND_CONTRAST", default=1.08)
        self.shorts_foreground_saturation = self._get_float("SHORTS_FOREGROUND_SATURATION", default=1.08)
        self.shorts_background_contrast = self._get_float("SHORTS_BACKGROUND_CONTRAST", default=1.00)
        self.shorts_background_saturation = self._get_float("SHORTS_BACKGROUND_SATURATION", default=1.00)
        self.shorts_video_crf = self._get_int("SHORTS_VIDEO_CRF", default=20)
        self.shorts_video_preset = os.getenv("SHORTS_VIDEO_PRESET", "veryfast").strip() or "veryfast"
        self.bgm_enabled = self._get_bool("BGM_ENABLED", default=True)
        self.bgm_default_path = os.getenv("BGM_DEFAULT_PATH", "storage/bgm/default_bgm.mp3").strip() or "storage/bgm/default_bgm.mp3"
        self.bgm_volume = self._get_float("BGM_VOLUME", default=0.10)
        self.voice_volume = self._get_float("VOICE_VOLUME", default=1.0)
        self.bgm_fade_out_seconds = self._get_float("BGM_FADE_OUT_SECONDS", default=3.0)
        self.bgm_temp_dir = os.getenv("BGM_TEMP_DIR", "storage/temp/bgm").strip() or "storage/temp/bgm"
        self.bgm_max_file_size_mb = self._get_int("BGM_MAX_FILE_SIZE_MB", default=50)
        self.bgm_allowed_extensions = self._get_csv("BGM_ALLOWED_EXTENSIONS", default=["mp3", "wav", "m4a", "aac", "ogg", "flac"])
        self.fpcalc_binary = os.getenv("FPCALC_BINARY", "fpcalc").strip() or "fpcalc"
        self.music_recognition_provider = os.getenv("MUSIC_RECOGNITION_PROVIDER", "acoustid").strip().lower() or "acoustid"
        self.acoustid_api_key = os.getenv("ACOUSTID_API_KEY", "").strip()
        self.bgm_signed_url_expires_seconds = self._get_int("BGM_SIGNED_URL_EXPIRES_SECONDS", default=3600)
        self.bgm_audio_analysis_enabled = self._get_bool("BGM_AUDIO_ANALYSIS_ENABLED", default=True)
        self.bgm_fingerprint_enabled = self._get_bool("BGM_FINGERPRINT_ENABLED", default=True)
        self.bgm_recognition_enabled = self._get_bool("BGM_RECOGNITION_ENABLED", default=True)
        self.shorts_set_final_video_path = self._get_bool("SHORTS_SET_FINAL_VIDEO_PATH", default=True)
        self.cloudinary_cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
        self.cloudinary_api_key = os.getenv("CLOUDINARY_API_KEY", "").strip()
        self.cloudinary_api_secret = os.getenv("CLOUDINARY_API_SECRET", "").strip()
        self.cloudinary_video_folder = os.getenv("CLOUDINARY_VIDEO_FOLDER", "reelybee/final-videos").strip() or "reelybee/final-videos"
        self.cloudinary_bgm_folder = os.getenv("CLOUDINARY_BGM_FOLDER", "reelybee/music").strip() or "reelybee/music"
        self.cloudinary_thumbnail_folder = os.getenv("CLOUDINARY_THUMBNAIL_FOLDER", "reelybee/thumbnails").strip() or "reelybee/thumbnails"
        self.cloudinary_video_chunk_size_mb = self._get_int("CLOUDINARY_VIDEO_CHUNK_SIZE_MB", default=20)
        cloudinary_configured = bool(self.cloudinary_cloud_name and self.cloudinary_api_key and self.cloudinary_api_secret)
        self.cloudinary_video_upload_enabled = self._get_bool("UPLOAD_FINAL_VIDEO_TO_CLOUDINARY", default=cloudinary_configured)
        self.cloudinary_bgm_upload_enabled = self._get_bool("UPLOAD_BGM_TO_CLOUDINARY", default=cloudinary_configured)
        self.cloudinary_thumbnail_upload_enabled = self._get_bool("UPLOAD_THUMBNAIL_TO_CLOUDINARY", default=cloudinary_configured)
        self.cloudinary_video_upload_required = self._get_bool("CLOUDINARY_VIDEO_UPLOAD_REQUIRED", default=False)
        self.cloudinary_thumbnail_upload_required = self._get_bool("CLOUDINARY_THUMBNAIL_UPLOAD_REQUIRED", default=False)
        self.ffmpeg_binary_path = self.ffmpeg_binary
        self.thumbnail_output_dir = os.getenv("THUMBNAIL_OUTPUT_DIR", "storage/thumbnails").strip() or "storage/thumbnails"
        self.thumbnail_reference_dir = os.getenv("THUMBNAIL_REFERENCE_DIR", "storage/thumbnail_refs").strip() or "storage/thumbnail_refs"
        self.thumbnail_width = self._get_int("THUMBNAIL_WIDTH", default=1080)
        self.thumbnail_height = self._get_int("THUMBNAIL_HEIGHT", default=1920)
        self.thumbnail_upload_to_supabase = self._get_bool("THUMBNAIL_UPLOAD_TO_SUPABASE", default=True)
        self.supabase_thumbnail_bucket = os.getenv("SUPABASE_THUMBNAIL_BUCKET", "movie-thumbnails").strip() or "movie-thumbnails"
        self.poster_output_dir = os.getenv("POSTER_OUTPUT_DIR", "storage/posters").strip() or "storage/posters"
        self.poster_max_size_mb = self._get_int("POSTER_MAX_SIZE_MB", default=20)
        self.poster_allowed_content_types = os.getenv("POSTER_ALLOWED_CONTENT_TYPES", "image/jpeg,image/png,image/webp").strip() or "image/jpeg,image/png,image/webp"
        self.poster_download_timeout_seconds = self._get_int("POSTER_DOWNLOAD_TIMEOUT_SECONDS", default=30)

    @staticmethod
    def _get_bool(name: str, default: bool) -> bool:
        raw_value = os.getenv(name)
        if raw_value is None:
            return default
        return raw_value.strip().lower() not in {"0", "false", "no", "off"}

    @staticmethod
    def _get_int(name: str, default: int) -> int:
        raw_value = os.getenv(name)
        if raw_value is None:
            return default
        try:
            return int(raw_value.strip())
        except ValueError:
            return default

    @staticmethod
    def _get_float(name: str, default: float) -> float:
        raw_value = os.getenv(name)
        if raw_value is None:
            return default
        try:
            return float(raw_value.strip())
        except ValueError:
            return default

    @staticmethod
    def _get_choice(name: str, default: str, allowed: set[str]) -> str:
        raw_value = os.getenv(name)
        if raw_value is None:
            return default
        normalized = raw_value.strip().lower()
        if normalized in allowed:
            return normalized
        return default

    @staticmethod
    def _get_csv(name: str, default: list[str]) -> list[str]:
        raw_value = os.getenv(name)
        if raw_value is None:
            return list(default)
        values = [item.strip().lower().lstrip(".") for item in raw_value.split(",")]
        filtered = [item for item in values if item]
        return filtered or list(default)


settings = Settings()
