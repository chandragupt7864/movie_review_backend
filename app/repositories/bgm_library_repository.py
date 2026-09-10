from math import ceil

from psycopg2 import sql
from psycopg2.extras import Json

from app.database import get_db_cursor


class BGMLibraryRepository:
    SORT_MAP = {
        "created_at.desc": sql.SQL("created_at DESC"),
        "created_at.asc": sql.SQL("created_at ASC"),
        "display_name.asc": sql.SQL("display_name ASC NULLS LAST"),
        "display_name.desc": sql.SQL("display_name DESC NULLS LAST"),
        "duration.asc": sql.SQL("duration_seconds ASC NULLS LAST"),
        "duration.desc": sql.SQL("duration_seconds DESC NULLS LAST"),
        "bpm.asc": sql.SQL("bpm ASC NULLS LAST"),
        "bpm.desc": sql.SQL("bpm DESC NULLS LAST"),
    }

    def ensure_table(self) -> None:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS bgm_library (
                    id BIGSERIAL PRIMARY KEY,
                    track_code VARCHAR(100) UNIQUE NOT NULL,
                    original_filename TEXT NOT NULL,
                    display_name TEXT,
                    storage_bucket VARCHAR(100),
                    storage_path TEXT,
                    mime_type VARCHAR(255),
                    file_extension VARCHAR(20),
                    file_size_bytes BIGINT,
                    sha256_hash VARCHAR(128) NOT NULL,
                    duration_seconds DOUBLE PRECISION,
                    codec VARCHAR(100),
                    bit_rate BIGINT,
                    sample_rate INT,
                    channels INT,
                    audio_format VARCHAR(100),
                    bpm DOUBLE PRECISION,
                    tempo_category VARCHAR(20),
                    energy_level VARCHAR(20),
                    loudness_lufs DOUBLE PRECISION,
                    peak_db DOUBLE PRECISION,
                    is_instrumental BOOLEAN,
                    technical_data_json JSONB,
                    embedded_metadata_json JSONB,
                    fingerprint TEXT,
                    fingerprint_provider VARCHAR(100),
                    recognition_provider VARCHAR(100),
                    recognition_status VARCHAR(50),
                    recognized_title TEXT,
                    recognized_artist TEXT,
                    recognized_album TEXT,
                    recognized_release TEXT,
                    recognized_recording_id VARCHAR(255),
                    recognized_musicbrainz_id VARCHAR(255),
                    recognition_confidence DOUBLE PRECISION,
                    recognition_data_json JSONB,
                    copyright_status VARCHAR(50) NOT NULL DEFAULT 'UNKNOWN',
                    copyright_risk_level VARCHAR(50) NOT NULL DEFAULT 'UNKNOWN',
                    license_type VARCHAR(100),
                    attribution_required BOOLEAN NOT NULL DEFAULT FALSE,
                    attribution_text TEXT,
                    copyright_reason TEXT,
                    source_type VARCHAR(100),
                    source_reference TEXT,
                    mood_tags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                    genre_tags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                    analysis_status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
                    analysis_warning TEXT,
                    analysis_data_json JSONB,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_bgm_library_sha256_hash ON bgm_library (sha256_hash);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_bgm_library_copyright_status ON bgm_library (copyright_status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_bgm_library_analysis_status ON bgm_library (analysis_status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_bgm_library_recognized_artist ON bgm_library (recognized_artist);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_bgm_library_duration_seconds ON bgm_library (duration_seconds);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_bgm_library_bpm ON bgm_library (bpm);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_bgm_library_energy_level ON bgm_library (energy_level);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_bgm_library_created_at ON bgm_library (created_at DESC);")

    def create_bgm_track(self, payload: dict) -> dict:
        self.ensure_table()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                INSERT INTO bgm_library (
                    track_code, original_filename, display_name, storage_bucket, storage_path,
                    mime_type, file_extension, file_size_bytes, sha256_hash, duration_seconds,
                    codec, bit_rate, sample_rate, channels, audio_format, bpm, tempo_category,
                    energy_level, loudness_lufs, peak_db, is_instrumental, technical_data_json,
                    embedded_metadata_json, fingerprint, fingerprint_provider, recognition_provider,
                    recognition_status, recognized_title, recognized_artist, recognized_album,
                    recognized_release, recognized_recording_id, recognized_musicbrainz_id,
                    recognition_confidence, recognition_data_json, copyright_status,
                    copyright_risk_level, license_type, attribution_required, attribution_text,
                    copyright_reason, source_type, source_reference, mood_tags_json,
                    genre_tags_json, analysis_status, analysis_warning, analysis_data_json, is_active
                )
                VALUES (
                    %(track_code)s, %(original_filename)s, %(display_name)s, %(storage_bucket)s, %(storage_path)s,
                    %(mime_type)s, %(file_extension)s, %(file_size_bytes)s, %(sha256_hash)s, %(duration_seconds)s,
                    %(codec)s, %(bit_rate)s, %(sample_rate)s, %(channels)s, %(audio_format)s, %(bpm)s, %(tempo_category)s,
                    %(energy_level)s, %(loudness_lufs)s, %(peak_db)s, %(is_instrumental)s, %(technical_data_json)s,
                    %(embedded_metadata_json)s, %(fingerprint)s, %(fingerprint_provider)s, %(recognition_provider)s,
                    %(recognition_status)s, %(recognized_title)s, %(recognized_artist)s, %(recognized_album)s,
                    %(recognized_release)s, %(recognized_recording_id)s, %(recognized_musicbrainz_id)s,
                    %(recognition_confidence)s, %(recognition_data_json)s, %(copyright_status)s,
                    %(copyright_risk_level)s, %(license_type)s, %(attribution_required)s, %(attribution_text)s,
                    %(copyright_reason)s, %(source_type)s, %(source_reference)s, %(mood_tags_json)s,
                    %(genre_tags_json)s, %(analysis_status)s, %(analysis_warning)s, %(analysis_data_json)s, %(is_active)s
                )
                RETURNING *;
                """,
                self._json_payload(payload),
            )
            return dict(cursor.fetchone())

    def get_bgm_by_id(self, track_id: int) -> dict | None:
        self.ensure_table()
        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM bgm_library WHERE id = %s AND is_active = TRUE;", (track_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_bgm_by_sha256(self, sha256_hash: str) -> dict | None:
        self.ensure_table()
        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM bgm_library WHERE sha256_hash = %s;", (sha256_hash,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_verified_track_by_fingerprint(self, fingerprint: str) -> dict | None:
        if not fingerprint:
            return None
        self.ensure_table()
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM bgm_library
                WHERE fingerprint = %s
                  AND copyright_status IN ('VERIFIED_SAFE', 'ATTRIBUTION_REQUIRED')
                ORDER BY updated_at DESC
                LIMIT 1;
                """,
                (fingerprint,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_bgm_analysis(self, track_id: int, payload: dict) -> dict | None:
        self.ensure_table()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE bgm_library
                SET
                    display_name = %(display_name)s,
                    mime_type = %(mime_type)s,
                    file_extension = %(file_extension)s,
                    file_size_bytes = %(file_size_bytes)s,
                    duration_seconds = %(duration_seconds)s,
                    codec = %(codec)s,
                    bit_rate = %(bit_rate)s,
                    sample_rate = %(sample_rate)s,
                    channels = %(channels)s,
                    audio_format = %(audio_format)s,
                    bpm = %(bpm)s,
                    tempo_category = %(tempo_category)s,
                    energy_level = %(energy_level)s,
                    loudness_lufs = %(loudness_lufs)s,
                    peak_db = %(peak_db)s,
                    is_instrumental = %(is_instrumental)s,
                    technical_data_json = %(technical_data_json)s,
                    embedded_metadata_json = %(embedded_metadata_json)s,
                    fingerprint = %(fingerprint)s,
                    fingerprint_provider = %(fingerprint_provider)s,
                    recognition_provider = %(recognition_provider)s,
                    recognition_status = %(recognition_status)s,
                    recognized_title = %(recognized_title)s,
                    recognized_artist = %(recognized_artist)s,
                    recognized_album = %(recognized_album)s,
                    recognized_release = %(recognized_release)s,
                    recognized_recording_id = %(recognized_recording_id)s,
                    recognized_musicbrainz_id = %(recognized_musicbrainz_id)s,
                    recognition_confidence = %(recognition_confidence)s,
                    recognition_data_json = %(recognition_data_json)s,
                    copyright_status = %(copyright_status)s,
                    copyright_risk_level = %(copyright_risk_level)s,
                    license_type = %(license_type)s,
                    attribution_required = %(attribution_required)s,
                    attribution_text = %(attribution_text)s,
                    copyright_reason = %(copyright_reason)s,
                    source_type = %(source_type)s,
                    source_reference = %(source_reference)s,
                    mood_tags_json = %(mood_tags_json)s,
                    genre_tags_json = %(genre_tags_json)s,
                    analysis_status = %(analysis_status)s,
                    analysis_warning = %(analysis_warning)s,
                    analysis_data_json = %(analysis_data_json)s,
                    updated_at = NOW()
                WHERE id = %(track_id)s
                RETURNING *;
                """,
                self._json_payload({**payload, "track_id": track_id}),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_bgm_storage(self, track_id: int, storage_bucket: str, storage_path: str) -> dict | None:
        self.ensure_table()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE bgm_library
                SET storage_bucket = %s, storage_path = %s, updated_at = NOW()
                WHERE id = %s
                RETURNING *;
                """,
                (storage_bucket, storage_path, track_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def delete_bgm_track(self, track_id: int) -> None:
        self.ensure_table()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute("DELETE FROM bgm_library WHERE id = %s;", (track_id,))

    def list_bgm_tracks(self, filters: dict) -> dict:
        self.ensure_table()
        page = max(1, int(filters.get("page") or 1))
        page_size = min(100, max(1, int(filters.get("page_size") or 20)))
        sort_sql = self.SORT_MAP.get(filters.get("sort_by") or "created_at.desc", self.SORT_MAP["created_at.desc"])

        where_clauses = [sql.SQL("is_active = TRUE")]
        params: list[object] = []

        if filters.get("q"):
            q_value = f"%{str(filters['q']).strip()}%"
            where_clauses.append(
                sql.SQL(
                    "(COALESCE(display_name, '') ILIKE %s OR COALESCE(original_filename, '') ILIKE %s OR "
                    "COALESCE(recognized_title, '') ILIKE %s OR COALESCE(recognized_artist, '') ILIKE %s)"
                )
            )
            params.extend([q_value, q_value, q_value, q_value])
        if filters.get("copyright_status"):
            where_clauses.append(sql.SQL("copyright_status = %s"))
            params.append(filters["copyright_status"])
        if filters.get("analysis_status"):
            where_clauses.append(sql.SQL("analysis_status = %s"))
            params.append(filters["analysis_status"])
        if filters.get("recognition_status"):
            where_clauses.append(sql.SQL("recognition_status = %s"))
            params.append(filters["recognition_status"])
        if filters.get("recognized") is True:
            where_clauses.append(sql.SQL("recognized_title IS NOT NULL"))
        elif filters.get("recognized") is False:
            where_clauses.append(sql.SQL("recognized_title IS NULL"))
        if filters.get("artist"):
            where_clauses.append(sql.SQL("recognized_artist ILIKE %s"))
            params.append(f"%{str(filters['artist']).strip()}%")
        if filters.get("duration_min") is not None:
            where_clauses.append(sql.SQL("duration_seconds >= %s"))
            params.append(filters["duration_min"])
        if filters.get("duration_max") is not None:
            where_clauses.append(sql.SQL("duration_seconds <= %s"))
            params.append(filters["duration_max"])
        if filters.get("bpm_min") is not None:
            where_clauses.append(sql.SQL("bpm >= %s"))
            params.append(filters["bpm_min"])
        if filters.get("bpm_max") is not None:
            where_clauses.append(sql.SQL("bpm <= %s"))
            params.append(filters["bpm_max"])
        if filters.get("tempo_category"):
            where_clauses.append(sql.SQL("tempo_category = %s"))
            params.append(filters["tempo_category"])
        if filters.get("energy_level"):
            where_clauses.append(sql.SQL("energy_level = %s"))
            params.append(filters["energy_level"])
        if filters.get("is_instrumental") is not None:
            where_clauses.append(sql.SQL("is_instrumental = %s"))
            params.append(filters["is_instrumental"])
        if filters.get("mood"):
            where_clauses.append(sql.SQL("mood_tags_json ? %s"))
            params.append(filters["mood"])
        if filters.get("genre"):
            where_clauses.append(sql.SQL("genre_tags_json ? %s"))
            params.append(filters["genre"])

        where_sql = sql.SQL(" WHERE ") + sql.SQL(" AND ").join(where_clauses)
        offset = (page - 1) * page_size

        with get_db_cursor() as cursor:
            cursor.execute(sql.SQL("SELECT COUNT(*) AS total FROM bgm_library") + where_sql, params)
            total = int(cursor.fetchone()["total"])
            cursor.execute(
                sql.SQL(
                    """
                    SELECT *
                    FROM bgm_library
                    """
                )
                + where_sql
                + sql.SQL(" ORDER BY ")
                + sort_sql
                + sql.SQL(" LIMIT %s OFFSET %s"),
                [*params, page_size, offset],
            )
            rows = [dict(row) for row in cursor.fetchall()]

        total_pages = ceil(total / page_size) if total else 0
        return {
            "filters": filters,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "total_results": total,
                "has_next": page < total_pages,
                "has_previous": page > 1 and total_pages > 0,
            },
            "tracks": rows,
        }

    def get_bgm_filter_options(self) -> dict:
        self.ensure_table()
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    ARRAY(SELECT DISTINCT copyright_status FROM bgm_library WHERE is_active = TRUE AND copyright_status IS NOT NULL ORDER BY 1) AS copyright_statuses,
                    ARRAY(SELECT DISTINCT analysis_status FROM bgm_library WHERE is_active = TRUE AND analysis_status IS NOT NULL ORDER BY 1) AS analysis_statuses,
                    ARRAY(SELECT DISTINCT recognized_artist FROM bgm_library WHERE is_active = TRUE AND recognized_artist IS NOT NULL ORDER BY 1) AS artists,
                    ARRAY(SELECT DISTINCT tempo_category FROM bgm_library WHERE is_active = TRUE AND tempo_category IS NOT NULL ORDER BY 1) AS tempo_categories,
                    ARRAY(SELECT DISTINCT energy_level FROM bgm_library WHERE is_active = TRUE AND energy_level IS NOT NULL ORDER BY 1) AS energy_levels,
                    ARRAY(
                        SELECT DISTINCT jsonb_array_elements_text(COALESCE(mood_tags_json, '[]'::jsonb))
                        FROM bgm_library
                        WHERE is_active = TRUE
                        ORDER BY 1
                    ) AS moods,
                    ARRAY(
                        SELECT DISTINCT jsonb_array_elements_text(COALESCE(genre_tags_json, '[]'::jsonb))
                        FROM bgm_library
                        WHERE is_active = TRUE
                        ORDER BY 1
                    ) AS genres;
                """
            )
            return dict(cursor.fetchone())

    def get_bgm_stats(self) -> dict:
        self.ensure_table()
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE is_active = TRUE) AS total_tracks,
                    COUNT(*) FILTER (WHERE is_active = TRUE AND copyright_status = 'VERIFIED_SAFE') AS verified_safe,
                    COUNT(*) FILTER (WHERE is_active = TRUE AND copyright_status = 'ATTRIBUTION_REQUIRED') AS attribution_required,
                    COUNT(*) FILTER (WHERE is_active = TRUE AND copyright_status = 'LIKELY_COPYRIGHTED') AS likely_copyrighted,
                    COUNT(*) FILTER (WHERE is_active = TRUE AND copyright_status = 'REVIEW_REQUIRED') AS review_required,
                    COUNT(*) FILTER (WHERE is_active = TRUE AND copyright_status = 'UNKNOWN') AS unknown,
                    COALESCE(SUM(file_size_bytes) FILTER (WHERE is_active = TRUE), 0) AS total_storage_bytes
                FROM bgm_library;
                """
            )
            return dict(cursor.fetchone())

    def get_next_track_code(self) -> str:
        self.ensure_table()
        with get_db_cursor(commit=True) as cursor:
            cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM bgm_library;")
            next_id = int(cursor.fetchone()["next_id"])
            return f"BGM-{next_id:06d}"

    @staticmethod
    def _json_payload(payload: dict) -> dict:
        json_fields = {
            "technical_data_json",
            "embedded_metadata_json",
            "recognition_data_json",
            "mood_tags_json",
            "genre_tags_json",
            "analysis_data_json",
        }
        converted = dict(payload)
        for field in json_fields:
            if field in converted:
                converted[field] = Json(converted[field]) if converted[field] is not None else None
        return converted
