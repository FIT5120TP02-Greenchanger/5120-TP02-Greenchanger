BEGIN;

-- Migration 029 exposed metric-specific scopes in this view. Older property
-- lookup code selects DISTINCT version_label/classification_scope, so that
-- produced two copies of every address row. Keep one combined scope across
-- both metric rows while retaining metric-specific explanations and methods.
CREATE OR REPLACE VIEW current_environmental_classification_threshold AS
SELECT
    scheme.classification_scheme_id,
    scheme.version_label,
    scheme.analysis_area_id,
    'fixed_temperature_bands_with_canopy_terciles'::TEXT AS method,
    'fixed_temperature_display_bands_and_versioned_melbourne_canopy_thresholds'::TEXT
        AS classification_scope,
    scheme.calculated_at,
    threshold.metric_code,
    threshold.source_dataset_version_id,
    CASE WHEN threshold.metric_code = 'heat' THEN 27.0
         ELSE threshold.lower_threshold END AS lower_threshold,
    CASE WHEN threshold.metric_code = 'heat' THEN 30.0
         ELSE threshold.upper_threshold END AS upper_threshold,
    threshold.unit,
    threshold.sample_count,
    threshold.low_label,
    threshold.medium_label,
    threshold.high_label,
    threshold.missing_label,
    CASE WHEN threshold.metric_code = 'heat' THEN
        'GreenChanger display bands: Low <=27 C, Medium >27 C and <=30 C, High >30 C. Application-defined only; not a BOM heatwave, health-risk or comfort classification.'
    ELSE threshold.explanation END AS explanation
FROM environmental_classification_scheme AS scheme
JOIN environmental_classification_threshold AS threshold
  USING (classification_scheme_id)
WHERE scheme.status = 'active';

CREATE OR REPLACE FUNCTION search_melbourne_addresses(
    p_address_search TEXT,
    p_result_limit INTEGER DEFAULT 10
)
RETURNS TABLE (
    full_address TEXT,
    normalized_address TEXT,
    address_ids UUID[],
    parcel_ids UUID[],
    parcel_count BIGINT,
    longitude NUMERIC,
    latitude NUMERIC
)
LANGUAGE SQL
STABLE
PARALLEL SAFE
AS $function$
WITH distinct_pairs AS (
    SELECT DISTINCT ON (baseline.address_id, baseline.parcel_id)
        baseline.address_id,
        baseline.parcel_id,
        baseline.full_address,
        normalize_melbourne_address_search(baseline.full_address)
            AS normalized_address,
        baseline.longitude,
        baseline.latitude
    FROM get_property_baseline(
        normalize_melbourne_address_search(p_address_search), 50
    ) AS baseline
    WHERE p_address_search IS NOT NULL
      AND BTRIM(p_address_search) <> ''
    ORDER BY baseline.address_id, baseline.parcel_id
), grouped_addresses AS (
    SELECT
        MIN(distinct_pairs.full_address) AS full_address,
        distinct_pairs.normalized_address,
        ARRAY_AGG(DISTINCT distinct_pairs.address_id)
            FILTER (WHERE distinct_pairs.address_id IS NOT NULL) AS address_ids,
        ARRAY_AGG(DISTINCT distinct_pairs.parcel_id)
            FILTER (WHERE distinct_pairs.parcel_id IS NOT NULL) AS parcel_ids,
        COUNT(DISTINCT distinct_pairs.parcel_id) AS parcel_count,
        MIN(distinct_pairs.longitude) AS longitude,
        MIN(distinct_pairs.latitude) AS latitude
    FROM distinct_pairs
    GROUP BY distinct_pairs.normalized_address
)
SELECT
    grouped_addresses.full_address,
    grouped_addresses.normalized_address,
    grouped_addresses.address_ids,
    grouped_addresses.parcel_ids,
    grouped_addresses.parcel_count,
    grouped_addresses.longitude,
    grouped_addresses.latitude
FROM grouped_addresses
ORDER BY
    CASE WHEN grouped_addresses.normalized_address =
              normalize_melbourne_address_search(p_address_search)
         THEN 0 ELSE 1 END,
    grouped_addresses.full_address
LIMIT LEAST(GREATEST(COALESCE(p_result_limit, 10), 1), 50);
$function$;

COMMENT ON FUNCTION search_melbourne_addresses(TEXT, INTEGER) IS
    'Returns one row per normalized Melbourne address, deduplicates repeated address-parcel joins, and preserves all distinct address and parcel IDs for selection.';

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
    v_address_count INTEGER;
    v_exact_address_count INTEGER;
BEGIN
    IF p_address_search IS NULL OR BTRIM(p_address_search) = '' THEN
        RAISE EXCEPTION 'address search is required';
    END IF;
    v_normalized_search := normalize_melbourne_address_search(p_address_search);

    WITH matches AS MATERIALIZED (
        SELECT address_match.*,
               address_match.normalized_address = v_normalized_search AS is_exact
        FROM search_melbourne_addresses(v_normalized_search, 50) AS address_match
    ), ranked AS (
        SELECT
            matches.*,
            COUNT(*) OVER ()::INTEGER AS address_count,
            COUNT(*) FILTER (WHERE is_exact) OVER ()::INTEGER
                AS exact_address_count,
            ROW_NUMBER() OVER (
                ORDER BY CASE WHEN is_exact THEN 0 ELSE 1 END, full_address
            ) AS match_rank
        FROM matches
    )
    SELECT
        ranked.full_address,
        ranked.longitude::DOUBLE PRECISION,
        ranked.latitude::DOUBLE PRECISION,
        ranked.address_count,
        ranked.exact_address_count
    INTO
        v_matched_address,
        v_longitude,
        v_latitude,
        v_address_count,
        v_exact_address_count
    FROM ranked
    WHERE match_rank = 1;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'no Melbourne address matched: %', BTRIM(p_address_search);
    END IF;
    IF v_exact_address_count = 0 AND v_address_count > 1 THEN
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
    'Normalises abbreviations and resolves one distinct Melbourne address. Repeated joins and multiple parcels sharing that address do not create false ambiguity; genuinely different matching addresses remain ambiguous.';

COMMIT;
