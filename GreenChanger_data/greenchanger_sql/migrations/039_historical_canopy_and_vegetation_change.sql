BEGIN;

INSERT INTO dataset_source (
    source_name, publisher, source_url, licence, licence_status,
    source_category, geographic_coverage, access_method, update_frequency
)
VALUES
    (
        'Tree Canopies 2008 (Urban Forest)', 'City of Melbourne',
        'https://data.melbourne.vic.gov.au/explore/dataset/tree-canopies-2008-urban-forest/',
        'Creative Commons Attribution 4.0 International', 'open_confirmed',
        'historical_canopy', 'City of Melbourne municipality',
        'Open Data Portal JSON-lines API and download', 'static historical snapshot'
    ),
    (
        'Tree Canopies 2015 (Urban Forest)', 'City of Melbourne',
        'https://data.melbourne.vic.gov.au/explore/dataset/tree-canopies-2015-urban-forest/',
        'Creative Commons Attribution 4.0 International', 'open_confirmed',
        'historical_canopy', 'City of Melbourne municipality',
        'Open Data Portal JSON-lines API and download', 'static historical snapshot'
    )
ON CONFLICT (source_name, publisher) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    licence = EXCLUDED.licence,
    licence_status = EXCLUDED.licence_status,
    source_category = EXCLUDED.source_category,
    geographic_coverage = EXCLUDED.geographic_coverage,
    access_method = EXCLUDED.access_method,
    update_frequency = EXCLUDED.update_frequency;

ALTER TABLE canopy_snapshot_feature
    DROP CONSTRAINT IF EXISTS canopy_snapshot_feature_observed_year_check;
ALTER TABLE canopy_snapshot_feature
    ADD CONSTRAINT canopy_snapshot_feature_observed_year_allowed
    CHECK (observed_year IN (2008, 2015, 2016, 2021));

CREATE TABLE metropolitan_vegetation_change_feature (
    vegetation_change_feature_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    source_feature_key TEXT NOT NULL,
    mesh_block_code TEXT,
    observed_from DATE NOT NULL DEFAULT DATE '2014-01-01',
    observed_to DATE NOT NULL DEFAULT DATE '2018-12-31',
    tree_change_pct_points NUMERIC CHECK (tree_change_pct_points BETWEEN -100 AND 100),
    shrub_change_pct_points NUMERIC CHECK (shrub_change_pct_points BETWEEN -100 AND 100),
    grass_change_pct_points NUMERIC CHECK (grass_change_pct_points BETWEEN -100 AND 100),
    total_vegetation_change_pct_points NUMERIC CHECK (
        total_vegetation_change_pct_points BETWEEN -100 AND 100
    ),
    change_geometry geometry(MultiPolygon, 7855) NOT NULL,
    source_properties JSONB NOT NULL DEFAULT '{}'::jsonb,
    quality_status TEXT NOT NULL DEFAULT 'passed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (dataset_version_id, source_feature_key)
);

CREATE INDEX idx_metropolitan_vegetation_change_version
    ON metropolitan_vegetation_change_feature(dataset_version_id, quality_status);
CREATE INDEX idx_metropolitan_vegetation_change_geometry
    ON metropolitan_vegetation_change_feature USING GIST(change_geometry);

CREATE OR REPLACE VIEW latest_metropolitan_vegetation_change AS
WITH ranked_versions AS (
    SELECT
        version.dataset_version_id,
        source.source_name,
        source.source_url,
        source.licence,
        ROW_NUMBER() OVER (
            ORDER BY version.extracted_at DESC, version.dataset_version_id DESC
        ) AS version_rank
    FROM dataset_version AS version
    JOIN dataset_source AS source USING (source_id)
    WHERE source.source_name =
          'Change in Vegetation Cover in Metropolitan Melbourne between 2014 and 2018'
      AND version.integration_status = 'integrated'
      AND version.quality_status IN ('passed', 'passed_with_limitations')
)
SELECT feature.*, version.source_name, version.source_url, version.licence
FROM metropolitan_vegetation_change_feature AS feature
JOIN ranked_versions AS version USING (dataset_version_id)
WHERE version.version_rank = 1
  AND feature.quality_status = 'passed';

INSERT INTO predictive_model_source (
    model_code, source_id, source_role, required_for_training,
    training_use_allowed, licence_decision
)
SELECT 'melbourne_canopy_change', source_id,
       'additional historical canopy snapshot', FALSE, TRUE,
       'CC BY 4.0 confirmed; attribution required'
FROM dataset_source
WHERE publisher = 'City of Melbourne'
  AND source_name IN (
      'Tree Canopies 2008 (Urban Forest)',
      'Tree Canopies 2015 (Urban Forest)'
  )
ON CONFLICT (model_code, source_id) DO UPDATE SET
    source_role = EXCLUDED.source_role,
    required_for_training = EXCLUDED.required_for_training,
    training_use_allowed = EXCLUDED.training_use_allowed,
    licence_decision = EXCLUDED.licence_decision;

COMMENT ON TABLE metropolitan_vegetation_change_feature IS
    'Percentage-point vegetation change from 2014 to 2018 on source polygons based on 2016 ABS Mesh Blocks. It is not interchangeable with City of Melbourne canopy polygons.';
COMMENT ON VIEW latest_metropolitan_vegetation_change IS
    'Latest quality-passing internal 2014-2018 metropolitan vegetation-change features with source attribution.';

COMMIT;
