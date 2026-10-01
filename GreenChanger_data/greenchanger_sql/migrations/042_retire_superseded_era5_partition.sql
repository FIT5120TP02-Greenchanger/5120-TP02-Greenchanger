BEGIN;

CREATE TEMP TABLE superseded_era5_version ON COMMIT DROP AS
SELECT DISTINCT ON (partial.dataset_version_id)
       partial.dataset_version_id AS partial_version_id,
       complete.dataset_version_id AS complete_version_id
FROM dataset_version AS partial
JOIN dataset_source AS source USING (source_id)
JOIN dataset_version AS complete
  ON complete.source_id = partial.source_id
 AND complete.dataset_version_id <> partial.dataset_version_id
 AND complete.source_observed_from <= partial.source_observed_from
 AND complete.source_observed_to >= partial.source_observed_to
 AND (
       complete.source_observed_from < partial.source_observed_from
       OR complete.source_observed_to > partial.source_observed_to
 )
WHERE source.source_name = 'ERA5-Land hourly data from 1950 to present'
  AND source.publisher = 'Copernicus Climate Change Service / ECMWF'
  AND partial.integration_status = 'integrated'
  AND complete.integration_status = 'integrated'
  AND partial.quality_status IN ('passed', 'passed_with_limitations')
  AND complete.quality_status IN ('passed', 'passed_with_limitations')
  AND EXISTS (
      SELECT 1
      FROM era5_land_daily_observation AS partial_observation
      WHERE partial_observation.dataset_version_id = partial.dataset_version_id
  )
  AND NOT EXISTS (
      SELECT 1
      FROM era5_land_daily_observation AS partial_observation
      WHERE partial_observation.dataset_version_id = partial.dataset_version_id
        AND NOT EXISTS (
            SELECT 1
            FROM era5_land_daily_observation AS complete_observation
            WHERE complete_observation.dataset_version_id = complete.dataset_version_id
              AND complete_observation.cell_key = partial_observation.cell_key
              AND complete_observation.observed_on = partial_observation.observed_on
              AND complete_observation.air_temperature_mean_c
                    IS NOT DISTINCT FROM partial_observation.air_temperature_mean_c
              AND complete_observation.air_temperature_min_c
                    IS NOT DISTINCT FROM partial_observation.air_temperature_min_c
              AND complete_observation.air_temperature_max_c
                    IS NOT DISTINCT FROM partial_observation.air_temperature_max_c
              AND complete_observation.precipitation_total_mm
                    IS NOT DISTINCT FROM partial_observation.precipitation_total_mm
              AND complete_observation.soil_water_layer_1_mean_m3_m3
                    IS NOT DISTINCT FROM partial_observation.soil_water_layer_1_mean_m3_m3
              AND complete_observation.surface_solar_radiation_total_mj_m2
                    IS NOT DISTINCT FROM partial_observation.surface_solar_radiation_total_mj_m2
              AND complete_observation.wind_speed_mean_ms
                    IS NOT DISTINCT FROM partial_observation.wind_speed_mean_ms
              AND complete_observation.hour_count = partial_observation.hour_count
        )
  )
ORDER BY partial.dataset_version_id,
         complete.source_observed_to DESC,
         complete.extracted_at DESC,
         complete.dataset_version_id DESC;

DELETE FROM era5_land_daily_observation AS observation
USING superseded_era5_version AS superseded
WHERE observation.dataset_version_id = superseded.partial_version_id;

UPDATE dataset_version AS version
SET integration_status = 'failed',
    publication_status = 'retired',
    derivation_method = CONCAT_WS(
        '; ', NULLIF(version.derivation_method, ''),
        'retired because an identical complete-period ERA5-Land version supersedes this partial period'
    )
FROM superseded_era5_version AS superseded
WHERE version.dataset_version_id = superseded.partial_version_id;

INSERT INTO data_limitation (
    dataset_version_id, limitation_type, description,
    affected_area, analytical_impact, mitigation
)
SELECT
    superseded.partial_version_id,
    'superseded_partial_period',
    'This partial ERA5-Land dataset version was retired after every observation was verified as identical to observations in a complete-period version.',
    'Melbourne ERA5-Land daily grid controls',
    'Keeping both versions active would duplicate logical cell-date records in cross-version training extracts.',
    'Use the complete-period dataset version and version-aware latest views.'
FROM superseded_era5_version AS superseded;

COMMIT;
