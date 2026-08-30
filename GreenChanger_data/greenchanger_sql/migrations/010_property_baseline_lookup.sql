BEGIN;

ALTER TABLE urban_tree
    ADD COLUMN feature_type TEXT,
    ADD COLUMN feature_subtype TEXT,
    ADD COLUMN dense_canopy BOOLEAN;

ALTER TABLE model_version
    ADD COLUMN validation_status TEXT NOT NULL DEFAULT 'draft',
    ADD COLUMN validation_completed_at TIMESTAMPTZ,
    ADD COLUMN validation_summary TEXT,
    ADD CONSTRAINT ck_model_version_validation_status CHECK (
        validation_status IN (
            'draft', 'prototype_only', 'validation_in_progress',
            'validated', 'retired'
        )
    );

UPDATE model_version
SET validation_status = 'prototype_only',
    validation_summary = 'Transparent arithmetic prototype only; no empirical intervention validation completed.'
WHERE model_name = 'GreenShift scenario comparison'
  AND version_label = 'baseline-arithmetic-v1';

CREATE OR REPLACE VIEW application_ready_measure_result AS
SELECT result.*
FROM measure_result AS result
JOIN analysis_run AS run USING (analysis_run_id)
JOIN model_version AS model USING (model_version_id)
WHERE model.validation_status = 'validated'
  AND run.run_status = 'completed';

CREATE OR REPLACE FUNCTION classify_residential_lot_size(p_area_m2 NUMERIC)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
RETURN CASE
    WHEN p_area_m2 IS NULL OR p_area_m2 <= 0 THEN 'unknown'
    WHEN p_area_m2 < 400 THEN 'small'
    WHEN p_area_m2 <= 800 THEN 'medium'
    ELSE 'large'
END;

COMMENT ON FUNCTION classify_residential_lot_size(NUMERIC) IS
    'Project-defined prototype categories: small <400 m2, medium 400-800 m2, large >800 m2. Not a statutory classification.';

CREATE OR REPLACE VIEW latest_greater_melbourne_address_property AS
WITH latest_address_version AS (
    SELECT dv.dataset_version_id
    FROM dataset_version AS dv
    JOIN dataset_source AS ds USING (source_id)
    JOIN analysis_area AS aa USING (analysis_area_id)
    WHERE ds.source_name = 'Vicmap Address'
      AND aa.source_area_code = '2GMEL'
      AND aa.source_year = 2026
      AND dv.integration_status = 'integrated'
      AND dv.publication_status = 'application_ready'
      AND dv.derivation_method LIKE 'clip_to_abs_gccsa_2GMEL_2026_v1:%'
    ORDER BY dv.extracted_at DESC
    LIMIT 1
), latest_property_version AS (
    SELECT dv.dataset_version_id
    FROM dataset_version AS dv
    JOIN dataset_source AS ds USING (source_id)
    JOIN analysis_area AS aa USING (analysis_area_id)
    WHERE ds.source_name = 'Vicmap Property'
      AND aa.source_area_code = '2GMEL'
      AND aa.source_year = 2026
      AND dv.integration_status = 'integrated'
      AND dv.publication_status = 'application_ready'
      AND dv.derivation_method LIKE 'clip_to_abs_gccsa_2GMEL_2026_v1:%'
    ORDER BY dv.extracted_at DESC
    LIMIT 1
)
SELECT
    a.address_id,
    a.dataset_version_id AS address_dataset_version_id,
    a.source_address_id,
    a.source_property_id,
    a.full_address,
    a.locality_name,
    a.postcode,
    a.lga_code,
    a.is_primary,
    a.address_class,
    a.address_location,
    p.parcel_id,
    p.dataset_version_id AS property_dataset_version_id,
    p.source_parcel_id,
    p.property_number,
    p.property_type,
    p.property_status,
    p.parcel_geometry,
    COALESCE(p.parcel_area_m2, ST_Area(p.parcel_geometry)) AS parcel_area_m2,
    classify_residential_lot_size(
        COALESCE(p.parcel_area_m2, ST_Area(p.parcel_geometry))::NUMERIC
    ) AS lot_size_category,
    COALESCE(ST_PointOnSurface(p.parcel_geometry), a.address_location) AS reference_point
FROM address AS a
CROSS JOIN latest_address_version AS av
CROSS JOIN latest_property_version AS pv
LEFT JOIN parcel AS p
  ON p.dataset_version_id = pv.dataset_version_id
 AND p.source_parcel_id = a.source_property_id
WHERE a.dataset_version_id = av.dataset_version_id;

