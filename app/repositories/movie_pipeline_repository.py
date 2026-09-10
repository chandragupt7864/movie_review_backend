import logging

from psycopg2.extras import Json

from app.database import get_db_cursor
from app.core.agent_status import (
    CURRENT_AGENT_CUT_MERGE,
    CURRENT_AGENT_REVIEW_REACTION,
    CURRENT_AGENT_SCENE_SELECTION,
    CURRENT_AGENT_SHORTS_COMPOSER,
    CURRENT_AGENT_POSTER_DOWNLOAD,
    CURRENT_AGENT_TRAILER,
    CURRENT_AGENT_VOICE_GENERATOR,
    CURRENT_AGENT_VIDEO_DOWNLOADER,
    NEXT_AGENT_CUT_MERGE,
    NEXT_AGENT_DONE,
    NEXT_AGENT_REVIEW_REACTION,
    NEXT_AGENT_SCENE_SELECTION,
    NEXT_AGENT_SHORTS_COMPOSER,
    NEXT_AGENT_THUMBNAIL_METADATA,
    NEXT_AGENT_TRAILER,
    NEXT_AGENT_VOICE_GENERATOR,
    NEXT_AGENT_VIDEO_DOWNLOADER,
    OVERALL_CUT_MERGE_FAILED,
    OVERALL_DRAFT_VIDEO_READY,
    OVERALL_FINAL_VIDEO_READY,
    OVERALL_MASTER_VIDEO_READY,
    OVERALL_RENDER_FAILED,
    OVERALL_RENDER_READY,
    OVERALL_SCENES_READY,
    OVERALL_SCENE_SELECTION_FAILED,
    OVERALL_SCRIPT_FAILED,
    OVERALL_SCRIPT_READY,
    OVERALL_SHORTS_COMPOSER_FAILED,
    OVERALL_TRAILER_FOUND,
    OVERALL_TRAILER_NOT_FOUND,
    OVERALL_VOICE_FAILED,
    OVERALL_VOICE_READY,
    OVERALL_WAITING_SOURCE_VIDEO,
    OVERALL_WAITING_VOICE_AUDIO,
    OVERALL_VIDEO_DOWNLOADED,
    OVERALL_VIDEO_DOWNLOAD_FAILED,
    POSTER_FAILED,
    POSTER_RUNNING,
    RENDER_COMPLETED,
    RENDER_FAILED,
    RENDER_PENDING,
    RENDER_RUNNING,
    REVIEW_COMPLETED,
    REVIEW_FAILED,
    REVIEW_PENDING,
    REVIEW_RUNNING,
    SCENE_COMPLETED,
    SCENE_FAILED,
    SCENE_PENDING,
    SCENE_RUNNING,
    SCENE_WAITING_SOURCE_VIDEO,
    SCENE_WAITING_VOICE_AUDIO,
    SHORTS_COMPLETED,
    SHORTS_FAILED,
    SHORTS_PENDING,
    SHORTS_RUNNING,
    SCRIPT_COMPLETED,
    SCRIPT_FAILED,
    SCRIPT_PENDING,
    SCRIPT_RUNNING,
    TRAILER_COMPLETED,
    TRAILER_FAILED,
    TRAILER_PENDING,
    TRAILER_RUNNING,
    VOICE_COMPLETED,
    VOICE_FAILED,
    VOICE_PENDING,
    VOICE_RUNNING,
    VIDEO_DOWNLOAD_PENDING,
    VIDEO_DOWNLOAD_RUNNING,
    VIDEO_DOWNLOAD_COMPLETED,
    VIDEO_DOWNLOAD_FAILED,
    CURRENT_AGENT_THUMBNAIL_METADATA,
    THUMBNAIL_RUNNING,
    THUMBNAIL_COMPLETED,
    THUMBNAIL_FAILED,
    THUMBNAIL_PENDING,
    OVERALL_THUMBNAIL_READY,
    OVERALL_THUMBNAIL_FAILED,
    OVERALL_WAITING_THUMBNAIL_UPLOAD,
    OVERALL_WAITING_VOICE_UPLOAD,
)


logger = logging.getLogger(__name__)


