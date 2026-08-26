BEGIN;

ALTER TABLE analysis_area
    ADD COLUMN IF NOT EXISTS dataset_version_id UUID REFERENCES dataset_version(dataset_version_id),
    ADD COLUMN IF NOT EXISTS source_area_code TEXT,
    ADD COLUMN IF NOT EXISTS source_year SMALLINT,
    ADD COLUMN IF NOT EXISTS source_area_sqkm NUMERIC,
    ADD COLUMN IF NOT EXISTS source_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE UNIQUE INDEX IF NOT EXISTS uq_analysis_area_source_version
    ON analysis_area (source_area_code, source_year)
    WHERE source_area_code IS NOT NULL AND source_year IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_analysis_area_dataset_version
    ON analysis_area (dataset_version_id);

COMMIT;
