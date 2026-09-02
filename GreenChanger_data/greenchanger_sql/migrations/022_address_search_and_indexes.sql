BEGIN;

-- Cover missing foreign-key and high-frequency filter columns. Primary-key and
-- existing unique/GiST indexes are deliberately not duplicated.
CREATE INDEX IF NOT EXISTS idx_dataset_source_category
    ON dataset_source(source_category);
CREATE INDEX IF NOT EXISTS idx_dataset_version_application_lookup
    ON dataset_version(
        source_id, analysis_area_id, integration_status,
        publication_status, extracted_at DESC
    );
CREATE INDEX IF NOT EXISTS idx_quality_result_rule
    ON data_quality_result(quality_rule_id);
CREATE INDEX IF NOT EXISTS idx_transformation_input_version
    ON transformation_run(input_version_id);
CREATE INDEX IF NOT EXISTS idx_transformation_output_version
    ON transformation_run(output_version_id)
    WHERE output_version_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_integration_run_version
    ON integration_run(dataset_version_id);
CREATE INDEX IF NOT EXISTS idx_data_limitation_version
    ON data_limitation(dataset_version_id);

CREATE INDEX IF NOT EXISTS idx_address_dataset_version
    ON address(dataset_version_id);
CREATE INDEX IF NOT EXISTS idx_address_upper_full_address_prefix
    ON address(UPPER(full_address) text_pattern_ops);
CREATE INDEX IF NOT EXISTS idx_address_postcode_locality
    ON address(postcode, locality_name);
CREATE INDEX IF NOT EXISTS idx_parcel_dataset_version
    ON parcel(dataset_version_id);
