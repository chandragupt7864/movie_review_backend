from app.agents.cut_merge_agent.agent import CutMergeAgent
from app.agents.movie_discovery_agent.agent import MovieDiscoveryAgent
from app.agents.pipeline_watchdog_agent.agent import PipelineWatchdogAgent
from app.agents.review_reaction_agent.agent import ReviewReactionAgent
from app.agents.scene_selection_agent.agent import SceneSelectionAgent
from app.agents.shorts_composer_agent.agent import ShortsComposerAgent
from app.agents.thumbnail_metadata_agent.agent import ThumbnailMetadataAgent
from app.agents.trailer_finder_agent.agent import TrailerFinderAgent
from app.agents.video_downloader_agent.agent import VideoDownloaderAgent
from app.agents.voice_generator_agent.agent import VoiceGeneratorAgent
from app.config import settings
from app.repositories.movie_pipeline_repository import MoviePipelineRepository
from app.services.audio_metadata_service import AudioMetadataService
from app.services.elevenlabs_tts_service import ElevenLabsTTSService
from app.services.ffmpeg_render_service import FFmpegRenderService
from app.services.gemini_video_service import GeminiVideoService
from app.services.gemini_script_service import GeminiScriptService
from app.services.openai_script_service import OpenAIScriptService
from app.services.shorts_composer_service import ShortsComposerService
from app.services.supabase_storage_service import SupabaseStorageService
from app.services.thumbnail_asset_service import ThumbnailAssetService
from app.services.tmdb_service import TMDBService
from app.services.video_metadata_service import VideoMetadataService
from app.services.visual_scene_selection_service import VisualSceneSelectionService
from app.services.wikipedia_service import WikipediaService
from app.services.youtube_downloader_service import YoutubeDownloaderService
from app.services.python_thumbnail_generator_service import PythonThumbnailGeneratorService
from app.services.cloudinary_video_storage_service import CloudinaryVideoStorageService


def build_movie_discovery_agent() -> MovieDiscoveryAgent:
    return MovieDiscoveryAgent(
        tmdb_service=TMDBService(),
        repository=MoviePipelineRepository(),
    )


def build_trailer_finder_agent() -> TrailerFinderAgent:
    return TrailerFinderAgent(
        tmdb_service=TMDBService(),
        repository=MoviePipelineRepository(),
    )


def build_review_script_agent() -> ReviewReactionAgent:
    script_service = GeminiScriptService() if settings.script_provider == "gemini" else OpenAIScriptService()
    return ReviewReactionAgent(
        tmdb_service=TMDBService(),
        wikipedia_service=WikipediaService(),
        openai_script_service=script_service,
        repository=MoviePipelineRepository(),
    )


def build_voice_generator_agent() -> VoiceGeneratorAgent:
    return VoiceGeneratorAgent(
        tts_service=ElevenLabsTTSService(),
        repository=MoviePipelineRepository(),
        storage_service=SupabaseStorageService() if settings.upload_audio_to_supabase else None,
    )


def build_scene_selection_agent() -> SceneSelectionAgent:
    return SceneSelectionAgent(
        repository=MoviePipelineRepository(),
        audio_metadata_service=AudioMetadataService(),
        video_metadata_service=VideoMetadataService(),
        gemini_video_service=GeminiVideoService(),
        visual_scene_selection_service=VisualSceneSelectionService(),
    )


def build_video_downloader_agent() -> VideoDownloaderAgent:
    return VideoDownloaderAgent(
        repository=MoviePipelineRepository(),
        youtube_downloader_service=YoutubeDownloaderService(),
        video_metadata_service=VideoMetadataService(),
    )


def build_cut_merge_agent() -> CutMergeAgent:
    return CutMergeAgent(
        repository=MoviePipelineRepository(),
        cut_merge_service=FFmpegRenderService(),
    )


def build_shorts_composer_agent() -> ShortsComposerAgent:
    storage_service = None
    if settings.supabase_url and settings.supabase_service_role_key:
        storage_service = SupabaseStorageService()
    cloudinary_video_storage_service = None
    if settings.cloudinary_video_upload_enabled:
        cloudinary_video_storage_service = CloudinaryVideoStorageService()
    return ShortsComposerAgent(
        repository=MoviePipelineRepository(),
        shorts_composer_service=ShortsComposerService(storage_service=storage_service),
        cloudinary_video_storage_service=cloudinary_video_storage_service,
    )


def build_thumbnail_metadata_agent() -> ThumbnailMetadataAgent:
    storage_service = None
    if settings.supabase_url and settings.supabase_service_role_key:
        storage_service = SupabaseStorageService()
    return ThumbnailMetadataAgent(
        repository=MoviePipelineRepository(),
        asset_service=ThumbnailAssetService(),
        generator_service=PythonThumbnailGeneratorService(),
        storage_service=storage_service,
    )


def build_pipeline_watchdog_agent() -> PipelineWatchdogAgent:
    return PipelineWatchdogAgent(
        repository=MoviePipelineRepository(),
    )
