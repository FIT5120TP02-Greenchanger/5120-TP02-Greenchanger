BEGIN;

CREATE TABLE environmental_classification_scheme (
    classification_scheme_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_label TEXT NOT NULL UNIQUE,
    analysis_area_id UUID NOT NULL REFERENCES analysis_area(analysis_area_id),
    method TEXT NOT NULL CHECK (method = 'tercile_percentile_cont'),
    classification_scope TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'active', 'retired')),
    calculated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes TEXT
);

CREATE UNIQUE INDEX environmental_classification_one_active_area
    ON environmental_classification_scheme(analysis_area_id)
    WHERE status = 'active';

CREATE TABLE environmental_classification_threshold (
    classification_threshold_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    classification_scheme_id UUID NOT NULL
        REFERENCES environmental_classification_scheme(classification_scheme_id)
        ON DELETE CASCADE,
    metric_code TEXT NOT NULL CHECK (metric_code IN ('heat', 'canopy')),
    source_dataset_version_id UUID NOT NULL
        REFERENCES dataset_version(dataset_version_id),
    lower_threshold NUMERIC NOT NULL,
    upper_threshold NUMERIC NOT NULL,
    unit TEXT NOT NULL,
    sample_count BIGINT NOT NULL CHECK (sample_count > 0),
    low_label TEXT NOT NULL DEFAULT 'Low',
    medium_label TEXT NOT NULL DEFAULT 'Medium',
    high_label TEXT NOT NULL DEFAULT 'High',
    missing_label TEXT NOT NULL DEFAULT 'Unavailable',
    explanation TEXT NOT NULL,
    CHECK (lower_threshold <= upper_threshold),
    UNIQUE (classification_scheme_id, metric_code)
);

CREATE OR REPLACE VIEW current_environmental_classification_threshold AS
SELECT
    scheme.classification_scheme_id,
    scheme.version_label,
    scheme.analysis_area_id,
    scheme.method,
    scheme.classification_scope,
    scheme.calculated_at,
    threshold.metric_code,
    threshold.source_dataset_version_id,
    threshold.lower_threshold,
    threshold.upper_threshold,
    threshold.unit,
    threshold.sample_count,
    threshold.low_label,
    threshold.medium_label,
    threshold.high_label,
    threshold.missing_label,
    threshold.explanation
FROM environmental_classification_scheme AS scheme
JOIN environmental_classification_threshold AS threshold
  USING (classification_scheme_id)
WHERE scheme.status = 'active';

CREATE OR REPLACE FUNCTION refresh_environmental_classifications(
    p_version_label TEXT
)
RETURNS UUID
LANGUAGE plpgsql
AS $function$
DECLARE
    v_scheme_id UUID;
    v_analysis_area_id UUID;
    v_threshold_count INTEGER;
