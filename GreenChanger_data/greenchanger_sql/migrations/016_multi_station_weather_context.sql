BEGIN;

ALTER FUNCTION get_property_baseline(TEXT, INTEGER)
    RENAME TO get_property_baseline_48h_legacy;

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
WITH baseline AS (
    SELECT *
    FROM get_property_baseline_48h_legacy(p_address_search, p_result_limit)
)
SELECT
    baseline.address_id,
    baseline.parcel_id,
    baseline.full_address,
    baseline.locality_name,
    baseline.postcode,
    baseline.source_property_id,
    baseline.parcel_area_m2,
    baseline.lot_size_category,
    baseline.property_type,
    baseline.property_status,
    baseline.longitude,
    baseline.latitude,
    baseline.parcel_geometry_geojson,
    baseline.land_surface_temperature_c,
    baseline.surface_temperature_observed_on,
    baseline.temperature_measurement_type,
    baseline.heat_baseline_method,
    baseline.heat_cell_geojson,
    CASE WHEN weather.distance_m <= 25000
         THEN weather.air_temperature_c END AS current_air_temperature_c,
    CASE WHEN weather.distance_m <= 25000
         THEN weather.apparent_temperature_c END AS current_apparent_temperature_c,
    weather.station_name AS weather_station_name,
    weather.observed_at AS weather_observed_at,
    weather.distance_m / 1000.0 AS weather_station_distance_km,
    CASE
        WHEN weather.weather_observation_id IS NULL
            THEN 'unavailable_no_observation_within_3_hours'
        WHEN weather.distance_m <= 10000 THEN 'good_local_context'
        WHEN weather.distance_m <= 25000 THEN 'regional_context_warning'
        ELSE 'too_distant_temperature_suppressed'
    END AS air_temperature_context_status,
    baseline.neighbourhood_canopy_percentage,
    baseline.property_canopy_percentage,
    baseline.canopy_analysis_scope,
    baseline.canopy_observed_on,
    baseline.canopy_source_type,
    baseline.canopy_source_is_proxy,
    baseline.canopy_cell_geojson,
    baseline.mapped_property_tree_count,
    baseline.property_tree_data_status,
    baseline.data_quality_status,
    JSONB_STRIP_NULLS(
        (COALESCE(baseline.limitations, '{}'::JSONB) - 'air_temperature')
        || JSONB_BUILD_OBJECT(
            'air_temperature', CASE
                WHEN weather.weather_observation_id IS NULL
                    THEN 'No integrated BOM station observation is available within the three-hour freshness window.'
                WHEN weather.distance_m <= 10000
                    THEN 'Nearest BOM observation within 10 km; local station context, not a property-level estimate.'
                WHEN weather.distance_m <= 25000
                    THEN 'Nearest BOM observation is 10-25 km away; regional context only, not a property-level estimate.'
                ELSE 'Nearest recent BOM station is more than 25 km away; air and apparent temperatures are suppressed.'
            END
        )
    ) AS limitations
FROM baseline
JOIN address AS candidate USING (address_id)
LEFT JOIN LATERAL (
    SELECT observation.*,
           ST_Distance(
               observation.observation_location,
               candidate.address_location
           ) AS distance_m
    FROM (
        SELECT DISTINCT ON (weather.station_code)
               weather.*
        FROM weather_observation AS weather
        JOIN dataset_version AS version USING (dataset_version_id)
        WHERE version.integration_status = 'integrated'
          AND version.publication_status = 'application_ready'
          AND weather.observation_location IS NOT NULL
          AND weather.observed_at >= CURRENT_TIMESTAMP - INTERVAL '3 hours'
          AND weather.observed_at <= CURRENT_TIMESTAMP + INTERVAL '5 minutes'
        ORDER BY
            weather.station_code,
            weather.observed_at DESC,
            version.extracted_at DESC
    ) AS observation
    ORDER BY observation.observation_location <-> candidate.address_location
    LIMIT 1
) AS weather ON TRUE;
$function$;

COMMENT ON FUNCTION get_property_baseline(TEXT, INTEGER) IS
    'Returns the nearest application-ready BOM station observation no older than three hours. Air temperature is suppressed beyond 25 km and always remains separate from Landsat land-surface temperature.';

COMMIT;
