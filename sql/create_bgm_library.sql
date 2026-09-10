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
