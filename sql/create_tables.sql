CREATE TABLE IF NOT EXISTS movie_review_pipeline (
    id BIGSERIAL PRIMARY KEY,

    job_code VARCHAR(100) UNIQUE NOT NULL,
    overall_status VARCHAR(50) NOT NULL DEFAULT 'DISCOVERED',
    current_agent VARCHAR(100),
    next_agent VARCHAR(100),
    progress_percent INT NOT NULL DEFAULT 0,

    tmdb_id INT,
    imdb_id VARCHAR(50),
    movie_title TEXT NOT NULL,
    release_date DATE,
    language_code VARCHAR(20),
    region_code VARCHAR(20),
    poster_url TEXT,
    backdrop_url TEXT,

    discovery_category VARCHAR(50),
    target_genres_json JSONB NOT NULL DEFAULT '[]'::jsonb,

    trailer_youtube_id VARCHAR(100),
    trailer_url TEXT,
    trailer_title TEXT,
    trailer_type VARCHAR(50),
    trailer_official BOOLEAN NOT NULL DEFAULT FALSE,

    final_script TEXT,
    voice_audio_path TEXT,
    bgm_audio_path TEXT,
    source_video_path TEXT,
    source_videos_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    master_video_path TEXT,
    draft_video_path TEXT,
    final_video_path TEXT,
    thumbnail_path TEXT,

    discovery_status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    trailer_status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    review_status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    script_status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    voice_status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    bgm_status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    scene_status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    render_status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    shorts_status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    thumbnail_status VARCHAR(50) NOT NULL DEFAULT 'PENDING',

    movie_data_json JSONB,
    trailer_data_json JSONB,
    review_data_json JSONB,
    script_data_json JSONB,
    voice_data_json JSONB,
    bgm_data_json JSONB,
    scene_data_json JSONB,
    render_data_json JSONB,
    shorts_data_json JSONB,
    thumbnail_data_json JSONB,

    last_error_agent VARCHAR(100),
    last_error_message TEXT,
    error_data_json JSONB,
    process_timeline_json JSONB NOT NULL DEFAULT '[]'::jsonb,

    is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    locked_by VARCHAR(100),
    locked_at TIMESTAMPTZ,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_approved_for_processing BOOLEAN NOT NULL DEFAULT FALSE,
    priority INT NOT NULL DEFAULT 5,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE movie_review_pipeline
ADD COLUMN IF NOT EXISTS source_videos_json JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE movie_review_pipeline
ADD COLUMN IF NOT EXISTS master_video_path TEXT;

ALTER TABLE movie_review_pipeline
ADD COLUMN IF NOT EXISTS shorts_status VARCHAR(50) NOT NULL DEFAULT 'PENDING';

ALTER TABLE movie_review_pipeline
ADD COLUMN IF NOT EXISTS shorts_data_json JSONB;

ALTER TABLE movie_review_pipeline
ADD COLUMN IF NOT EXISTS draft_video_path TEXT;

ALTER TABLE movie_review_pipeline ADD COLUMN IF NOT EXISTS bgm_status VARCHAR(50) NOT NULL DEFAULT 'PENDING';
ALTER TABLE movie_review_pipeline ADD COLUMN IF NOT EXISTS bgm_audio_path TEXT;
ALTER TABLE movie_review_pipeline ADD COLUMN IF NOT EXISTS bgm_data_json JSONB;

CREATE UNIQUE INDEX IF NOT EXISTS idx_movie_review_pipeline_tmdb_id
ON movie_review_pipeline (tmdb_id);

CREATE INDEX IF NOT EXISTS idx_movie_review_pipeline_queue
ON movie_review_pipeline (next_agent, overall_status, is_locked, is_active);

CREATE INDEX IF NOT EXISTS idx_movie_review_pipeline_created_at
ON movie_review_pipeline (created_at);

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

CREATE UNIQUE INDEX IF NOT EXISTS idx_bgm_library_sha256_hash
ON bgm_library (sha256_hash);

CREATE INDEX IF NOT EXISTS idx_bgm_library_copyright_status
ON bgm_library (copyright_status);

CREATE INDEX IF NOT EXISTS idx_bgm_library_analysis_status
ON bgm_library (analysis_status);

CREATE INDEX IF NOT EXISTS idx_bgm_library_recognized_artist
ON bgm_library (recognized_artist);

CREATE INDEX IF NOT EXISTS idx_bgm_library_duration_seconds
ON bgm_library (duration_seconds);

CREATE INDEX IF NOT EXISTS idx_bgm_library_bpm
ON bgm_library (bpm);

CREATE INDEX IF NOT EXISTS idx_bgm_library_energy_level
ON bgm_library (energy_level);

CREATE INDEX IF NOT EXISTS idx_bgm_library_created_at
ON bgm_library (created_at DESC);

