BEGIN;

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
    v_matched_address TEXT;
    v_longitude DOUBLE PRECISION;
    v_latitude DOUBLE PRECISION;
    v_match_count INTEGER;
    v_exact_match_count INTEGER;
BEGIN
    IF p_address_search IS NULL OR BTRIM(p_address_search) = '' THEN
        RAISE EXCEPTION 'address search is required';
    END IF;

    WITH matches AS MATERIALIZED (
        SELECT baseline.*,
               UPPER(BTRIM(baseline.full_address)) =
                   UPPER(BTRIM(p_address_search)) AS is_exact
        FROM get_property_baseline(p_address_search, 2) AS baseline
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
        v_longitude,
        v_latitude,
        p_radius_m,
        p_layers,
        p_result_limit
    ) AS context;
END;
$function$;

COMMENT ON FUNCTION get_environment_context_by_address(
    TEXT, DOUBLE PRECISION, TEXT[], INTEGER
) IS
    'Resolves one unambiguous Melbourne property address and returns the application-ready mapped-tree and Landsat heat context within the requested radius.';

COMMIT;