CREATE OR REPLACE FUNCTION get_property_baseline(
    p_address_search TEXT,
    p_result_limit INTEGER DEFAULT 10
)
RETURNS TABLE (
    address_id UUID,
    parcel_id UUID,
    full_address TEXT,
    locality_name TEXT,
    postcode TEXT,
    source_property_id TEXT,
    parcel_area_m2 NUMERIC,
    lot_size_category TEXT,
    property_type TEXT,
    property_status TEXT,
    longitude NUMERIC,
    latitude NUMERIC,
    parcel_geometry_geojson JSONB,
    land_surface_temperature_c NUMERIC,
    surface_temperature_observed_on DATE,
    temperature_measurement_type TEXT,
    heat_baseline_method TEXT,
    heat_cell_geojson JSONB,
    current_air_temperature_c NUMERIC,
    current_apparent_temperature_c NUMERIC,
    weather_station_name TEXT,
    weather_observed_at TIMESTAMPTZ,
    weather_station_distance_km NUMERIC,
    air_temperature_context_status TEXT,
    neighbourhood_canopy_percentage NUMERIC,
    property_canopy_percentage NUMERIC,
    canopy_analysis_scope TEXT,
    canopy_observed_on DATE,
    canopy_source_type TEXT,
    canopy_source_is_proxy BOOLEAN,
    canopy_cell_geojson JSONB,
    mapped_property_tree_count BIGINT,
    property_tree_data_status TEXT,
    data_quality_status TEXT,
    limitations JSONB
)
LANGUAGE SQL
STABLE
PARALLEL SAFE
AS $function$
WITH latest_tree_version AS (
    SELECT dv.dataset_version_id, dv.source_observed_to
    FROM dataset_version AS dv
    JOIN dataset_source AS ds USING (source_id)
    WHERE ds.source_name = 'Vicmap Vegetation - Tree Urban Point'
      AND dv.integration_status = 'integrated'
      AND dv.publication_status = 'application_ready'
    ORDER BY dv.extracted_at DESC
    LIMIT 1
), candidates AS (
    SELECT property.*
    FROM latest_greater_melbourne_address_property AS property
    WHERE p_address_search IS NOT NULL
      AND BTRIM(p_address_search) <> ''
      AND UPPER(property.full_address) LIKE UPPER(BTRIM(p_address_search)) || '%'
    ORDER BY
        CASE WHEN UPPER(property.full_address) = UPPER(BTRIM(p_address_search)) THEN 0 ELSE 1 END,
        CASE WHEN property.is_primary = 'Y' THEN 0 ELSE 1 END,
        property.full_address,
        property.source_address_id
    LIMIT LEAST(GREATEST(COALESCE(p_result_limit, 10), 1), 50)
)
SELECT
    candidate.address_id,
    candidate.parcel_id,
    candidate.full_address,
    candidate.locality_name,
    candidate.postcode,
    candidate.source_property_id,
    candidate.parcel_area_m2,
    candidate.lot_size_category,
    candidate.property_type,
    candidate.property_status,
    ST_X(ST_Transform(candidate.address_location, 4326))::NUMERIC AS longitude,
    ST_Y(ST_Transform(candidate.address_location, 4326))::NUMERIC AS latitude,
    CASE WHEN candidate.parcel_geometry IS NULL THEN NULL
         ELSE ST_AsGeoJSON(ST_Transform(candidate.parcel_geometry, 4326), 6)::JSONB
    END AS parcel_geometry_geojson,
    heat.baseline_surface_temperature_c AS land_surface_temperature_c,
    heat.observed_on AS surface_temperature_observed_on,
    CASE WHEN heat.heat_baseline_cell_id IS NOT NULL
         THEN 'land_surface_temperature' END AS temperature_measurement_type,
    heat.baseline_method AS heat_baseline_method,
    CASE WHEN heat.cell_geometry IS NULL THEN NULL
         ELSE ST_AsGeoJSON(ST_Transform(heat.cell_geometry, 4326), 6)::JSONB
    END AS heat_cell_geojson,
    weather.air_temperature_c AS current_air_temperature_c,
    weather.apparent_temperature_c AS current_apparent_temperature_c,
    weather.station_name AS weather_station_name,
    weather.observed_at AS weather_observed_at,
    weather.distance_m / 1000.0 AS weather_station_distance_km,
    CASE WHEN weather.weather_observation_id IS NULL THEN 'unavailable'
         ELSE 'observed_station_context_not_property_estimate'
    END AS air_temperature_context_status,
    canopy.canopy_percentage AS neighbourhood_canopy_percentage,
    NULL::NUMERIC AS property_canopy_percentage,
    CASE WHEN canopy.canopy_baseline_cell_id IS NOT NULL
         THEN 'neighbourhood_500m' END AS canopy_analysis_scope,
    canopy.observed_on AS canopy_observed_on,
    canopy.source_type AS canopy_source_type,
    canopy.source_is_proxy AS canopy_source_is_proxy,
    CASE WHEN canopy.cell_geometry IS NULL THEN NULL
         ELSE ST_AsGeoJSON(ST_Transform(canopy.cell_geometry, 4326), 6)::JSONB
    END AS canopy_cell_geojson,
    property_trees.tree_count AS mapped_property_tree_count,
    CASE
        WHEN candidate.parcel_id IS NULL THEN 'unavailable_missing_property'
        WHEN property_trees.tree_dataset_version_id IS NULL
            THEN 'not_loaded_neighbourhood_canopy_only'
        ELSE 'mapped_tree_points_available'
    END AS property_tree_data_status,
    CASE
        WHEN candidate.parcel_id IS NULL THEN 'partial_missing_property'
        WHEN heat.heat_baseline_cell_id IS NULL AND canopy.canopy_baseline_cell_id IS NULL
            THEN 'partial_missing_environmental_baselines'
        WHEN heat.heat_baseline_cell_id IS NULL THEN 'partial_missing_heat'
        WHEN canopy.canopy_baseline_cell_id IS NULL THEN 'partial_missing_canopy'
        ELSE 'passed'
    END AS data_quality_status,
    JSONB_STRIP_NULLS(JSONB_BUILD_OBJECT(
        'lot_size_category', 'Project-defined; not a statutory property classification.',
        'heat', CASE WHEN heat.heat_baseline_cell_id IS NOT NULL
                     THEN 'Landsat land-surface temperature, not residential air temperature.' END,
        'air_temperature', CASE WHEN weather.weather_observation_id IS NOT NULL
                     THEN 'Nearest recent BOM station observation; not a property-level estimate.' END,
        'canopy', CASE WHEN canopy.source_is_proxy
                       THEN 'Neighbourhood-only rendered API proxy; property canopy percentage is deliberately suppressed.' END,
        'property_trees', CASE WHEN property_trees.tree_dataset_version_id IS NULL
                       THEN 'Load Vicmap Tree Urban Point before showing mapped individual-tree context.' END,
        'canopy_source_period', CASE WHEN canopy.canopy_baseline_cell_id IS NOT NULL
                                     THEN 'Source imagery varies by location from 2013-12-07 to 2020-11-02.' END
    )) AS limitations
