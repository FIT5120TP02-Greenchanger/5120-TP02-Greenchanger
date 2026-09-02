BEGIN;

CREATE INDEX IF NOT EXISTS idx_weather_current_property_lookup
    ON weather_observation(observed_at DESC, station_code)
    INCLUDE (air_temperature_c, apparent_temperature_c, station_name)
    WHERE observation_location IS NOT NULL
      AND air_temperature_c IS NOT NULL
      AND quality_status = 'passed';

CREATE OR REPLACE FUNCTION get_property_air_temperature_by_address(
    p_address_search TEXT,
    p_result_limit INTEGER DEFAULT 10
)
RETURNS TABLE (
    address_id UUID,
    parcel_id UUID,
    full_address TEXT,
    air_temperature_c NUMERIC,
    apparent_temperature_c NUMERIC,
    temperature_unit TEXT,
    station_code TEXT,
    station_name TEXT,
    observed_at TIMESTAMPTZ,
    observation_age_minutes NUMERIC,
    station_distance_km NUMERIC,
    context_status TEXT,
    data_status TEXT,
    measurement_type TEXT,
    source_dataset_version_id UUID,
    source_name TEXT,
    source_publisher TEXT,
    source_url TEXT,
    limitation TEXT
)
LANGUAGE SQL
STABLE
PARALLEL SAFE
AS $function$
WITH candidates AS (
    SELECT property.*
    FROM latest_greater_melbourne_address_property AS property
    WHERE p_address_search IS NOT NULL
      AND BTRIM(p_address_search) <> ''
      AND normalize_melbourne_address_search(property.full_address)
          LIKE normalize_melbourne_address_search(p_address_search) || '%'
    ORDER BY
        CASE WHEN normalize_melbourne_address_search(property.full_address) =
                  normalize_melbourne_address_search(p_address_search) THEN 0 ELSE 1 END,
        CASE WHEN property.is_primary = 'Y' THEN 0 ELSE 1 END,
        property.full_address,
        property.source_address_id
    LIMIT LEAST(GREATEST(COALESCE(p_result_limit, 10), 1), 50)
)
SELECT
    candidate.address_id,
    candidate.parcel_id,
    candidate.full_address,
    CASE WHEN weather.distance_m <= 25000
         THEN weather.air_temperature_c END AS air_temperature_c,
    CASE WHEN weather.distance_m <= 25000
         THEN weather.apparent_temperature_c END AS apparent_temperature_c,
    'degC'::TEXT AS temperature_unit,
    weather.station_code,
    weather.station_name,
    weather.observed_at,
    CASE WHEN weather.observed_at IS NULL THEN NULL
         ELSE ROUND(GREATEST(
             0,
             EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - weather.observed_at)) / 60
         )::NUMERIC, 1)
    END AS observation_age_minutes,
    CASE WHEN weather.distance_m IS NULL THEN NULL
         ELSE ROUND((weather.distance_m / 1000.0)::NUMERIC, 2)
    END AS station_distance_km,
    CASE
        WHEN weather.weather_observation_id IS NULL
            THEN 'unavailable_no_observation_within_3_hours'
        WHEN weather.distance_m <= 10000 THEN 'good_local_context'
        WHEN weather.distance_m <= 25000 THEN 'regional_context_warning'
        ELSE 'too_distant_temperature_suppressed'
    END AS context_status,
    CASE
        WHEN weather.weather_observation_id IS NULL OR weather.distance_m > 25000
            THEN 'Unavailable'
        ELSE 'Available'
    END AS data_status,
    'nearest_recent_bom_station_air_temperature_context'::TEXT AS measurement_type,
    weather.dataset_version_id AS source_dataset_version_id,
    weather.source_name,
    weather.publisher AS source_publisher,
    weather.source_url,
    CASE
        WHEN weather.weather_observation_id IS NULL THEN
            'No application-ready BOM station observation is available within the three-hour freshness window; missing temperature is not zero.'
        WHEN weather.distance_m <= 10000 THEN
            'Nearest BOM observation within 10 km; local station context, not a temperature measured at the property.'
        WHEN weather.distance_m <= 25000 THEN
            'Nearest BOM observation is 10-25 km away; regional context only, not a temperature measured at the property.'
        ELSE
            'Nearest recent BOM station is more than 25 km away; temperature is suppressed rather than presented as property context.'
    END AS limitation
FROM candidates AS candidate
LEFT JOIN LATERAL (
    SELECT observation.*,
           ST_Distance(
               observation.observation_location,
               candidate.address_location
           ) AS distance_m
    FROM (
        SELECT DISTINCT ON (weather.station_code)
               weather.*,
               source.source_name,
               source.publisher,
               source.source_url,
               version.extracted_at
        FROM weather_observation AS weather
        JOIN dataset_version AS version USING (dataset_version_id)
        JOIN dataset_source AS source USING (source_id)
        WHERE version.integration_status = 'integrated'
          AND version.publication_status = 'application_ready'
          AND weather.quality_status = 'passed'
          AND weather.air_temperature_c IS NOT NULL
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

COMMENT ON FUNCTION get_property_air_temperature_by_address(TEXT, INTEGER) IS
    'Returns nearest recent BOM station air-temperature context for each matched Melbourne property. Values are in degrees Celsius, observations older than three hours are unavailable, and temperatures beyond 25 km are suppressed. This is not a temperature measured at the property.';

COMMIT;
