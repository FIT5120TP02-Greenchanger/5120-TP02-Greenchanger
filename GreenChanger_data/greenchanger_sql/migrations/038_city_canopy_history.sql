BEGIN;

INSERT INTO dataset_source (
    source_name, publisher, source_url, licence, licence_status,
    source_category, geographic_coverage, access_method, update_frequency
)
VALUES
    (
        'Tree Canopies 2016 (Urban Forest)', 'City of Melbourne',
        'https://data.melbourne.vic.gov.au/explore/dataset/tree-canopies-2016-urban-forest/',
        'Creative Commons Attribution 4.0 International', 'open_confirmed',
        'historical_canopy', 'City of Melbourne municipality',
        'Open Data Portal JSON-lines API and download', 'static historical snapshot'
    ),
    (
        'Tree Canopies 2021 (Urban Forest)', 'City of Melbourne',
        'https://data.melbourne.vic.gov.au/explore/dataset/tree-canopies-2021-urban-forest/',
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

CREATE TABLE canopy_snapshot_feature (
    canopy_snapshot_feature_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    source_feature_key TEXT NOT NULL,
    observed_year SMALLINT NOT NULL CHECK (observed_year IN (2016, 2021)),
    observed_on DATE NOT NULL,
    canopy_geometry geometry(MultiPolygon, 7855) NOT NULL,
    source_area_m2 NUMERIC,
    calculated_area_m2 NUMERIC NOT NULL CHECK (calculated_area_m2 > 0),
    source_area_difference_pct NUMERIC CHECK (
        source_area_difference_pct IS NULL
        OR source_area_difference_pct BETWEEN 0 AND 100
    ),
    geometry_repaired BOOLEAN NOT NULL DEFAULT FALSE,
    quality_status TEXT NOT NULL DEFAULT 'passed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (dataset_version_id, source_feature_key)
);

CREATE INDEX idx_canopy_snapshot_year_version
    ON canopy_snapshot_feature(observed_year, dataset_version_id, quality_status);
CREATE INDEX idx_canopy_snapshot_geometry
    ON canopy_snapshot_feature USING GIST(canopy_geometry);

CREATE OR REPLACE VIEW latest_city_canopy_snapshots AS
WITH ranked_versions AS (
    SELECT
        version.dataset_version_id,
        source.source_name,
        source.source_url,
        source.licence,
        ROW_NUMBER() OVER (
            PARTITION BY EXTRACT(YEAR FROM version.source_observed_to)
            ORDER BY version.extracted_at DESC, version.dataset_version_id DESC
        ) AS version_rank
    FROM dataset_version AS version
    JOIN dataset_source AS source USING (source_id)
    WHERE source.publisher = 'City of Melbourne'
      AND source.source_category = 'historical_canopy'
      AND version.integration_status = 'integrated'
      AND version.quality_status IN ('passed', 'passed_with_limitations')
)
SELECT
    snapshot.*,
    version.source_name,
    version.source_url,
    version.licence
FROM canopy_snapshot_feature AS snapshot
JOIN ranked_versions AS version USING (dataset_version_id)
WHERE version.version_rank = 1
  AND snapshot.quality_status = 'passed';

INSERT INTO predictive_model_source (
    model_code, source_id, source_role, required_for_training,
    training_use_allowed, licence_decision
)
SELECT
    'melbourne_canopy_change', source.source_id,
    CASE source.source_name
        WHEN 'Tree Canopies 2016 (Urban Forest)' THEN 'five-year canopy baseline'
        ELSE 'five-year observed canopy outcome'
    END,
    TRUE, TRUE,
    'CC BY 4.0 confirmed; attribution required'
FROM dataset_source AS source
WHERE source.publisher = 'City of Melbourne'
  AND source.source_name IN (
      'Tree Canopies 2016 (Urban Forest)',
      'Tree Canopies 2021 (Urban Forest)'
  )
ON CONFLICT (model_code, source_id) DO UPDATE SET
    source_role = EXCLUDED.source_role,
    required_for_training = EXCLUDED.required_for_training,
    training_use_allowed = EXCLUDED.training_use_allowed,
    licence_decision = EXCLUDED.licence_decision;

UPDATE predictive_model_specification
SET target_metric = 'canopy_area_change_m2_2016_2021',
    training_grain = 'consistently aligned City of Melbourne analysis cell',
    model_status = 'training_data_not_prepared',
    limitations = 'The initial five-year target covers the City of Melbourne municipality, not all Melbourne. The 2016 aerial-photography/LiDAR and 2021 multispectral mapping methods may create non-biological differences; outputs remain suppressed until alignment and held-out validation are complete.',
    updated_at = CURRENT_TIMESTAMP
WHERE model_code = 'melbourne_canopy_change';

COMMENT ON TABLE canopy_snapshot_feature IS
    'Normalised City of Melbourne canopy polygons for 2016 and 2021. These snapshots are inputs to five-year change-label preparation, not predictions.';
COMMENT ON VIEW latest_city_canopy_snapshots IS
    'Latest quality-passing internal snapshot features for each City of Melbourne canopy observation year.';

COMMIT;
