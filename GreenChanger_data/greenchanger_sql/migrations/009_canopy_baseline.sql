BEGIN;

CREATE TABLE IF NOT EXISTS canopy_baseline_cell (
    canopy_baseline_cell_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    analysis_area_id UUID NOT NULL REFERENCES analysis_area(analysis_area_id),
    cell_geometry geometry(Polygon, 7855) NOT NULL,
    canopy_percentage NUMERIC(5, 2) NOT NULL CHECK (canopy_percentage BETWEEN 0 AND 100),
    observed_on DATE NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('analytical_geotiff', 'api_tile_proxy')),
    source_pixel_size_m NUMERIC NOT NULL CHECK (source_pixel_size_m > 0),
    grid_size_m NUMERIC NOT NULL CHECK (grid_size_m > 0),
    source_is_proxy BOOLEAN NOT NULL,
    coverage_confidence_pct NUMERIC(5, 2) CHECK (
        coverage_confidence_pct IS NULL OR coverage_confidence_pct BETWEEN 0 AND 100
    ),
    baseline_method TEXT NOT NULL,
    quality_status TEXT NOT NULL DEFAULT 'unreviewed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (dataset_version_id, cell_geometry)
);

CREATE INDEX IF NOT EXISTS idx_canopy_baseline_version
    ON canopy_baseline_cell(dataset_version_id);
CREATE INDEX IF NOT EXISTS idx_canopy_baseline_area
    ON canopy_baseline_cell(analysis_area_id);
CREATE INDEX IF NOT EXISTS idx_canopy_baseline_observed_on
    ON canopy_baseline_cell(observed_on);
CREATE INDEX IF NOT EXISTS idx_canopy_baseline_geometry
    ON canopy_baseline_cell USING GIST(cell_geometry);

CREATE OR REPLACE VIEW latest_greater_melbourne_canopy_baseline AS
SELECT cells.*
FROM canopy_baseline_cell AS cells
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
        AND candidate.derivation_method = 'vicmap_canopy_baseline_500m_v1'
        AND candidate.integration_status = 'integrated'
        AND candidate.publication_status = 'application_ready'
      ORDER BY candidate.extracted_at DESC
      LIMIT 1
  );

COMMIT;
