BEGIN;

-- Migration 002 predates the multi-station BOM ingestion contract. Keep that
-- immutable migration intact and register the current source under the exact
-- name used by ingestion, provenance queries and integration fixtures.
INSERT INTO dataset_source (
    source_name, publisher, source_url, licence, source_category,
    geographic_coverage, access_method, update_frequency
) VALUES (
    'BOM Melbourne station observations',
    'Bureau of Meteorology',
    'https://www.bom.gov.au/fwo/IDV60901/',
    NULL,
    'weather',
    'Melbourne',
    'Official station-specific JSON feeds listed in config/bom_stations.json',
    'frequent'
)
ON CONFLICT (source_name, publisher) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    licence = EXCLUDED.licence,
    source_category = EXCLUDED.source_category,
    geographic_coverage = EXCLUDED.geographic_coverage,
    access_method = EXCLUDED.access_method,
    update_frequency = EXCLUDED.update_frequency;

COMMIT;
