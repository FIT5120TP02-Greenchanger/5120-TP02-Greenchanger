BEGIN;

CREATE TABLE property_canopy_summary (
    property_canopy_summary_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    source_canopy_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    parcel_id UUID NOT NULL REFERENCES parcel(parcel_id),
    observed_on DATE NOT NULL,
    canopy_area_m2 NUMERIC CHECK (canopy_area_m2 IS NULL OR canopy_area_m2 >= 0),
    parcel_area_m2 NUMERIC NOT NULL CHECK (parcel_area_m2 > 0),
    raster_covered_area_m2 NUMERIC NOT NULL CHECK (raster_covered_area_m2 >= 0),
    canopy_percentage NUMERIC(6, 2) CHECK (
        canopy_percentage IS NULL OR canopy_percentage BETWEEN 0 AND 100
    ),
    coverage_percentage NUMERIC(6, 2) NOT NULL CHECK (
        coverage_percentage BETWEEN 0 AND 100
    ),
    source_pixel_size_m NUMERIC NOT NULL CHECK (
        source_pixel_size_m > 0 AND source_pixel_size_m <= 2
    ),
    calculation_method TEXT NOT NULL DEFAULT 'parcel_clip_pixel_centre_v1',
    quality_status TEXT NOT NULL CHECK (quality_status IN ('passed', 'failed')),
    failure_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (dataset_version_id, parcel_id),
    CHECK (
        (quality_status = 'passed' AND canopy_percentage IS NOT NULL
         AND canopy_area_m2 IS NOT NULL AND coverage_percentage >= 95)
        OR
        (quality_status = 'failed' AND canopy_percentage IS NULL
         AND failure_reason IS NOT NULL)
    )
);

CREATE INDEX idx_property_canopy_parcel_version
    ON property_canopy_summary(parcel_id, dataset_version_id);
CREATE INDEX idx_property_canopy_source_version
    ON property_canopy_summary(source_canopy_version_id);

CREATE OR REPLACE VIEW latest_melbourne_property_canopy AS
WITH latest_version AS (
    SELECT dv.dataset_version_id
    FROM dataset_version AS dv
    JOIN dataset_source AS ds USING (source_id)
    JOIN analysis_area AS aa USING (analysis_area_id)
    WHERE ds.source_name = 'Vicmap Vegetation - Tree Extent'
      AND aa.source_area_code = '2GMEL'
      AND aa.source_year = 2026
      AND dv.integration_status = 'integrated'
      AND dv.publication_status = 'application_ready'
      AND dv.quality_pass_rate >= 95
      AND dv.derivation_method = 'property_canopy_raster_clip_v1'
    ORDER BY dv.extracted_at DESC
    LIMIT 1
)
SELECT summary.*
FROM property_canopy_summary AS summary
JOIN latest_version USING (dataset_version_id)
WHERE summary.quality_status = 'passed';

CREATE OR REPLACE FUNCTION get_property_canopy_by_address(
    p_address_search TEXT,
    p_result_limit INTEGER DEFAULT 10
)
RETURNS TABLE (
    address_id UUID,
    parcel_id UUID,
    full_address TEXT,
    parcel_area_m2 NUMERIC,
    canopy_area_m2 NUMERIC,
    property_canopy_percentage NUMERIC,
    raster_coverage_percentage NUMERIC,
    observed_on DATE,
    source_pixel_size_m NUMERIC,
    calculation_method TEXT,
    data_status TEXT,
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
        property.full_address,
        property.source_address_id
    LIMIT LEAST(GREATEST(COALESCE(p_result_limit, 10), 1), 50)
)
SELECT
    candidate.address_id,
    candidate.parcel_id,
    candidate.full_address,
    candidate.parcel_area_m2,
    canopy.canopy_area_m2,
    canopy.canopy_percentage,
    canopy.coverage_percentage,
    canopy.observed_on,
    canopy.source_pixel_size_m,
    canopy.calculation_method,
    CASE
        WHEN candidate.parcel_id IS NULL THEN 'Unavailable'
        WHEN canopy.property_canopy_summary_id IS NULL THEN 'Unavailable'
        ELSE 'Available'
    END AS data_status,
    CASE
        WHEN candidate.parcel_id IS NULL THEN 'No parcel geometry is linked to this address.'
        WHEN canopy.property_canopy_summary_id IS NULL THEN
            'No application-ready analytical property-canopy result is loaded; missing data is not zero canopy.'
        ELSE 'Machine-derived canopy from source imagery; not a current field survey.'
    END AS limitation
FROM candidates AS candidate
LEFT JOIN latest_melbourne_property_canopy AS canopy
  ON canopy.parcel_id = candidate.parcel_id;
$function$;

COMMENT ON TABLE property_canopy_summary IS
    'Versioned parcel-clipped canopy measures from a <=2 m analytical Tree Extent GeoTIFF. Rendered API proxy mosaics are prohibited.';