BEGIN
    IF p_version_label IS NULL OR BTRIM(p_version_label) = '' THEN
        RAISE EXCEPTION 'classification version label is required';
    END IF;
    IF EXISTS (
        SELECT 1 FROM environmental_classification_scheme
        WHERE version_label = BTRIM(p_version_label)
    ) THEN
        RAISE EXCEPTION 'classification version % already exists', BTRIM(p_version_label);
    END IF;

    SELECT analysis_area_id
    INTO STRICT v_analysis_area_id
    FROM analysis_area
    WHERE source_area_code = '2GMEL' AND source_year = 2026;

    INSERT INTO environmental_classification_scheme (
        version_label, analysis_area_id, method, classification_scope,
        status, notes
    ) VALUES (
        BTRIM(p_version_label), v_analysis_area_id,
        'tercile_percentile_cont',
        'relative_to_greater_melbourne_application_ready_baseline',
        'draft',
        'Low is the bottom third, Medium the middle third and High the top third of the selected application-ready Greater Melbourne baseline. Missing values are Unavailable.'
    )
    RETURNING classification_scheme_id INTO v_scheme_id;

    INSERT INTO environmental_classification_threshold (
        classification_scheme_id, metric_code, source_dataset_version_id,
        lower_threshold, upper_threshold, unit, sample_count, explanation
    )
    SELECT
        v_scheme_id,
        'heat',
        dataset_version_id,
        PERCENTILE_CONT(1.0 / 3.0) WITHIN GROUP (
            ORDER BY baseline_surface_temperature_c
        )::NUMERIC,
        PERCENTILE_CONT(2.0 / 3.0) WITHIN GROUP (
            ORDER BY baseline_surface_temperature_c
        )::NUMERIC,
        'degC_land_surface_temperature',
        COUNT(*),
        'Relative to application-ready Greater Melbourne Landsat 500 m baseline cells; this is land-surface temperature, not air temperature.'
    FROM latest_greater_melbourne_heat_baseline
    WHERE baseline_surface_temperature_c IS NOT NULL
    GROUP BY dataset_version_id;

    INSERT INTO environmental_classification_threshold (
        classification_scheme_id, metric_code, source_dataset_version_id,
        lower_threshold, upper_threshold, unit, sample_count, explanation
    )
    SELECT
        v_scheme_id,
        'canopy',
        dataset_version_id,
        PERCENTILE_CONT(1.0 / 3.0) WITHIN GROUP (
            ORDER BY canopy_percentage
        )::NUMERIC,
        PERCENTILE_CONT(2.0 / 3.0) WITHIN GROUP (
            ORDER BY canopy_percentage
        )::NUMERIC,
        'percent_neighbourhood_canopy',
        COUNT(*),
        'Relative to application-ready Greater Melbourne 500 m neighbourhood canopy cells; the current rendered source is a proxy and not property-level canopy.'
    FROM latest_greater_melbourne_canopy_baseline
    WHERE canopy_percentage IS NOT NULL
    GROUP BY dataset_version_id;

    SELECT COUNT(*) INTO v_threshold_count
    FROM environmental_classification_threshold
    WHERE classification_scheme_id = v_scheme_id;

    IF v_threshold_count <> 2 THEN
        RAISE EXCEPTION
            'expected heat and canopy thresholds but calculated % row(s)',
            v_threshold_count;
    END IF;

    UPDATE environmental_classification_scheme
    SET status = 'retired'
    WHERE analysis_area_id = v_analysis_area_id AND status = 'active';

    UPDATE environmental_classification_scheme
    SET status = 'active', calculated_at = CURRENT_TIMESTAMP
    WHERE classification_scheme_id = v_scheme_id;

    RETURN v_scheme_id;
END;
$function$;

CREATE OR REPLACE FUNCTION classify_environmental_value(
    p_metric_code TEXT,
    p_value NUMERIC,
    p_version_label TEXT DEFAULT NULL
)
RETURNS TEXT
LANGUAGE SQL
STABLE
PARALLEL SAFE
RETURN CASE
    WHEN p_value IS NULL THEN 'Unavailable'
    ELSE COALESCE((
        SELECT CASE
            WHEN p_value <= threshold.lower_threshold THEN threshold.low_label
            WHEN p_value <= threshold.upper_threshold THEN threshold.medium_label
            ELSE threshold.high_label
        END
        FROM current_environmental_classification_threshold AS threshold
        WHERE threshold.metric_code = p_metric_code
          AND (p_version_label IS NULL OR threshold.version_label = p_version_label)
        LIMIT 1
    ), 'Unavailable')
END;

COMMENT ON FUNCTION classify_environmental_value(TEXT, NUMERIC, TEXT) IS
    'Returns Low, Medium or High using a versioned Greater Melbourne tercile scheme. Missing values or unavailable thresholds always return Unavailable.';

ALTER FUNCTION get_property_baseline(TEXT, INTEGER)
    RENAME TO get_property_baseline_pre_classification_legacy;

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
    limitations JSONB,
    heat_classification TEXT,
    canopy_classification TEXT,
    classification_scheme_version TEXT,
    classification_scope TEXT
)
LANGUAGE SQL
STABLE
PARALLEL SAFE
AS $function$
WITH baseline AS (
    SELECT *
    FROM get_property_baseline_pre_classification_legacy(
        p_address_search, p_result_limit
    )
), current_scheme AS (
    SELECT DISTINCT version_label, classification_scope
    FROM current_environmental_classification_threshold
)
SELECT
    baseline.*,
    classify_environmental_value(
        'heat', baseline.land_surface_temperature_c, scheme.version_label
    ) AS heat_classification,
    classify_environmental_value(
        'canopy', baseline.neighbourhood_canopy_percentage, scheme.version_label
    ) AS canopy_classification,
    scheme.version_label AS classification_scheme_version,
    scheme.classification_scope
FROM baseline
LEFT JOIN current_scheme AS scheme ON TRUE;
$function$;

COMMENT ON FUNCTION get_property_baseline(TEXT, INTEGER) IS
    'Returns the property baseline plus versioned Greater Melbourne-relative heat and canopy classifications. Missing environmental values always classify as Unavailable.';

COMMIT;
