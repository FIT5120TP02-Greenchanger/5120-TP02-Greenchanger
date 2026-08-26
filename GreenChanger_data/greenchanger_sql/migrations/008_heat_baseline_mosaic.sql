BEGIN;

CREATE TABLE IF NOT EXISTS heat_baseline_cell (
    heat_baseline_cell_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    analysis_area_id UUID NOT NULL REFERENCES analysis_area(analysis_area_id),
    cell_geometry geometry(Polygon, 7855) NOT NULL,
    baseline_surface_temperature_c NUMERIC NOT NULL,
    observed_on DATE NOT NULL,
    observation_count INTEGER NOT NULL CHECK (observation_count > 0),
    scene_count INTEGER NOT NULL CHECK (scene_count > 0),
    source_scene_ids TEXT[] NOT NULL,
    mean_cloud_cover_pct NUMERIC(5, 2) CHECK (
        mean_cloud_cover_pct IS NULL OR mean_cloud_cover_pct BETWEEN 0 AND 100
    ),
    minimum_contributing_temperature_c NUMERIC NOT NULL,
    maximum_contributing_temperature_c NUMERIC NOT NULL,
    same_day_spread_c NUMERIC NOT NULL CHECK (same_day_spread_c >= 0),
    baseline_method TEXT NOT NULL,
    quality_status TEXT NOT NULL DEFAULT 'unreviewed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (baseline_surface_temperature_c BETWEEN -50 AND 80),
    CHECK (minimum_contributing_temperature_c <= baseline_surface_temperature_c),
    CHECK (maximum_contributing_temperature_c >= baseline_surface_temperature_c),
    UNIQUE (dataset_version_id, cell_geometry)
);

CREATE INDEX IF NOT EXISTS idx_heat_baseline_version
    ON heat_baseline_cell(dataset_version_id);

CREATE INDEX IF NOT EXISTS idx_heat_baseline_area
    ON heat_baseline_cell(analysis_area_id);

CREATE INDEX IF NOT EXISTS idx_heat_baseline_observed_on
    ON heat_baseline_cell(observed_on);

CREATE INDEX IF NOT EXISTS idx_heat_baseline_geometry
    ON heat_baseline_cell USING GIST(cell_geometry);

CREATE OR REPLACE VIEW latest_greater_melbourne_heat_baseline AS
SELECT cells.*
FROM heat_baseline_cell AS cells
JOIN dataset_version AS versions USING (dataset_version_id)
JOIN analysis_area AS areas ON areas.analysis_area_id = cells.analysis_area_id
WHERE areas.source_area_code = '2GMEL'
  AND areas.source_year = 2026
  AND versions.integration_status = 'integrated'
  AND versions.publication_status = 'application_ready'
  AND versions.dataset_version_id = (
      SELECT candidate.dataset_version_id
      FROM dataset_version AS candidate
      WHERE candidate.analysis_area_id = versions.analysis_area_id
        AND candidate.derivation_method = 'landsat_latest_daily_mosaic_v1'
        AND candidate.integration_status = 'integrated'
        AND candidate.publication_status = 'application_ready'
      ORDER BY candidate.extracted_at DESC
      LIMIT 1
  );

COMMIT;