COMMENT ON FUNCTION get_property_canopy_by_address(TEXT, INTEGER) IS
    'Returns canopy clipped to the matched Melbourne parcel. Missing analytical results return Unavailable, never zero canopy.';

ALTER FUNCTION get_property_baseline(TEXT, INTEGER)
    RENAME TO get_property_baseline_pre_property_canopy_legacy;

CREATE OR REPLACE FUNCTION get_property_baseline(
    p_address_search TEXT,
    p_result_limit INTEGER DEFAULT 10
)
RETURNS TABLE (
    address_id UUID, parcel_id UUID, full_address TEXT, locality_name TEXT,
    postcode TEXT, source_property_id TEXT, parcel_area_m2 NUMERIC,
    lot_size_category TEXT, property_type TEXT, property_status TEXT,
    longitude NUMERIC, latitude NUMERIC, parcel_geometry_geojson JSONB,
    land_surface_temperature_c NUMERIC, surface_temperature_observed_on DATE,
    temperature_measurement_type TEXT, heat_baseline_method TEXT,
    heat_cell_geojson JSONB, current_air_temperature_c NUMERIC,
    current_apparent_temperature_c NUMERIC, weather_station_name TEXT,
    weather_observed_at TIMESTAMPTZ, weather_station_distance_km NUMERIC,
    air_temperature_context_status TEXT, neighbourhood_canopy_percentage NUMERIC,
    property_canopy_percentage NUMERIC, canopy_analysis_scope TEXT,
    canopy_observed_on DATE, canopy_source_type TEXT,
    canopy_source_is_proxy BOOLEAN, canopy_cell_geojson JSONB,
    mapped_property_tree_count BIGINT, property_tree_data_status TEXT,
    data_quality_status TEXT, limitations JSONB, heat_classification TEXT,
    canopy_classification TEXT, classification_scheme_version TEXT,
    classification_scope TEXT
)
LANGUAGE SQL
STABLE
PARALLEL SAFE
AS $function$
WITH baseline AS (
    SELECT *
    FROM get_property_baseline_pre_property_canopy_legacy(
        p_address_search, p_result_limit
    )
)
SELECT
    baseline.address_id, baseline.parcel_id, baseline.full_address,
    baseline.locality_name, baseline.postcode, baseline.source_property_id,
    baseline.parcel_area_m2, baseline.lot_size_category, baseline.property_type,
    baseline.property_status, baseline.longitude, baseline.latitude,
    baseline.parcel_geometry_geojson, baseline.land_surface_temperature_c,
    baseline.surface_temperature_observed_on, baseline.temperature_measurement_type,
    baseline.heat_baseline_method, baseline.heat_cell_geojson,
    baseline.current_air_temperature_c, baseline.current_apparent_temperature_c,
    baseline.weather_station_name, baseline.weather_observed_at,
    baseline.weather_station_distance_km, baseline.air_temperature_context_status,
    baseline.neighbourhood_canopy_percentage,
    property_canopy.canopy_percentage AS property_canopy_percentage,
    CASE WHEN property_canopy.property_canopy_summary_id IS NOT NULL
         THEN 'property_raster_clip'
         ELSE baseline.canopy_analysis_scope END AS canopy_analysis_scope,
    COALESCE(property_canopy.observed_on, baseline.canopy_observed_on),
    CASE WHEN property_canopy.property_canopy_summary_id IS NOT NULL
         THEN 'analytical_geotiff_property_clip'
         ELSE baseline.canopy_source_type END AS canopy_source_type,
    CASE WHEN property_canopy.property_canopy_summary_id IS NOT NULL
         THEN FALSE ELSE baseline.canopy_source_is_proxy END AS canopy_source_is_proxy,
    baseline.canopy_cell_geojson, baseline.mapped_property_tree_count,
    baseline.property_tree_data_status, baseline.data_quality_status,
    baseline.limitations || JSONB_BUILD_OBJECT(
        'property_canopy',
        CASE WHEN property_canopy.property_canopy_summary_id IS NOT NULL THEN
            FORMAT(
                'Parcel-clipped analytical Tree Extent at %s m source resolution; %s%% raster coverage. Machine-derived, not a current field survey.',
                property_canopy.source_pixel_size_m,
                property_canopy.coverage_percentage
            )
        ELSE
            'Unavailable until a quality-passed analytical Tree Extent result covers this parcel; missing is not zero canopy.'
        END
    ) AS limitations,
    baseline.heat_classification,
    baseline.canopy_classification,
    baseline.classification_scheme_version,
    baseline.classification_scope
FROM baseline
LEFT JOIN latest_melbourne_property_canopy AS property_canopy
  ON property_canopy.parcel_id = baseline.parcel_id;
$function$;

COMMENT ON FUNCTION get_property_baseline(TEXT, INTEGER) IS
    'Returns existing heat, weather and 500 m canopy context plus parcel-clipped analytical property canopy when an application-ready result exists. The canopy classification remains neighbourhood-relative.';

COMMIT;
