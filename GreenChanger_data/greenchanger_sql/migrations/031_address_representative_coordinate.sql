BEGIN;

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
), ranked_pairs AS (
    SELECT
        distinct_pairs.*,
        ROW_NUMBER() OVER (
            PARTITION BY distinct_pairs.normalized_address
            ORDER BY
                CASE WHEN distinct_pairs.longitude IS NULL
                           OR distinct_pairs.latitude IS NULL THEN 1 ELSE 0 END,
                distinct_pairs.full_address,
                distinct_pairs.address_id,
                distinct_pairs.parcel_id
        ) AS representative_rank
    FROM distinct_pairs
), grouped_addresses AS (
    SELECT
        ranked_pairs.normalized_address,
        ARRAY_AGG(DISTINCT ranked_pairs.address_id)
            FILTER (WHERE ranked_pairs.address_id IS NOT NULL) AS address_ids,
        ARRAY_AGG(DISTINCT ranked_pairs.parcel_id)
            FILTER (WHERE ranked_pairs.parcel_id IS NOT NULL) AS parcel_ids,
        COUNT(DISTINCT ranked_pairs.parcel_id) AS parcel_count
    FROM ranked_pairs
    GROUP BY ranked_pairs.normalized_address
), representative AS (
    SELECT
        ranked_pairs.full_address,
        ranked_pairs.normalized_address,
        ranked_pairs.longitude,
        ranked_pairs.latitude
    FROM ranked_pairs
    WHERE ranked_pairs.representative_rank = 1
)
SELECT
    representative.full_address,
    representative.normalized_address,
    grouped_addresses.address_ids,
    grouped_addresses.parcel_ids,
    grouped_addresses.parcel_count,
    representative.longitude,
    representative.latitude
FROM representative
JOIN grouped_addresses USING (normalized_address)
ORDER BY
    CASE WHEN representative.normalized_address =
              normalize_melbourne_address_search(p_address_search)
         THEN 0 ELSE 1 END,
    representative.full_address
LIMIT LEAST(GREATEST(COALESCE(p_result_limit, 10), 1), 50);
$function$;

COMMENT ON FUNCTION search_melbourne_addresses(TEXT, INTEGER) IS
    'Returns one row per normalized Melbourne address and all distinct parcel options. Full address, longitude and latitude come from the same deterministic representative row; coordinates are never assembled from independent aggregates.';

COMMIT;