CREATE INDEX IF NOT EXISTS idx_site_address
    ON site(address_id) WHERE address_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_site_parcel
    ON site(parcel_id) WHERE parcel_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_weather_version_station_time
    ON weather_observation(dataset_version_id, station_code, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_heat_observation_version
    ON heat_observation(dataset_version_id);
CREATE INDEX IF NOT EXISTS idx_heat_observation_site
    ON heat_observation(site_id) WHERE site_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_vegetation_observation_version
    ON vegetation_observation(dataset_version_id);
CREATE INDEX IF NOT EXISTS idx_vegetation_observation_site
    ON vegetation_observation(site_id) WHERE site_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_canopy_patch_version
    ON canopy_patch(dataset_version_id);
CREATE INDEX IF NOT EXISTS idx_canopy_patch_site
    ON canopy_patch(site_id) WHERE site_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_urban_tree_version_quality
    ON urban_tree(dataset_version_id, quality_status);
CREATE INDEX IF NOT EXISTS idx_urban_tree_site
    ON urban_tree(site_id) WHERE site_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_urban_tree_species
    ON urban_tree(species_id) WHERE species_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_cost_estimate_analysis_area
    ON cost_estimate(analysis_area_id) WHERE analysis_area_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_analysis_run_site_time
    ON analysis_run(site_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_run_dataset_version
    ON analysis_run(dataset_version_id);
CREATE INDEX IF NOT EXISTS idx_analysis_run_model_version
    ON analysis_run(model_version_id) WHERE model_version_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_measure_result_measure
    ON measure_result(measure_id);
CREATE INDEX IF NOT EXISTS idx_measure_test_result_case
    ON measure_test_result(test_case_id);
CREATE INDEX IF NOT EXISTS idx_measure_test_result_model
    ON measure_test_result(model_version_id)
    WHERE model_version_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_model_evidence_evidence
    ON model_evidence(evidence_id);
CREATE INDEX IF NOT EXISTS idx_intervention_parameter_source_evidence
    ON intervention_model_parameter(source_evidence_id)
    WHERE source_evidence_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_intervention_validation_run_model
    ON intervention_model_validation_run(model_version_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_classification_scheme_area_status
    ON environmental_classification_scheme(analysis_area_id, status);
CREATE INDEX IF NOT EXISTS idx_classification_threshold_source_version
    ON environmental_classification_threshold(source_dataset_version_id);
CREATE INDEX IF NOT EXISTS idx_classification_reference_metric
    ON environmental_classification_reference(metric_code, threshold_value);

CREATE OR REPLACE FUNCTION normalize_melbourne_address_search(p_address TEXT)
RETURNS TEXT
LANGUAGE plpgsql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $function$
DECLARE
    v_address TEXT;
BEGIN
    v_address := REGEXP_REPLACE(UPPER(BTRIM(p_address)), '[[:space:]]+', ' ', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mRD\M', 'ROAD', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mAVE\M', 'AVENUE', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mAV\M', 'AVENUE', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mBLVD\M', 'BOULEVARD', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mCRES\M', 'CRESCENT', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mCT\M', 'COURT', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mDR\M', 'DRIVE', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mHWY\M', 'HIGHWAY', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mLN\M', 'LANE', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mPDE\M', 'PARADE', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mPL\M', 'PLACE', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mTCE\M', 'TERRACE', 'g');
    RETURN v_address;
END;
$function$;

COMMENT ON FUNCTION normalize_melbourne_address_search(TEXT) IS
    'Normalises case/whitespace and expands unambiguous Australian street-type abbreviations before Vicmap prefix matching. ST is intentionally not expanded because it can mean Saint, as in St Kilda.';

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
        normalize_melbourne_address_search(p_address_search), p_result_limit
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
    'Returns the property baseline with versioned classifications after expanding supported Australian street-type abbreviations such as RD to ROAD.';

CREATE OR REPLACE FUNCTION get_environment_context_by_address(
    p_address_search TEXT,
    p_radius_m DOUBLE PRECISION DEFAULT 500.0,
    p_layers TEXT[] DEFAULT ARRAY['trees', 'heat']::TEXT[],
    p_result_limit INTEGER DEFAULT 1000
)
RETURNS TABLE (
    layer TEXT,
    feature_id TEXT,
    dataset_version_id UUID,
    distance_m NUMERIC,
    observed_on DATE,
    properties JSONB,
    geometry_geojson JSONB
)
LANGUAGE plpgsql
STABLE
PARALLEL SAFE
AS $function$
DECLARE
    v_normalized_search TEXT;
    v_matched_address TEXT;
    v_longitude DOUBLE PRECISION;
    v_latitude DOUBLE PRECISION;
    v_match_count INTEGER;
    v_exact_match_count INTEGER;
BEGIN
    IF p_address_search IS NULL OR BTRIM(p_address_search) = '' THEN
        RAISE EXCEPTION 'address search is required';
    END IF;
    v_normalized_search := normalize_melbourne_address_search(p_address_search);

    WITH matches AS MATERIALIZED (
        SELECT baseline.*,
               normalize_melbourne_address_search(baseline.full_address) =
                   v_normalized_search AS is_exact
        FROM get_property_baseline(v_normalized_search, 2) AS baseline
    ), ranked AS (
        SELECT
            matches.*,
            COUNT(*) OVER ()::INTEGER AS match_count,
            COUNT(*) FILTER (WHERE is_exact) OVER ()::INTEGER
                AS exact_match_count,
            ROW_NUMBER() OVER (
                ORDER BY
                    CASE WHEN is_exact THEN 0 ELSE 1 END,
                    full_address,
                    address_id
            ) AS match_rank
        FROM matches
    )
    SELECT
        ranked.full_address,
        ranked.longitude::DOUBLE PRECISION,
        ranked.latitude::DOUBLE PRECISION,
        ranked.match_count,
        ranked.exact_match_count
    INTO
        v_matched_address,
        v_longitude,
        v_latitude,
        v_match_count,
        v_exact_match_count
    FROM ranked
    WHERE match_rank = 1;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'no Melbourne address matched: %', BTRIM(p_address_search);
    END IF;
    IF v_exact_match_count > 1
       OR (v_exact_match_count = 0 AND v_match_count > 1) THEN
        RAISE EXCEPTION
            'address search is ambiguous: %. Supply the complete address and postcode',
            BTRIM(p_address_search);
    END IF;
    IF v_longitude IS NULL OR v_latitude IS NULL THEN
        RAISE EXCEPTION 'matched address has no usable coordinate: %', v_matched_address;
    END IF;

    RETURN QUERY
    SELECT context.*
    FROM get_environment_context(
        v_longitude, v_latitude, p_radius_m, p_layers, p_result_limit
    ) AS context;
END;
$function$;

COMMENT ON FUNCTION get_environment_context_by_address(
    TEXT, DOUBLE PRECISION, TEXT[], INTEGER
) IS
    'Normalises supported street abbreviations, resolves one unambiguous Melbourne property address and returns bounded application-ready tree and heat context.';

COMMIT;