class MoviePipelineRepository:
    _runtime_indexes_checked = False
    _runtime_indexes_failed = False
    _source_videos_column_checked = False
    _master_video_path_column_checked = False
    _video_download_status_column_checked = False
    _shorts_columns_checked = False
    _thumbnail_columns_checked = False
    _poster_columns_checked = False
    _bgm_columns_checked = False

    def release_stale_locks(self) -> int:
        self.ensure_video_download_status_column()
        self.ensure_master_video_path_column()
        self.ensure_shorts_columns()
        self.ensure_thumbnail_columns()
        self.ensure_poster_columns()
        self.ensure_bgm_columns()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    trailer_status = CASE WHEN trailer_status = %s THEN %s ELSE trailer_status END,
                    review_status = CASE WHEN review_status = %s THEN %s ELSE review_status END,
                    script_status = CASE WHEN script_status = %s THEN %s ELSE script_status END,
                    voice_status = CASE WHEN voice_status = %s THEN %s ELSE voice_status END,
                    scene_status = CASE WHEN scene_status = %s THEN %s ELSE scene_status END,
                    video_download_status = CASE WHEN video_download_status = %s THEN %s ELSE video_download_status END,
                    render_status = CASE WHEN render_status = %s THEN %s ELSE render_status END,
                    shorts_status = CASE WHEN shorts_status = %s THEN %s ELSE shorts_status END,
                    thumbnail_status = CASE WHEN thumbnail_status = %s THEN %s ELSE thumbnail_status END,
                    poster_status = CASE WHEN poster_status = %s THEN %s ELSE poster_status END,
                    current_agent = NULL,
                    is_locked = FALSE,
                    locked_by = NULL,
                    locked_at = NULL,
                    updated_at = NOW()
                WHERE is_locked = TRUE
                   OR current_agent IS NOT NULL;
                """,
                (
                    TRAILER_RUNNING, TRAILER_FAILED,
                    REVIEW_RUNNING, REVIEW_FAILED,
                    SCRIPT_RUNNING, SCRIPT_FAILED,
                    VOICE_RUNNING, VOICE_FAILED,
                    SCENE_RUNNING, SCENE_FAILED,
                    VIDEO_DOWNLOAD_RUNNING, VIDEO_DOWNLOAD_FAILED,
                    RENDER_RUNNING, RENDER_FAILED,
                    SHORTS_RUNNING, SHORTS_FAILED,
                    THUMBNAIL_RUNNING, THUMBNAIL_FAILED,
                    POSTER_RUNNING, POSTER_FAILED,
                ),
            )
            return cursor.rowcount or 0

    def ensure_runtime_indexes(self) -> None:
        if self.__class__._runtime_indexes_checked or self.__class__._runtime_indexes_failed:
            return
        try:
            with get_db_cursor(commit=True) as cursor:
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_movie_pipeline_trailer_queue
                    ON movie_review_pipeline (next_agent, trailer_status, is_locked, is_active, priority, created_at);
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_movie_pipeline_voice_queue
                    ON movie_review_pipeline (next_agent, script_status, voice_status, is_locked, is_active, priority, created_at);
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_movie_pipeline_video_download_queue
                    ON movie_review_pipeline (next_agent, video_download_status, voice_status, is_locked, is_active, priority, created_at);
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_movie_pipeline_scene_queue
                    ON movie_review_pipeline (next_agent, scene_status, voice_status, is_locked, is_active, priority, created_at);
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_movie_pipeline_cut_merge_queue
                    ON movie_review_pipeline (next_agent, scene_status, render_status, is_locked, is_active, priority, created_at);
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_movie_pipeline_shorts_queue
                    ON movie_review_pipeline (next_agent, render_status, shorts_status, voice_status, is_locked, is_active, priority, created_at);
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_movie_pipeline_latest_movies
                    ON movie_review_pipeline (created_at DESC);
                    """
                )
            self.__class__._runtime_indexes_checked = True
        except Exception as exc:
            self.__class__._runtime_indexes_failed = True
            logger.warning("Skipping runtime index creation for this process because it failed: %s", exc)

    def ensure_source_videos_column(self) -> None:
        if self.__class__._source_videos_column_checked:
            return
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                ALTER TABLE movie_review_pipeline
                ADD COLUMN IF NOT EXISTS source_videos_json JSONB NOT NULL DEFAULT '[]'::jsonb;
                """
            )
        self.__class__._source_videos_column_checked = True
        self.ensure_video_download_status_column()

    def ensure_master_video_path_column(self) -> None:
        if self.__class__._master_video_path_column_checked:
            return
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                ALTER TABLE movie_review_pipeline
                ADD COLUMN IF NOT EXISTS master_video_path TEXT;
                """
            )
        self.__class__._master_video_path_column_checked = True
        self.ensure_shorts_columns()

    def ensure_video_download_status_column(self) -> None:
        if self.__class__._video_download_status_column_checked:
            return
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                ALTER TABLE movie_review_pipeline
                ADD COLUMN IF NOT EXISTS video_download_status VARCHAR(50) NOT NULL DEFAULT 'PENDING';
                """
            )
        self.__class__._video_download_status_column_checked = True

    def ensure_shorts_columns(self) -> None:
        if self.__class__._shorts_columns_checked:
            return
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                ALTER TABLE movie_review_pipeline
                ADD COLUMN IF NOT EXISTS shorts_status VARCHAR(50) NOT NULL DEFAULT 'PENDING';
                """
            )
            cursor.execute(
                """
                ALTER TABLE movie_review_pipeline
                ADD COLUMN IF NOT EXISTS shorts_data_json JSONB;
                """
            )
            cursor.execute(
                """
                ALTER TABLE movie_review_pipeline
                ADD COLUMN IF NOT EXISTS draft_video_path TEXT;
                """
            )
        self.__class__._shorts_columns_checked = True

    def ensure_bgm_columns(self) -> None:
        if self.__class__._bgm_columns_checked:
            return
        with get_db_cursor(commit=True) as cursor:
            cursor.execute("ALTER TABLE movie_review_pipeline ADD COLUMN IF NOT EXISTS bgm_status VARCHAR(50) NOT NULL DEFAULT 'PENDING';")
            cursor.execute("ALTER TABLE movie_review_pipeline ADD COLUMN IF NOT EXISTS bgm_audio_path TEXT;")
            cursor.execute("ALTER TABLE movie_review_pipeline ADD COLUMN IF NOT EXISTS bgm_data_json JSONB;")
        self.__class__._bgm_columns_checked = True

    def ensure_thumbnail_columns(self) -> None:
        if self.__class__._thumbnail_columns_checked:
            return
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                ALTER TABLE movie_review_pipeline
                ADD COLUMN IF NOT EXISTS thumbnail_status VARCHAR(50) NOT NULL DEFAULT 'PENDING';
                """
            )
            cursor.execute(
                """
                ALTER TABLE movie_review_pipeline
                ADD COLUMN IF NOT EXISTS thumbnail_path TEXT;
                """
            )
            cursor.execute(
                """
                ALTER TABLE movie_review_pipeline
                ADD COLUMN IF NOT EXISTS thumbnail_data_json JSONB;
                """
            )
            cursor.execute(
                """
                ALTER TABLE movie_review_pipeline
                ADD COLUMN IF NOT EXISTS youtube_title TEXT;
                """
            )
            cursor.execute(
                """
                ALTER TABLE movie_review_pipeline
                ADD COLUMN IF NOT EXISTS youtube_description TEXT;
                """
            )
            cursor.execute(
                """
                ALTER TABLE movie_review_pipeline
                ADD COLUMN IF NOT EXISTS youtube_tags_json JSONB;
                """
            )
            cursor.execute(
                """
                ALTER TABLE movie_review_pipeline
                ADD COLUMN IF NOT EXISTS youtube_keywords_json JSONB;
                """
            )
        self.__class__._thumbnail_columns_checked = True

    def ensure_poster_columns(self) -> None:
        if self.__class__._poster_columns_checked:
            return
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                ALTER TABLE movie_review_pipeline
                ADD COLUMN IF NOT EXISTS poster_status VARCHAR(50) NOT NULL DEFAULT 'PENDING';
                """
            )
            cursor.execute(
                """
                ALTER TABLE movie_review_pipeline
                ADD COLUMN IF NOT EXISTS poster_local_path TEXT;
                """
            )
            cursor.execute(
                """
                ALTER TABLE movie_review_pipeline
                ADD COLUMN IF NOT EXISTS backdrop_local_path TEXT;
                """
            )
            cursor.execute(
                """
                ALTER TABLE movie_review_pipeline
                ADD COLUMN IF NOT EXISTS poster_data_json JSONB;
                """
            )
            cursor.execute(
                """
                ALTER TABLE movie_review_pipeline
                ADD COLUMN IF NOT EXISTS poster_error TEXT;
                """
            )
        self.__class__._poster_columns_checked = True

    def get_pending_voice_jobs(self, limit: int, require_approval: bool) -> list[dict]:
        self.ensure_runtime_indexes()
        approval_filter = "AND is_approved_for_processing = TRUE" if require_approval else ""
        with get_db_cursor() as cursor:
            cursor.execute(
                f"""
                SELECT *
                FROM movie_review_pipeline
                WHERE is_active = TRUE
                  AND is_locked = FALSE
                  AND next_agent = %s
                  AND script_status = %s
                  AND voice_status = %s
                  AND final_script IS NOT NULL
                  {approval_filter}
                ORDER BY priority ASC, created_at ASC
                LIMIT %s;
                """,
                (NEXT_AGENT_VOICE_GENERATOR, SCRIPT_COMPLETED, VOICE_PENDING, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_pending_review_script_jobs(self, limit: int) -> list[dict]:
        self.ensure_runtime_indexes()
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM movie_review_pipeline
                WHERE is_active = TRUE
                  AND is_locked = FALSE
                  AND next_agent = %s
                  AND trailer_status = %s
                  AND review_status = %s
                  AND script_status = %s
                ORDER BY priority ASC, created_at ASC
                LIMIT %s;
                """,
                (NEXT_AGENT_REVIEW_REACTION, TRAILER_COMPLETED, REVIEW_PENDING, SCRIPT_PENDING, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_pending_trailer_jobs(self, limit: int) -> list[dict]:
        self.ensure_runtime_indexes()
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM movie_review_pipeline
                WHERE is_active = TRUE
                  AND is_locked = FALSE
                  AND next_agent = %s
                  AND trailer_status = %s
                ORDER BY priority ASC, created_at ASC
                LIMIT %s;
                """,
                (NEXT_AGENT_TRAILER, TRAILER_PENDING, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_manual_controller_candidates(self, limit: int) -> list[dict]:
        self.ensure_source_videos_column()
        self.ensure_master_video_path_column()
        self.ensure_shorts_columns()
        self.ensure_thumbnail_columns()
        self.ensure_poster_columns()
        self.ensure_runtime_indexes()
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM movie_review_pipeline
                WHERE is_active = TRUE
                  AND COALESCE(next_agent, '') <> ''
                  AND next_agent <> %s
                ORDER BY priority ASC, created_at ASC
                LIMIT %s;
                """,
                (NEXT_AGENT_DONE, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_pending_scene_jobs(self, limit: int) -> list[dict]:
        self.ensure_source_videos_column()
        self.ensure_runtime_indexes()
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM movie_review_pipeline
                WHERE is_active = TRUE
                  AND is_locked = FALSE
                  AND next_agent = %s
                  AND voice_status = %s
                  AND voice_audio_path IS NOT NULL
                  AND scene_status IN (%s, %s, %s, %s)
                  AND (
                        source_video_path IS NOT NULL
                        OR jsonb_array_length(COALESCE(source_videos_json, '[]'::jsonb)) > 0
                  )
                ORDER BY priority ASC, created_at ASC
                LIMIT %s;
                """,
                (
                    NEXT_AGENT_SCENE_SELECTION,
                    VOICE_COMPLETED,
                    SCENE_PENDING,
                    SCENE_FAILED,
                    SCENE_WAITING_SOURCE_VIDEO,
                    SCENE_WAITING_VOICE_AUDIO,
                    limit,
                ),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_pending_shorts_composer_jobs(self, limit: int) -> list[dict]:
        self.ensure_master_video_path_column()
        self.ensure_shorts_columns()
        self.ensure_runtime_indexes()
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM movie_review_pipeline
                WHERE is_active = TRUE
                  AND is_locked = FALSE
                  AND next_agent = %s
                  AND render_status = %s
                  AND master_video_path IS NOT NULL
                  AND voice_status = %s
                  AND voice_audio_path IS NOT NULL
                  AND shorts_status IN (%s, %s)
                ORDER BY priority ASC, created_at ASC
                LIMIT %s;
                """,
                (
                    NEXT_AGENT_SHORTS_COMPOSER,
                    RENDER_COMPLETED,
                    VOICE_COMPLETED,
                    SHORTS_PENDING,
                    SHORTS_FAILED,
                    limit,
                ),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_pending_thumbnail_jobs(self, limit: int) -> list[dict]:
        self.ensure_thumbnail_columns()
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM movie_review_pipeline
                WHERE is_active = TRUE
                  AND is_locked = FALSE
                  AND next_agent = %s
                  AND shorts_status = %s
                  AND draft_video_path IS NOT NULL
                  AND thumbnail_status = %s
                ORDER BY priority ASC, created_at ASC
                LIMIT %s;
                """,
                (NEXT_AGENT_THUMBNAIL_METADATA, SHORTS_COMPLETED, THUMBNAIL_PENDING, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def lock_movie_for_agent(self, movie_id: int, agent_name: str = CURRENT_AGENT_TRAILER) -> dict | None:
        self.ensure_video_download_status_column()
        self.ensure_master_video_path_column()
        self.ensure_shorts_columns()
        self.ensure_thumbnail_columns()
        self.ensure_poster_columns()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    is_locked = TRUE,
                    locked_by = %s,
                    locked_at = NOW(),
                    current_agent = %s,
                    trailer_status = CASE WHEN %s = %s THEN %s ELSE trailer_status END,
                    review_status = CASE WHEN %s = %s THEN %s ELSE review_status END,
                    script_status = CASE WHEN %s = %s THEN %s ELSE script_status END,
                    voice_status = CASE WHEN %s = %s THEN %s ELSE voice_status END,
                    scene_status = CASE WHEN %s = %s THEN %s ELSE scene_status END,
                    video_download_status = CASE WHEN %s = %s THEN %s ELSE video_download_status END,
                    render_status = CASE WHEN %s = %s THEN %s ELSE render_status END,
                    shorts_status = CASE WHEN %s = %s THEN %s ELSE shorts_status END,
                    thumbnail_status = CASE WHEN %s = %s THEN %s ELSE thumbnail_status END,
                    poster_status = CASE WHEN %s = %s THEN %s ELSE poster_status END,
                    updated_at = NOW()
                WHERE id = %s
                  AND is_active = TRUE
                  AND is_locked = FALSE
                RETURNING *;
                """,
                (
                    agent_name,
                    agent_name,
                    agent_name,
                    CURRENT_AGENT_TRAILER,
                    TRAILER_RUNNING,
                    agent_name,
                    CURRENT_AGENT_REVIEW_REACTION,
                    REVIEW_RUNNING,
                    agent_name,
                    CURRENT_AGENT_REVIEW_REACTION,
                    SCRIPT_RUNNING,
                    agent_name,
                    CURRENT_AGENT_VOICE_GENERATOR,
                    VOICE_RUNNING,
                    agent_name,
                    CURRENT_AGENT_SCENE_SELECTION,
                    SCENE_RUNNING,
                    agent_name,
                    CURRENT_AGENT_VIDEO_DOWNLOADER,
                    VIDEO_DOWNLOAD_RUNNING,
                    agent_name,
                    CURRENT_AGENT_CUT_MERGE,
                    RENDER_RUNNING,
                    agent_name,
                    CURRENT_AGENT_SHORTS_COMPOSER,
                    SHORTS_RUNNING,
                    agent_name,
                    CURRENT_AGENT_THUMBNAIL_METADATA,
                    THUMBNAIL_RUNNING,
                    agent_name,
                    CURRENT_AGENT_POSTER_DOWNLOAD,
                    POSTER_RUNNING,
                    movie_id,
                ),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def upsert_movie(self, payload: dict) -> str:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                INSERT INTO movie_review_pipeline (
                    job_code,
                    overall_status,
                    current_agent,
                    next_agent,
                    progress_percent,
                    tmdb_id,
                    imdb_id,
                    movie_title,
                    release_date,
                    language_code,
                    region_code,
                    poster_url,
                    backdrop_url,
                    discovery_category,
                    target_genres_json,
                    discovery_status,
                    movie_data_json,
                    process_timeline_json,
                    is_active,
                    updated_at
                )
                VALUES (
                    %(job_code)s,
                    %(overall_status)s,
                    %(current_agent)s,
                    %(next_agent)s,
                    %(progress_percent)s,
                    %(tmdb_id)s,
                    %(imdb_id)s,
                    %(movie_title)s,
                    %(release_date)s,
                    %(language_code)s,
                    %(region_code)s,
                    %(poster_url)s,
                    %(backdrop_url)s,
                    %(discovery_category)s,
                    %(target_genres_json)s,
                    %(discovery_status)s,
                    %(movie_data_json)s,
                    %(process_timeline_json)s,
                    TRUE,
                    NOW()
                )
                ON CONFLICT (tmdb_id)
                DO UPDATE SET
                    imdb_id = EXCLUDED.imdb_id,
                    movie_title = EXCLUDED.movie_title,
                    release_date = EXCLUDED.release_date,
                    language_code = EXCLUDED.language_code,
                    region_code = EXCLUDED.region_code,
                    poster_url = EXCLUDED.poster_url,
                    backdrop_url = EXCLUDED.backdrop_url,
                    discovery_category = EXCLUDED.discovery_category,
                    target_genres_json = EXCLUDED.target_genres_json,
                    discovery_status = EXCLUDED.discovery_status,
                    movie_data_json = EXCLUDED.movie_data_json,
                    updated_at = NOW()
                RETURNING (xmax = 0) AS inserted;
                """,
                payload,
            )
            result = cursor.fetchone()
            return "inserted" if result["inserted"] else "updated"


    def list_latest_movies(self, limit: int) -> list[dict]:
        self.ensure_runtime_indexes()
        self.ensure_source_videos_column()
        self.ensure_master_video_path_column()
        self.ensure_shorts_columns()
        self.ensure_thumbnail_columns()
        self.ensure_poster_columns()
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    job_code,
                    movie_title,
                    tmdb_id,
                    release_date,
                    discovery_category,
                    target_genres_json,
                    poster_url,
                    backdrop_url,
                    trailer_status,
                    trailer_youtube_id,
                    trailer_url,
                    trailer_title,
                    trailer_type,
                    trailer_official,
                    voice_status,
                    voice_audio_path,
                    voice_data_json,
                    video_download_status,
                    source_video_path,
                    source_videos_json,
                    scene_status,
                    scene_data_json,
                    render_status,
                    render_data_json,
                    shorts_status,
                    shorts_data_json,
                    master_video_path,
                    draft_video_path,
                    final_video_path,
                    thumbnail_status,
                    thumbnail_path,
                    thumbnail_data_json,
                    youtube_title,
                    youtube_description,
                    youtube_tags_json,
                    youtube_keywords_json,
                    poster_status,
                    poster_local_path,
                    backdrop_local_path,
                    poster_data_json,
                    poster_error,
                    overall_status,
                    current_agent,
                    next_agent,
                    progress_percent,
                    discovery_status,
                    review_status,
                    script_status,
                    process_timeline_json,
                    is_active,
                    is_locked,
                    created_at,
                    updated_at
                FROM movie_review_pipeline
                ORDER BY
                    CASE
                        WHEN is_locked = TRUE OR current_agent IS NOT NULL THEN 0
                        ELSE 1
                    END,
                    created_at DESC
                LIMIT %s;
                """,
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def list_movies_by_discovery_category(self, category: str, limit: int) -> list[dict]:
        self.ensure_source_videos_column()
        self.ensure_master_video_path_column()
        self.ensure_shorts_columns()
        self.ensure_thumbnail_columns()
        self.ensure_poster_columns()
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM movie_review_pipeline
                WHERE discovery_category = %s
                ORDER BY created_at DESC
                LIMIT %s;
                """,
                (category, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_movie_by_id(self, movie_id: int) -> dict | None:
        self.ensure_source_videos_column()
        self.ensure_master_video_path_column()
        self.ensure_shorts_columns()
        self.ensure_thumbnail_columns()
        self.ensure_poster_columns()
        self.ensure_bgm_columns()
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM movie_review_pipeline
                WHERE id = %s;
                """,
                (movie_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_bgm_generation(self, movie_id: int, status: str, bgm_audio_path: str | None = None, bgm_data: dict | None = None, error: str | None = None) -> None:
        self.ensure_bgm_columns()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET bgm_status = %(status)s,
                    bgm_audio_path = CASE WHEN %(audio_path)s IS NOT NULL THEN %(audio_path)s ELSE bgm_audio_path END,
                    bgm_data_json = CASE WHEN %(bgm_data)s IS NOT NULL THEN %(bgm_data)s ELSE bgm_data_json END,
                    shorts_status = CASE WHEN %(has_audio)s THEN 'PENDING' ELSE shorts_status END,
                    next_agent = CASE WHEN %(has_audio)s THEN 'SHORTS_COMPOSER_AGENT' ELSE next_agent END,
                    overall_status = CASE WHEN %(has_audio)s THEN 'BGM_READY' ELSE overall_status END,
                    last_error_agent = CASE
                        WHEN %(error)s IS NOT NULL THEN 'BGM_GENERATOR'
                        WHEN %(has_audio)s AND last_error_agent = 'BGM_GENERATOR' THEN NULL
                        ELSE last_error_agent
                    END,
                    last_error_message = CASE
                        WHEN %(error)s IS NOT NULL THEN %(error)s
                        WHEN %(has_audio)s AND last_error_agent = 'BGM_GENERATOR' THEN NULL
                        ELSE last_error_message
                    END,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    "status": status,
                    "audio_path": bgm_audio_path,
                    "bgm_data": Json(bgm_data) if bgm_data is not None else None,
                    "has_audio": bool(bgm_audio_path),
                    "error": error,
                    "movie_id": movie_id,
                },
            )

    def get_movie_by_tmdb_id(self, tmdb_id: int) -> dict | None:
        self.ensure_source_videos_column()
        self.ensure_master_video_path_column()
        self.ensure_shorts_columns()
        self.ensure_thumbnail_columns()
        self.ensure_poster_columns()
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM movie_review_pipeline
                WHERE tmdb_id = %s
                LIMIT 1;
                """,
                (tmdb_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def delete_movie(self, movie_id: int) -> bool:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                DELETE FROM movie_review_pipeline
                WHERE id = %s;
                """,
                (movie_id,),
            )
            return bool(cursor.rowcount)

    def get_existing_tmdb_ids(self, tmdb_ids: list[int]) -> set[int]:
        if not tmdb_ids:
            return set()
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT tmdb_id
                FROM movie_review_pipeline
                WHERE tmdb_id = ANY(%s);
                """,
                (tmdb_ids,),
            )
            return {int(row["tmdb_id"]) for row in cursor.fetchall() if row.get("tmdb_id") is not None}

    def get_existing_tmdb_ids_by_discovery_category(self, tmdb_ids: list[int], category: str) -> set[int]:
        if not tmdb_ids:
            return set()
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT tmdb_id
                FROM movie_review_pipeline
                WHERE tmdb_id = ANY(%s)
                  AND discovery_category = %s;
                """,
                (tmdb_ids, category),
            )
            return {int(row["tmdb_id"]) for row in cursor.fetchall() if row.get("tmdb_id") is not None}

    def update_trailer_success(self, movie_id: int, trailer_payload: dict) -> None:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    trailer_status = %(status)s,
                    trailer_youtube_id = %(youtube_id)s,
                    trailer_url = %(url)s,
                    trailer_title = %(title)s,
                    trailer_type = %(type)s,
                    trailer_official = %(official)s,
                    trailer_data_json = %(trailer_data_json)s,
                    overall_status = %(overall_status)s,
                    current_agent = NULL,
                    next_agent = %(next_agent)s,
                    progress_percent = 20,
                    is_locked = FALSE,
                    locked_by = NULL,
                    locked_at = NULL,
                    last_error_agent = NULL,
                    last_error_message = NULL,
                    error_data_json = NULL,
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    **trailer_payload,
                    "movie_id": movie_id,
                    "trailer_data_json": Json(trailer_payload["trailer_data"]),
                    "timeline_event": Json([trailer_payload["timeline_event"]]),
                    "status": TRAILER_COMPLETED,
                    "overall_status": OVERALL_TRAILER_FOUND,
                    "next_agent": NEXT_AGENT_REVIEW_REACTION,
                },
            )

    def update_trailer_failed(self, movie_id: int, error_payload: dict) -> None:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    trailer_status = %(status)s,
                    overall_status = CASE
                        WHEN %(not_found)s THEN %(overall_not_found)s
                        ELSE overall_status
                    END,
                    last_error_agent = %(agent)s,
                    last_error_message = %(error_message)s,
                    error_data_json = %(error_data_json)s,
                    current_agent = NULL,
                    next_agent = %(next_agent)s,
                    is_locked = FALSE,
                    locked_by = NULL,
                    locked_at = NULL,
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    **error_payload,
                    "movie_id": movie_id,
                    "status": TRAILER_FAILED,
                    "overall_not_found": OVERALL_TRAILER_NOT_FOUND,
                    "agent": CURRENT_AGENT_TRAILER,
                    "next_agent": NEXT_AGENT_TRAILER,
                    "error_data_json": Json(error_payload["error_data"]),
                    "timeline_event": Json([error_payload["timeline_event"]]),
                },
            )

    def update_review_script_success(self, movie_id: int, review_payload: dict, script_payload: dict) -> None:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    review_status = %(review_status)s,
                    script_status = %(script_status)s,
                    review_data_json = %(review_data_json)s,
                    script_data_json = %(script_data_json)s,
                    final_script = %(final_script)s,
                    overall_status = %(overall_status)s,
                    current_agent = NULL,
                    next_agent = %(next_agent)s,
                    progress_percent = 35,
                    is_locked = FALSE,
                    locked_by = NULL,
                    locked_at = NULL,
                    last_error_agent = NULL,
                    last_error_message = NULL,
                    error_data_json = NULL,
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    "movie_id": movie_id,
                    "review_status": REVIEW_COMPLETED,
                    "script_status": SCRIPT_COMPLETED,
                    "review_data_json": Json(review_payload["review_data"]),
                    "script_data_json": Json(script_payload["script_data"]),
                    "final_script": script_payload["script_data"]["script"],
                    "overall_status": script_payload.get("overall_status", OVERALL_SCRIPT_READY),
                    "next_agent": script_payload.get("next_agent", NEXT_AGENT_VOICE_GENERATOR),
                    "timeline_event": Json([script_payload["timeline_event"]]),
                },
            )

    def update_review_script_failed(self, movie_id: int, error_payload: dict) -> None:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    review_status = %(review_status)s,
                    script_status = %(script_status)s,
                    review_data_json = COALESCE(%(review_data_json)s::jsonb, review_data_json),
                    overall_status = %(overall_status)s,
                    last_error_agent = %(agent)s,
                    last_error_message = %(error_message)s,
                    error_data_json = %(error_data_json)s,
                    current_agent = NULL,
                    next_agent = %(next_agent)s,
                    is_locked = FALSE,
                    locked_by = NULL,
                    locked_at = NULL,
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    **error_payload,
                    "movie_id": movie_id,
                    "review_status": REVIEW_FAILED if error_payload.get("stage") == "research" else REVIEW_COMPLETED,
                    "script_status": SCRIPT_FAILED,
                    "review_data_json": Json(error_payload["review_data"]) if error_payload.get("review_data") else None,
                    "overall_status": OVERALL_SCRIPT_FAILED,
                    "agent": CURRENT_AGENT_REVIEW_REACTION,
                    "next_agent": NEXT_AGENT_REVIEW_REACTION,
                    "error_data_json": Json(error_payload["error_data"]),
                    "timeline_event": Json([error_payload["timeline_event"]]),
                },
            )

    def update_voice_success(self, movie_id: int, voice_payload: dict) -> None:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    voice_status = %(voice_status)s,
                    voice_audio_path = %(audio_path)s,
                    voice_data_json = %(voice_data_json)s,
                    overall_status = %(overall_status)s,
                    current_agent = NULL,
                    next_agent = %(next_agent)s,
                    progress_percent = 50,
                    is_locked = FALSE,
                    locked_by = NULL,
                    locked_at = NULL,
                    last_error_agent = NULL,
                    last_error_message = NULL,
                    error_data_json = NULL,
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    "movie_id": movie_id,
                    "voice_status": VOICE_COMPLETED,
                    "audio_path": voice_payload["audio_path"],
                    "voice_data_json": Json(voice_payload["voice_data"]),
                    "overall_status": voice_payload.get("overall_status", OVERALL_VOICE_READY),
                    "next_agent": voice_payload.get("next_agent", NEXT_AGENT_VIDEO_DOWNLOADER),
                    "timeline_event": Json([voice_payload["timeline_event"]]),
                },
            )

    def update_voice_failed(self, movie_id: int, error_payload: dict) -> None:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    voice_status = %(voice_status)s,
                    overall_status = %(overall_status)s,
                    last_error_agent = %(agent)s,
                    last_error_message = %(error_message)s,
                    error_data_json = %(error_data_json)s,
                    current_agent = NULL,
                    next_agent = %(next_agent)s,
                    is_locked = FALSE,
                    locked_by = NULL,
                    locked_at = NULL,
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    **error_payload,
                    "movie_id": movie_id,
                    "voice_status": VOICE_FAILED,
                    "overall_status": OVERALL_VOICE_FAILED,
                    "agent": CURRENT_AGENT_VOICE_GENERATOR,
                    "next_agent": NEXT_AGENT_VOICE_GENERATOR,
                    "error_data_json": Json(error_payload["error_data"]),
                    "timeline_event": Json([error_payload["timeline_event"]]),
                },
            )

    def update_scene_success(self, movie_id: int, scene_payload: dict) -> None:
        self.ensure_source_videos_column()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    scene_status = %(scene_status)s,
                    scene_data_json = %(scene_data_json)s,
                    overall_status = %(overall_status)s,
                    current_agent = NULL,
                    next_agent = %(next_agent)s,
                    progress_percent = 65,
                    is_locked = FALSE,
                    locked_by = NULL,
                    locked_at = NULL,
                    last_error_agent = NULL,
                    last_error_message = NULL,
                    error_data_json = NULL,
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    "movie_id": movie_id,
                    "scene_status": SCENE_COMPLETED,
                    "scene_data_json": Json(scene_payload["scene_data"]),
                    "overall_status": OVERALL_SCENES_READY,
                    "next_agent": NEXT_AGENT_CUT_MERGE,
                    "timeline_event": Json([scene_payload["timeline_event"]]),
                },
            )

    def update_scene_failed(self, movie_id: int, error_payload: dict) -> None:
        self.ensure_source_videos_column()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    scene_status = %(scene_status)s,
                    overall_status = %(overall_status)s,
                    last_error_agent = %(agent)s,
                    last_error_message = %(error_message)s,
                    error_data_json = %(error_data_json)s,
                    current_agent = NULL,
                    next_agent = %(next_agent)s,
                    is_locked = FALSE,
                    locked_by = NULL,
                    locked_at = NULL,
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    **error_payload,
                    "movie_id": movie_id,
                    "scene_status": SCENE_FAILED,
                    "overall_status": OVERALL_SCENE_SELECTION_FAILED,
                    "agent": CURRENT_AGENT_SCENE_SELECTION,
                    "next_agent": NEXT_AGENT_SCENE_SELECTION,
                    "error_data_json": Json(error_payload["error_data"]),
                    "timeline_event": Json([error_payload["timeline_event"]]),
                },
            )

    def update_scene_waiting_source_video(self, movie_id: int, error_payload: dict) -> None:
        self._update_scene_waiting(
            movie_id=movie_id,
            scene_status=SCENE_WAITING_SOURCE_VIDEO,
            overall_status=OVERALL_WAITING_SOURCE_VIDEO,
            error_payload=error_payload,
        )

    def update_scene_waiting_voice_audio(self, movie_id: int, error_payload: dict) -> None:
        self._update_scene_waiting(
            movie_id=movie_id,
            scene_status=SCENE_WAITING_VOICE_AUDIO,
            overall_status=OVERALL_WAITING_VOICE_AUDIO,
            error_payload=error_payload,
        )

    def add_source_video(self, movie_id: int, source_video_payload: dict) -> dict | None:
        self.ensure_source_videos_column()
        self.ensure_video_download_status_column()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    video_download_status = %(video_download_status)s,
                    source_video_path = COALESCE(source_video_path, %(source_video_path)s),
                    source_videos_json = COALESCE(source_videos_json, '[]'::jsonb) || %(source_videos_json)s::jsonb,
                    overall_status = CASE
                        WHEN voice_status = %(voice_status)s THEN %(overall_status)s
                        ELSE overall_status
                    END,
                    next_agent = CASE
                        WHEN voice_status = %(voice_status)s
                             AND (
                                 next_agent IS NULL
                                 OR next_agent = %(voice_generator_agent)s
                                 OR next_agent = %(video_downloader_agent)s
                                 OR next_agent = %(scene_selection_agent)s
                             )
                        THEN %(scene_selection_agent)s
                        ELSE next_agent
                    END,
                    current_agent = NULL,
                    is_locked = FALSE,
                    locked_by = NULL,
                    locked_at = NULL,
                    last_error_agent = NULL,
                    last_error_message = NULL,
                    error_data_json = NULL,
                    updated_at = NOW()
                WHERE id = %(movie_id)s
                RETURNING *;
                """,
                {
                    "movie_id": movie_id,
                    "video_download_status": VIDEO_DOWNLOAD_COMPLETED,
                    "source_video_path": source_video_payload["source_video_path"],
                    "source_videos_json": Json([source_video_payload]),
                    "voice_status": VOICE_COMPLETED,
                    "overall_status": OVERALL_VOICE_READY,
                    "voice_generator_agent": NEXT_AGENT_VOICE_GENERATOR,
                    "video_downloader_agent": NEXT_AGENT_VIDEO_DOWNLOADER,
                    "scene_selection_agent": NEXT_AGENT_SCENE_SELECTION,
                },
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def queue_manual_source_video_url(self, movie_id: int, source_url_payload: dict) -> dict | None:
        self.ensure_video_download_status_column()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                SELECT error_data_json
                FROM movie_review_pipeline
                WHERE id = %s
                LIMIT 1;
                """,
                (movie_id,),
            )
            existing_row = cursor.fetchone()
            if not existing_row:
                return None

            error_data = existing_row.get("error_data_json") or {}
            if not isinstance(error_data, dict):
                error_data = {}

            manual_candidates = error_data.get("manual_source_candidates")
            if not isinstance(manual_candidates, list):
                manual_candidates = []

            source_url = str(source_url_payload["url"]).strip()
            manual_candidates = [
                item
                for item in manual_candidates
                if isinstance(item, dict) and str(item.get("url") or "").strip() != source_url
            ]
            manual_candidates.append(source_url_payload)

            next_error_data = {
                **error_data,
                "manual_source_url_required": False,
                "automatic_retry_blocked": False,
                "youtube_auth_required": False,
                "video_download_attempt_count": 0,
                "retry_exhausted": False,
                "failed_candidate_keys": [],
                "manual_source_candidates": manual_candidates,
            }

            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    video_download_status = %(video_download_status)s,
                    overall_status = %(overall_status)s,
                    next_agent = %(next_agent)s,
                    current_agent = NULL,
                    is_locked = FALSE,
                    locked_by = NULL,
                    locked_at = NULL,
                    last_error_agent = NULL,
                    last_error_message = NULL,
                    error_data_json = %(error_data_json)s,
                    updated_at = NOW()
                WHERE id = %(movie_id)s
                RETURNING *;
                """,
                {
                    "movie_id": movie_id,
                    "video_download_status": VIDEO_DOWNLOAD_PENDING,
                    "overall_status": OVERALL_VOICE_READY,
                    "next_agent": NEXT_AGENT_VIDEO_DOWNLOADER,
                    "error_data_json": Json(next_error_data),
                },
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def retry_video_download(self, movie_id: int) -> dict | None:
        """Requeue an exhausted downloader job without requiring direct DB edits."""
        self.ensure_video_download_status_column()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    video_download_status = %(video_download_status)s,
                    overall_status = %(overall_status)s,
                    next_agent = %(next_agent)s,
                    current_agent = NULL,
                    is_locked = FALSE,
                    locked_by = NULL,
                    locked_at = NULL,
                    last_error_agent = NULL,
                    last_error_message = NULL,
                    error_data_json = COALESCE(error_data_json, '{}'::jsonb)
                        || %(retry_data)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s
                RETURNING *;
                """,
                {
                    "movie_id": movie_id,
                    "video_download_status": VIDEO_DOWNLOAD_PENDING,
                    "overall_status": OVERALL_VOICE_READY,
                    "next_agent": NEXT_AGENT_VIDEO_DOWNLOADER,
                    "retry_data": Json(
                        {
                            "manual_source_url_required": False,
                            "automatic_retry_blocked": False,
                            "youtube_auth_required": False,
                            "video_download_attempt_count": 0,
                            "retry_exhausted": False,
                            "failed_candidate_keys": [],
                        }
                    ),
                },
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_voice_audio_cleanup_candidates(self, safe_only: bool) -> list[dict]:
        render_filter = "AND final_video_path IS NOT NULL" if safe_only else ""
        with get_db_cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    id,
                    movie_title,
                    voice_audio_path,
                    voice_data_json,
                    final_video_path,
                    updated_at
                FROM movie_review_pipeline
                WHERE voice_audio_path IS NOT NULL
                  AND voice_audio_path <> ''
                  {render_filter}
                ORDER BY updated_at DESC;
                """
            )
            return [dict(row) for row in cursor.fetchall()]

    def mark_voice_audio_deleted(self, movie_id: int, deleted_at: str) -> None:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    voice_data_json = COALESCE(voice_data_json, '{}'::jsonb) || %(deletion_data)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    "movie_id": movie_id,
                    "deletion_data": Json(
                        {
                            "audio_deleted_from_storage": True,
                            "audio_deleted_at": deleted_at,
                        }
                    ),
                },
            )

    def approve_processing(self, movie_id: int) -> dict | None:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    is_approved_for_processing = TRUE,
                    overall_status = CASE
                        WHEN script_status = %s
                             AND voice_status = %s
                        THEN %s
                        ELSE overall_status
                    END,
                    updated_at = NOW()
                WHERE id = %s
                RETURNING *;
                """,
                (
                    SCRIPT_COMPLETED,
                    VOICE_PENDING,
                    OVERALL_SCRIPT_READY,
                    movie_id,
                ),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def _update_scene_waiting(self, movie_id: int, scene_status: str, overall_status: str, error_payload: dict) -> None:
        self.ensure_source_videos_column()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    scene_status = %(scene_status)s,
                    overall_status = %(overall_status)s,
                    last_error_agent = %(agent)s,
                    last_error_message = %(error_message)s,
                    error_data_json = %(error_data_json)s,
                    current_agent = NULL,
                    next_agent = %(next_agent)s,
                    is_locked = FALSE,
                    locked_by = NULL,
                    locked_at = NULL,
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    **error_payload,
                    "movie_id": movie_id,
                    "scene_status": scene_status,
                    "overall_status": overall_status,
                    "agent": CURRENT_AGENT_SCENE_SELECTION,
                    "next_agent": NEXT_AGENT_SCENE_SELECTION,
                    "error_data_json": Json(error_payload["error_data"]),
                    "timeline_event": Json([error_payload["timeline_event"]]),
                },
            )

    def get_pending_video_downloader_jobs(self, limit: int) -> list[dict]:
        self.ensure_video_download_status_column()
        self.ensure_runtime_indexes()
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM movie_review_pipeline
                WHERE is_active = TRUE
                  AND is_locked = FALSE
                  AND next_agent = %s
                  AND voice_status = %s
                  AND voice_audio_path IS NOT NULL
                  AND video_download_status = %s
                  AND COALESCE(error_data_json->>'manual_source_url_required', 'false') <> 'true'
                  AND COALESCE(error_data_json->>'automatic_retry_blocked', 'false') <> 'true'
                ORDER BY priority ASC, created_at ASC
                LIMIT %s;
                """,
                (
                    NEXT_AGENT_VIDEO_DOWNLOADER,
                    VOICE_COMPLETED,
                    VIDEO_DOWNLOAD_PENDING,
                    limit,
                ),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_pending_cut_merge_jobs(self, limit: int) -> list[dict]:
        self.ensure_video_download_status_column()
        self.ensure_master_video_path_column()
        self.ensure_runtime_indexes()
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM movie_review_pipeline
                WHERE is_active = TRUE
                  AND is_locked = FALSE
                  AND next_agent = %s
                  AND scene_status = %s
                  AND render_status IN (%s, %s)
                  AND scene_data_json IS NOT NULL
                ORDER BY priority ASC, created_at ASC
                LIMIT %s;
                """,
                (
                    NEXT_AGENT_CUT_MERGE,
                    SCENE_COMPLETED,
                    RENDER_PENDING,
                    RENDER_FAILED,
                    limit,
                ),
            )
            return [dict(row) for row in cursor.fetchall()]

    def update_video_downloader_success(self, movie_id: int, download_payload: dict) -> None:
        self.ensure_video_download_status_column()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    video_download_status = %(video_download_status)s,
                    source_video_path = COALESCE(source_video_path, %(primary_source_video_path)s),
                    source_videos_json = COALESCE(source_videos_json, '[]'::jsonb) || %(source_videos_json)s::jsonb,
                    overall_status = %(overall_status)s,
                    current_agent = NULL,
                    next_agent = %(next_agent)s,
                    progress_percent = 58,
                    is_locked = FALSE,
                    locked_by = NULL,
                    locked_at = NULL,
                    last_error_agent = NULL,
                    last_error_message = NULL,
                    error_data_json = NULL,
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    **download_payload,
                    "movie_id": movie_id,
                    "video_download_status": VIDEO_DOWNLOAD_COMPLETED,
                    "overall_status": OVERALL_VIDEO_DOWNLOADED,
                    "next_agent": NEXT_AGENT_SCENE_SELECTION,
                    "source_videos_json": Json(download_payload["source_video_payloads"]),
                    "timeline_event": Json([download_payload["timeline_event"]]),
                },
            )

    def update_video_downloader_failed(self, movie_id: int, error_payload: dict) -> None:
        self.ensure_video_download_status_column()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    video_download_status = %(video_download_status)s,
                    overall_status = %(overall_status)s,
                    last_error_agent = %(agent)s,
                    last_error_message = %(error_message)s,
                    error_data_json = %(error_data_json)s,
                    current_agent = NULL,
                    next_agent = %(next_agent)s,
                    is_locked = FALSE,
                    locked_by = NULL,
                    locked_at = NULL,
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    **error_payload,
                    "movie_id": movie_id,
                    "video_download_status": VIDEO_DOWNLOAD_FAILED,
                    "overall_status": OVERALL_VIDEO_DOWNLOAD_FAILED,
                    "agent": CURRENT_AGENT_VIDEO_DOWNLOADER,
                    # A failed source download is not the end of the movie
                    # pipeline. Keep it recoverable through retry/manual upload.
                    "next_agent": NEXT_AGENT_VIDEO_DOWNLOADER,
                    "error_data_json": Json(error_payload["error_data"]),
                    "timeline_event": Json([error_payload["timeline_event"]]),
                },
            )

    def update_video_downloader_waiting_source(self, movie_id: int, error_payload: dict) -> None:
        self.ensure_video_download_status_column()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    video_download_status = %(video_download_status)s,
                    overall_status = %(overall_status)s,
                    last_error_agent = %(agent)s,
                    last_error_message = %(error_message)s,
                    error_data_json = %(error_data_json)s,
                    current_agent = NULL,
                    next_agent = %(next_agent)s,
                    is_locked = FALSE,
                    locked_by = NULL,
                    locked_at = NULL,
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    **error_payload,
                    "movie_id": movie_id,
                    "video_download_status": VIDEO_DOWNLOAD_PENDING,
                    "overall_status": OVERALL_WAITING_SOURCE_VIDEO,
                    "agent": CURRENT_AGENT_VIDEO_DOWNLOADER,
                    "next_agent": NEXT_AGENT_VIDEO_DOWNLOADER,
                    "error_data_json": Json(error_payload["error_data"]),
                    "timeline_event": Json([error_payload["timeline_event"]]),
                },
            )

    def update_cut_merge_success(self, movie_id: int, render_payload: dict) -> None:
        self.ensure_master_video_path_column()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    render_status = %(render_status)s,
                    master_video_path = %(master_video_path)s,
                    render_data_json = %(render_data_json)s,
                    overall_status = %(overall_status)s,
                    current_agent = NULL,
                    next_agent = %(next_agent)s,
                    progress_percent = 80,
                    is_locked = FALSE,
                    locked_by = NULL,
                    locked_at = NULL,
                    last_error_agent = NULL,
                    last_error_message = NULL,
                    error_data_json = NULL,
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    **render_payload,
                    "movie_id": movie_id,
                    "render_status": RENDER_COMPLETED,
                    "render_data_json": Json(render_payload["render_data"]),
                    "overall_status": OVERALL_MASTER_VIDEO_READY,
                    "next_agent": NEXT_AGENT_SHORTS_COMPOSER,
                    "timeline_event": Json([render_payload["timeline_event"]]),
                },
            )

    def update_cut_merge_failed(self, movie_id: int, error_payload: dict) -> None:
        self.ensure_master_video_path_column()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    render_status = %(render_status)s,
                    overall_status = %(overall_status)s,
                    last_error_agent = %(agent)s,
                    last_error_message = %(error_message)s,
                    error_data_json = %(error_data_json)s,
                    current_agent = NULL,
                    next_agent = %(next_agent)s,
                    is_locked = FALSE,
                    locked_by = NULL,
                    locked_at = NULL,
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    **error_payload,
                    "movie_id": movie_id,
                    "render_status": RENDER_FAILED,
                    "overall_status": OVERALL_CUT_MERGE_FAILED,
                    "agent": CURRENT_AGENT_CUT_MERGE,
                    "next_agent": NEXT_AGENT_CUT_MERGE,
                    "error_data_json": Json(error_payload["error_data"]),
                    "timeline_event": Json([error_payload["timeline_event"]]),
                },
            )

    def update_shorts_composer_success(self, movie_id: int, shorts_payload: dict) -> None:
        self.ensure_shorts_columns()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    shorts_status = %(shorts_status)s,
                    draft_video_path = %(draft_video_path)s,
                    final_video_path = CASE
                        WHEN %(final_video_path)s IS NOT NULL THEN %(final_video_path)s
                        ELSE final_video_path
                    END,
                    shorts_data_json = %(shorts_data_json)s,
                    overall_status = %(overall_status)s,
                    current_agent = NULL,
                    next_agent = %(next_agent)s,
                    progress_percent = 100,
                    is_locked = FALSE,
                    locked_by = NULL,
                    locked_at = NULL,
                    last_error_agent = NULL,
                    last_error_message = NULL,
                    error_data_json = NULL,
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    **shorts_payload,
                    "movie_id": movie_id,
                    "shorts_status": SHORTS_COMPLETED,
                    "shorts_data_json": Json(
                        {
                            "draft_video_path": shorts_payload["draft_video_path"],
                            "final_video_path": shorts_payload.get("final_video_path"),
                            "master_video_path": shorts_payload["master_video_path"],
                            "voice_audio_path": shorts_payload["voice_audio_path"],
                            "bgm_path": shorts_payload.get("bgm_path"),
                            "duration_seconds": shorts_payload.get("duration_seconds"),
                            "master_duration_seconds": shorts_payload.get("master_duration_seconds"),
                            "voice_duration_seconds": shorts_payload.get("voice_duration_seconds"),
                            "resolution": shorts_payload.get("resolution"),
                            "fps": shorts_payload.get("fps"),
                            "layout": shorts_payload.get("layout") or {},
                            "preprocessing": shorts_payload.get("preprocessing") or {},
                            "audio_mix": shorts_payload.get("audio_mix") or {},
                            "preview_base_path": shorts_payload.get("preview_base_path"),
                            "appearance": shorts_payload.get("appearance") or {},
                            "thumbnail_end_card": shorts_payload.get("thumbnail_end_card") or {},
                            "cloudinary_video_url": shorts_payload.get("cloudinary_video_url"),
                            "cloudinary_public_id": shorts_payload.get("cloudinary_public_id"),
                            "cloudinary": shorts_payload.get("cloudinary") or {},
                            "warnings": shorts_payload.get("warnings") or [],
                        }
                    ),
                    "overall_status": shorts_payload.get("overall_status", OVERALL_FINAL_VIDEO_READY),
                    "next_agent": shorts_payload.get("next_agent", NEXT_AGENT_DONE),
                    "timeline_event": Json([shorts_payload["timeline_event"]]),
                },
            )

    def update_cloudinary_final_video(self, movie_id: int, cloudinary_payload: dict) -> None:
        self.ensure_shorts_columns()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    shorts_data_json = COALESCE(shorts_data_json, '{}'::jsonb) || %(cloudinary_data)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    "movie_id": movie_id,
                    "cloudinary_data": Json(
                        {
                            "cloudinary_video_url": cloudinary_payload["secure_url"],
                            "cloudinary_public_id": cloudinary_payload["public_id"],
                            "cloudinary": cloudinary_payload,
                        }
                    ),
                },
            )

    def update_waiting_voice_upload(self, movie_id: int, timeline_event: dict) -> None:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    overall_status = %(overall_status)s,
                    next_agent = %(next_agent)s,
                    current_agent = NULL,
                    is_locked = FALSE,
                    locked_by = NULL,
                    locked_at = NULL,
                    last_error_agent = NULL,
                    last_error_message = NULL,
                    error_data_json = NULL,
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    "movie_id": movie_id,
                    "overall_status": OVERALL_WAITING_VOICE_UPLOAD,
                    "next_agent": NEXT_AGENT_VOICE_GENERATOR,
                    "timeline_event": Json([timeline_event]),
                },
            )

    def update_waiting_thumbnail_upload(self, movie_id: int, timeline_event: dict) -> None:
        self.ensure_thumbnail_columns()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    overall_status = %(overall_status)s,
                    next_agent = %(next_agent)s,
                    thumbnail_status = CASE
                        WHEN thumbnail_status = %(thumbnail_completed)s THEN thumbnail_status
                        ELSE %(thumbnail_pending)s
                    END,
                    current_agent = NULL,
                    is_locked = FALSE,
                    locked_by = NULL,
                    locked_at = NULL,
                    last_error_agent = NULL,
                    last_error_message = NULL,
                    error_data_json = NULL,
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    "movie_id": movie_id,
                    "overall_status": OVERALL_WAITING_THUMBNAIL_UPLOAD,
                    "next_agent": NEXT_AGENT_THUMBNAIL_METADATA,
                    "thumbnail_completed": THUMBNAIL_COMPLETED,
                    "thumbnail_pending": THUMBNAIL_PENDING,
                    "timeline_event": Json([timeline_event]),
                },
            )

    def update_shorts_composer_failed(self, movie_id: int, error_payload: dict) -> None:
        self.ensure_shorts_columns()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    shorts_status = %(shorts_status)s,
                    overall_status = %(overall_status)s,
                    last_error_agent = %(agent)s,
                    last_error_message = %(error_message)s,
                    error_data_json = %(error_data_json)s,
                    current_agent = NULL,
                    next_agent = %(next_agent)s,
                    is_locked = FALSE,
                    locked_by = NULL,
                    locked_at = NULL,
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    **error_payload,
                    "movie_id": movie_id,
                    "shorts_status": SHORTS_FAILED,
                    "overall_status": OVERALL_SHORTS_COMPOSER_FAILED,
                    "agent": CURRENT_AGENT_SHORTS_COMPOSER,
                    "next_agent": NEXT_AGENT_SHORTS_COMPOSER,
                    "error_data_json": Json(error_payload["error_data"]),
                    "timeline_event": Json([error_payload["timeline_event"]]),
                },
            )

    def update_thumbnail_success(self, movie_id: int, thumbnail_payload: dict) -> None:
        self.ensure_thumbnail_columns()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    thumbnail_status = %(thumbnail_status)s,
                    thumbnail_path = %(thumbnail_path)s,
                    thumbnail_data_json = %(thumbnail_data_json)s,
                    youtube_title = %(youtube_title)s,
                    youtube_description = %(youtube_description)s,
                    youtube_tags_json = %(youtube_tags_json)s,
                    youtube_keywords_json = %(youtube_keywords_json)s,
                    overall_status = CASE WHEN render_status = 'COMPLETED' THEN 'MASTER_VIDEO_READY' ELSE overall_status END,
                    next_agent = CASE WHEN render_status = 'COMPLETED' THEN 'SHORTS_COMPOSER_AGENT' ELSE next_agent END,
                    shorts_status = CASE WHEN render_status = 'COMPLETED' THEN 'PENDING' ELSE shorts_status END,
                    shorts_data_json = CASE WHEN render_status = 'COMPLETED' THEN NULL ELSE shorts_data_json END,
                    draft_video_path = CASE WHEN render_status = 'COMPLETED' THEN NULL ELSE draft_video_path END,
                    final_video_path = CASE WHEN render_status = 'COMPLETED' THEN NULL ELSE final_video_path END,
                    progress_percent = LEAST(progress_percent, 90),
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    "movie_id": movie_id,
                    "thumbnail_status": THUMBNAIL_COMPLETED,
                    "thumbnail_path": thumbnail_payload["thumbnail_path"],
                    "thumbnail_data_json": Json(thumbnail_payload["thumbnail_data"]),
                    "youtube_title": thumbnail_payload.get("youtube_title"),
                    "youtube_description": thumbnail_payload.get("youtube_description"),
                    "youtube_tags_json": Json(thumbnail_payload.get("youtube_tags") or []) if thumbnail_payload.get("youtube_tags") is not None else None,
                    "youtube_keywords_json": Json(thumbnail_payload.get("youtube_keywords") or []) if thumbnail_payload.get("youtube_keywords") is not None else None,
                    "overall_status": OVERALL_THUMBNAIL_READY,
                    "next_agent": NEXT_AGENT_DONE,
                    "timeline_event": Json([thumbnail_payload["timeline_event"]]),
                },
            )

    def update_thumbnail_failed(self, movie_id: int, error_payload: dict) -> None:
        self.ensure_thumbnail_columns()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    thumbnail_status = %(thumbnail_status)s,
                    overall_status = %(overall_status)s,
                    last_error_agent = %(agent)s,
                    last_error_message = %(error_message)s,
                    error_data_json = %(error_data_json)s,
                    current_agent = NULL,
                    next_agent = %(next_agent)s,
                    is_locked = FALSE,
                    locked_by = NULL,
                    locked_at = NULL,
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    **error_payload,
                    "movie_id": movie_id,
                    "thumbnail_status": THUMBNAIL_FAILED,
                    "overall_status": OVERALL_THUMBNAIL_FAILED,
                    "agent": CURRENT_AGENT_THUMBNAIL_METADATA,
                    "next_agent": NEXT_AGENT_THUMBNAIL_METADATA,
                    "error_data_json": Json(error_payload["error_data"]),
                    "timeline_event": Json([error_payload["timeline_event"]]),
                },
            )

    def get_pending_poster_jobs(self, limit: int) -> list[dict]:
        self.ensure_poster_columns()
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM movie_review_pipeline
                WHERE is_active = TRUE
                  AND is_locked = FALSE
                  AND poster_status = 'PENDING'
                  AND (poster_url IS NOT NULL OR backdrop_url IS NOT NULL)
                ORDER BY priority ASC, created_at ASC
                LIMIT %s;
                """,
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def update_poster_success(self, movie_id: int, poster_payload: dict) -> None:
        self.ensure_poster_columns()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    poster_status = %(poster_status)s,
                    poster_local_path = %(poster_local_path)s,
                    backdrop_local_path = %(backdrop_local_path)s,
                    poster_data_json = %(poster_data_json)s,
                    poster_error = NULL,
                    current_agent = NULL,
                    is_locked = FALSE,
                    locked_by = NULL,
                    locked_at = NULL,
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    "movie_id": movie_id,
                    "poster_status": poster_payload["poster_status"],
                    "poster_local_path": poster_payload["poster_local_path"],
                    "backdrop_local_path": poster_payload["backdrop_local_path"],
                    "poster_data_json": Json(poster_payload["poster_data"]),
                    "timeline_event": Json([poster_payload["timeline_event"]]),
                },
            )

    def update_poster_failed(self, movie_id: int, error_payload: dict) -> None:
        self.ensure_poster_columns()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    poster_status = %(poster_status)s,
                    poster_error = %(poster_error)s,
                    last_error_agent = %(agent)s,
                    last_error_message = %(error_message)s,
                    error_data_json = %(error_data_json)s,
                    current_agent = NULL,
                    is_locked = FALSE,
                    locked_by = NULL,
                    locked_at = NULL,
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    **error_payload,
                    "movie_id": movie_id,
                    "poster_status": POSTER_FAILED,
                    "poster_error": error_payload["error_message"],
                    "agent": CURRENT_AGENT_POSTER_DOWNLOAD,
                    "error_data_json": Json(error_payload["error_data"]),
                    "timeline_event": Json([error_payload["timeline_event"]]),
                },
            )

    def update_poster_status(self, movie_id: int, status: str) -> None:
        self.ensure_poster_columns()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    poster_status = %s,
                    updated_at = NOW()
                WHERE id = %s;
                """,
                (status, movie_id),
            )

    # ------------------------------------------------------------------
    # Pipeline Watchdog Agent Methods
    # ------------------------------------------------------------------

    def get_watchdog_candidates(self, limit: int = 20) -> list[dict]:
        """
        Pipeline Watchdog ke liye active movies fetch karta hai jahan source videos
        ya trailer discovery data sanitize/recover kiya ja sakta ho.
        """
        self.ensure_source_videos_column()
        self.ensure_video_download_status_column()
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM movie_review_pipeline
                WHERE is_active = TRUE
                  AND is_locked = FALSE
                  AND current_agent IS NULL
                  AND (
                        overall_status = %s
                        OR COALESCE(source_video_path, '') <> ''
                        OR jsonb_array_length(COALESCE(source_videos_json, '[]'::jsonb)) > 0
                        OR trailer_data_json IS NOT NULL
                        OR COALESCE(trailer_youtube_id, '') <> ''
                      )
                ORDER BY
                    CASE WHEN overall_status = %s THEN 0 ELSE 1 END,
                    priority ASC,
                    updated_at ASC
                LIMIT %s;
                """,
                (OVERALL_WAITING_SOURCE_VIDEO, OVERALL_WAITING_SOURCE_VIDEO, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_stuck_waiting_source_movies(self, limit: int = 20) -> list[dict]:
        """
        WAITING_SOURCE_VIDEO overall_status wali movies fetch karta hai —
        yeh movies Watchdog ke review ke liye candidate hain.
        """
        return self.get_watchdog_candidates(limit=limit)

    def update_source_videos_json(
        self,
        movie_id: int,
        kept_videos: list[dict],
        removed_labels: list[str],
        timeline_event: dict,
    ) -> None:
        """
        source_videos_json mein sirf kept_videos rakhta hai (clips/non-trailer entries hata deta hai).
        Agar kept_videos empty hai toh source_video_path bhi NULL kar deta hai.
        """
        self.ensure_source_videos_column()
        kept_empty = not kept_videos
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    source_videos_json = %(source_videos_json)s::jsonb,
                    source_video_path = CASE
                        WHEN %(kept_empty)s THEN NULL
                        ELSE source_video_path
                    END,
                    last_error_agent = %(agent)s,
                    last_error_message = %(message)s,
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    "movie_id": movie_id,
                    "source_videos_json": Json(kept_videos),
                    "kept_empty": kept_empty,
                    "agent": "PIPELINE_WATCHDOG_AGENT",
                    "message": f"Watchdog removed {len(removed_labels)} non-trailer/teaser entry(ies).",
                    "timeline_event": Json([timeline_event]),
                },
            )

    def update_trailer_data_json(
        self,
        movie_id: int,
        trailer_data: dict,
        timeline_event: dict,
        removed_labels: list[str],
    ) -> None:
        """
        trailer_data_json ko sanitize karke save karta hai taaki selected_videos aur
        TMDB response mein sirf trailer/teaser candidates hi rahein.
        """
        with get_db_cursor(commit=True) as cursor:
            selected_video = trailer_data.get("selected_video") or {}
            youtube_id = str(selected_video.get("key") or "").strip() or None
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    trailer_data_json = %(trailer_data_json)s,
                    trailer_youtube_id = %(trailer_youtube_id)s,
                    trailer_url = %(trailer_url)s,
                    trailer_title = %(trailer_title)s,
                    trailer_type = %(trailer_type)s,
                    trailer_official = %(trailer_official)s,
                    last_error_agent = %(agent)s,
                    last_error_message = %(message)s,
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    "movie_id": movie_id,
                    "trailer_data_json": Json(trailer_data),
                    "trailer_youtube_id": youtube_id,
                    "trailer_url": f"https://www.youtube.com/watch?v={youtube_id}" if youtube_id else None,
                    "trailer_title": selected_video.get("name") if youtube_id else None,
                    "trailer_type": selected_video.get("type") if youtube_id else None,
                    "trailer_official": bool(selected_video.get("official")) if youtube_id else False,
                    "agent": "PIPELINE_WATCHDOG_AGENT",
                    "message": f"Watchdog removed {len(removed_labels)} invalid trailer discovery entry(ies).",
                    "timeline_event": Json([timeline_event]),
                },
            )

    def reset_scene_to_pending(self, movie_id: int, timeline_event: dict) -> None:
        """
        scene_status ko PENDING mein reset karta hai — jab Watchdog valid source video dhundh le
        aur scene selection WAITING_SOURCE_VIDEO mein phasi ho.
        """
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    scene_status = %(scene_status)s,
                    overall_status = %(overall_status)s,
                    next_agent = %(next_agent)s,
                    last_error_agent = NULL,
                    last_error_message = NULL,
                    error_data_json = NULL,
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s
                  AND scene_status = %(waiting_status)s;
                """,
                {
                    "movie_id": movie_id,
                    "scene_status": SCENE_PENDING,
                    "overall_status": OVERALL_SCENES_READY,
                    "next_agent": NEXT_AGENT_SCENE_SELECTION,
                    "waiting_status": SCENE_WAITING_SOURCE_VIDEO,
                    "timeline_event": Json([timeline_event]),
                },
            )

    def requeue_for_video_downloader(self, movie_id: int, timeline_event: dict) -> None:
        """
        Movie ko Video Downloader Agent ke liye re-queue karta hai —
        video_download_status PENDING karta hai, error_data_json clear karta hai
        (lekin failed_candidate_keys preserve karta hai taaki same failed URLs retry na hoin).
        """
        self.ensure_video_download_status_column()
        with get_db_cursor(commit=True) as cursor:
            # Pehle existing error_data_json fetch karo
            cursor.execute(
                "SELECT error_data_json FROM movie_review_pipeline WHERE id = %s;",
                (movie_id,),
            )
            row = cursor.fetchone()
            existing_error_data = (row["error_data_json"] if row else None) or {}

            # failed_candidate_keys preserve karo, baki error data clear karo
            failed_keys = []
            if isinstance(existing_error_data, dict):
                failed_keys = (
                    existing_error_data.get("failed_candidate_keys")
                    or existing_error_data.get("failed_candidate_youtube_ids")
                    or []
                )

            new_error_data = {"failed_candidate_keys": failed_keys} if failed_keys else None

            cursor.execute(
                """
                UPDATE movie_review_pipeline
                SET
                    video_download_status = %(video_download_status)s,
                    overall_status = %(overall_status)s,
                    next_agent = %(next_agent)s,
                    error_data_json = %(error_data_json)s,
                    last_error_agent = NULL,
                    last_error_message = NULL,
                    process_timeline_json = COALESCE(process_timeline_json, '[]'::jsonb) || %(timeline_event)s::jsonb,
                    updated_at = NOW()
                WHERE id = %(movie_id)s;
                """,
                {
                    "movie_id": movie_id,
                    "video_download_status": VIDEO_DOWNLOAD_PENDING,
                    "overall_status": OVERALL_WAITING_SOURCE_VIDEO,
                    "next_agent": NEXT_AGENT_VIDEO_DOWNLOADER,
                    "error_data_json": Json(new_error_data) if new_error_data else None,
                    "timeline_event": Json([timeline_event]),
                },
            )