FROM candidates AS candidate
LEFT JOIN LATERAL (
    SELECT cell.*
    FROM latest_greater_melbourne_heat_baseline AS cell
    WHERE cell.cell_geometry && candidate.reference_point
      AND ST_Covers(cell.cell_geometry, candidate.reference_point)
    ORDER BY cell.observed_on DESC, cell.heat_baseline_cell_id
    LIMIT 1
) AS heat ON TRUE
LEFT JOIN LATERAL (
    SELECT cell.*
    FROM latest_greater_melbourne_canopy_baseline AS cell
    WHERE cell.cell_geometry && candidate.reference_point
      AND ST_Covers(cell.cell_geometry, candidate.reference_point)
    ORDER BY cell.observed_on DESC, cell.canopy_baseline_cell_id
    LIMIT 1
) AS canopy ON TRUE
LEFT JOIN LATERAL (
    SELECT observation.*,
           ST_Distance(observation.observation_location, candidate.reference_point) AS distance_m
    FROM (
        SELECT DISTINCT ON (weather.station_code)
               weather.*
        FROM weather_observation AS weather
        JOIN dataset_version AS version USING (dataset_version_id)
        WHERE version.integration_status = 'integrated'
          AND weather.observation_location IS NOT NULL
          AND weather.observed_at >= CURRENT_TIMESTAMP - INTERVAL '48 hours'
        ORDER BY weather.station_code, weather.observed_at DESC
    ) AS observation
    ORDER BY observation.observation_location <-> candidate.reference_point
    LIMIT 1
) AS weather ON TRUE
LEFT JOIN LATERAL (
    SELECT tree_version.dataset_version_id AS tree_dataset_version_id,
           tree_version.source_observed_to,
           COUNT(tree.tree_id)::BIGINT AS tree_count
    FROM latest_tree_version AS tree_version
    LEFT JOIN urban_tree AS tree
      ON tree.dataset_version_id = tree_version.dataset_version_id
     AND candidate.parcel_geometry IS NOT NULL
     AND tree.tree_location && candidate.parcel_geometry
     AND ST_Covers(candidate.parcel_geometry, tree.tree_location)
    GROUP BY tree_version.dataset_version_id, tree_version.source_observed_to
) AS property_trees ON TRUE;
$function$;

COMMENT ON FUNCTION get_property_baseline(TEXT, INTEGER) IS
    'Priority 4 prototype lookup: joins current Melbourne Vicmap Address and Property, then attaches the current 500 m heat and canopy baselines.';

COMMIT;
