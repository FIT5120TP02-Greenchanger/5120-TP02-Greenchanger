BEGIN;

CREATE TABLE IF NOT EXISTS spatial_asset (
    spatial_asset_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    asset_role TEXT NOT NULL,
    source_scene_id TEXT NOT NULL DEFAULT '',
    source_href TEXT,
    local_path TEXT,
    media_type TEXT,
    source_crs TEXT,
    target_srid INTEGER,
    pixel_size_m NUMERIC CHECK (pixel_size_m IS NULL OR pixel_size_m > 0),
    checksum TEXT,
    acquired_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (dataset_version_id, asset_role, source_scene_id)
);

CREATE INDEX IF NOT EXISTS idx_spatial_asset_dataset_version
ON spatial_asset (dataset_version_id);

COMMIT;
