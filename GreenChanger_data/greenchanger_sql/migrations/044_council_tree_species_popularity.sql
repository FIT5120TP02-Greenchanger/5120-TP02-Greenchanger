BEGIN;

CREATE OR REPLACE FUNCTION get_council_tree_species_popularity_by_address(
    p_address_search TEXT,
    p_result_limit INTEGER DEFAULT 20
)
RETURNS TABLE (
    council_code TEXT,
    council_name TEXT,
    popularity_rank BIGINT,
    list_category TEXT,
    scientific_name TEXT,
    common_name TEXT,
    display_name TEXT,
    recorded_tree_count BIGINT,
    recorded_tree_percentage NUMERIC,
    median_height_m NUMERIC,
    median_canopy_width_m NUMERIC,
    guidance_status TEXT,
    source_names TEXT[],
    licences TEXT[],
    latest_source_observed_on DATE,
    status TEXT,
    limitation TEXT
)
LANGUAGE plpgsql
STABLE
AS $function$
DECLARE
    v_normalized_search TEXT;
    v_longitude DOUBLE PRECISION;
    v_latitude DOUBLE PRECISION;
    v_match_count INTEGER;
    v_exact_count INTEGER;
    v_lga latest_victorian_lga_boundary%ROWTYPE;
BEGIN
    IF p_address_search IS NULL OR BTRIM(p_address_search) = '' THEN
        RAISE EXCEPTION 'address search is required';
    END IF;
    IF p_result_limit <= 0 OR p_result_limit > 100 THEN
        RAISE EXCEPTION 'result_limit must be between 1 and 100';
    END IF;

    v_normalized_search := normalize_melbourne_address_search(p_address_search);
    WITH matches AS MATERIALIZED (
        SELECT match.*,
               match.normalized_address = v_normalized_search AS is_exact
        FROM search_melbourne_addresses(v_normalized_search, 50) AS match
    ), ranked AS (
        SELECT matches.*,
               COUNT(*) OVER ()::INTEGER AS match_count,
               COUNT(*) FILTER (WHERE is_exact) OVER ()::INTEGER AS exact_count,
               ROW_NUMBER() OVER (
                   ORDER BY CASE WHEN is_exact THEN 0 ELSE 1 END, full_address
               ) AS match_rank
        FROM matches
    )
    SELECT longitude::DOUBLE PRECISION, latitude::DOUBLE PRECISION,
           match_count, exact_count
    INTO v_longitude, v_latitude, v_match_count, v_exact_count
    FROM ranked
    WHERE match_rank = 1;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'no Melbourne address matched: %', BTRIM(p_address_search);
    END IF;
    IF v_exact_count = 0 AND v_match_count > 1 THEN
        RAISE EXCEPTION
            'address search is ambiguous: %. Supply the complete address and postcode',
            BTRIM(p_address_search);
    END IF;

    SELECT boundary.* INTO v_lga
    FROM latest_victorian_lga_boundary AS boundary
    WHERE ST_Covers(
        boundary.boundary_geometry,
        ST_Transform(ST_SetSRID(ST_MakePoint(v_longitude, v_latitude), 4326), 7855)
    )
    ORDER BY boundary.area_m2, boundary.lga_code
    LIMIT 1;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'matched address is outside the loaded Victorian LGA boundaries';
    END IF;

    RETURN QUERY
    WITH inventory_rows AS MATERIALIZED (
        SELECT
            tree.*,
            CASE
                WHEN NULLIF(BTRIM(tree.scientific_name), '') IS NOT NULL
                    THEN 'scientific:' || LOWER(BTRIM(tree.scientific_name))
                ELSE 'common:' || LOWER(BTRIM(tree.common_name))
            END AS species_key,
            COALESCE(
                tree.height_m,
                CASE
                    WHEN tree.height_min_m IS NOT NULL
                     AND tree.height_max_m IS NOT NULL
                    THEN (tree.height_min_m + tree.height_max_m) / 2.0
                END
            ) AS representative_height_m,
            COALESCE(
                tree.canopy_width_m,
                CASE
                    WHEN tree.canopy_width_min_m IS NOT NULL
                     AND tree.canopy_width_max_m IS NOT NULL
                    THEN (tree.canopy_width_min_m + tree.canopy_width_max_m) / 2.0
                END
            ) AS representative_canopy_width_m
        FROM latest_metropolitan_named_tree_inventory AS tree
        WHERE ST_Covers(v_lga.boundary_geometry, tree.tree_location)
          AND COALESCE(
                  NULLIF(BTRIM(tree.scientific_name), ''),
                  NULLIF(BTRIM(tree.common_name), '')
              ) IS NOT NULL
    ), species_counts AS (
        SELECT
            rows.species_key,
            MIN(NULLIF(BTRIM(rows.scientific_name), '')) AS scientific_name,
            MIN(NULLIF(BTRIM(rows.common_name), '')) AS common_name,
            MIN(NULLIF(BTRIM(rows.display_name), '')) AS display_name,
            COUNT(*)::BIGINT AS recorded_tree_count,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
                ORDER BY rows.representative_height_m
            )::NUMERIC, 2) AS median_height_m,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (
                ORDER BY rows.representative_canopy_width_m
            )::NUMERIC, 2) AS median_canopy_width_m,
            ARRAY_AGG(DISTINCT rows.source_name ORDER BY rows.source_name)
                AS source_names,
            ARRAY_AGG(DISTINCT rows.licence ORDER BY rows.licence)
                AS licences,
            MAX(rows.source_observed_on) AS latest_source_observed_on
        FROM inventory_rows AS rows
        GROUP BY rows.species_key
    ), guidance AS (
        SELECT
            item.scientific_name,
            item.common_name,
            ARRAY_AGG(DISTINCT item.guidance_status ORDER BY item.guidance_status)
                AS statuses
        FROM latest_council_species_guidance AS item
        WHERE item.lga_code = v_lga.lga_code
        GROUP BY item.scientific_name, item.common_name
    ), enriched AS (
        SELECT
            counts.*,
            matched_guidance.statuses AS guidance_statuses,
            CASE
                WHEN matched_guidance.statuses && ARRAY['not_recommended']::TEXT[]
                    THEN 'not_recommended'
                WHEN matched_guidance.statuses &&
                     ARRAY['conditional', 'approval_required']::TEXT[]
                    THEN 'council_approval_required'
                WHEN matched_guidance.statuses &&
                     ARRAY['approved', 'recommended']::TEXT[]
                    THEN 'available_now'
                ELSE 'council_approval_required'
            END AS list_category
        FROM species_counts AS counts
        LEFT JOIN LATERAL (
            SELECT ARRAY_AGG(DISTINCT status ORDER BY status) AS statuses
            FROM (
                SELECT UNNEST(item.statuses) AS status
                FROM guidance AS item
                WHERE (
                    counts.scientific_name IS NOT NULL
                    AND item.scientific_name IS NOT NULL
                    AND LOWER(BTRIM(item.scientific_name)) =
                        LOWER(BTRIM(counts.scientific_name))
                ) OR (
                    counts.scientific_name IS NULL
                    AND counts.common_name IS NOT NULL
                    AND item.common_name IS NOT NULL
                    AND LOWER(BTRIM(item.common_name)) =
                        LOWER(BTRIM(counts.common_name))
                )
            ) AS matched(status)
        ) AS matched_guidance ON TRUE
    ), ranked_species AS (
        SELECT
            enriched.*,
            ROW_NUMBER() OVER (
                ORDER BY enriched.recorded_tree_count DESC,
                         COALESCE(enriched.common_name, enriched.scientific_name),
                         enriched.species_key
            ) AS popularity_rank,
            ROUND(
                100.0 * enriched.recorded_tree_count /
                NULLIF(SUM(enriched.recorded_tree_count) OVER (), 0),
                2
            ) AS recorded_tree_percentage
        FROM enriched
    ), result_rows AS (
        SELECT
            v_lga.lga_code AS council_code,
            v_lga.lga_official_name AS council_name,
            ranked_species.popularity_rank,
            ranked_species.list_category,
            ranked_species.scientific_name,
            ranked_species.common_name,
            COALESCE(
                ranked_species.common_name,
                ranked_species.scientific_name,
                ranked_species.display_name
            ) AS display_name,
            ranked_species.recorded_tree_count,
            ranked_species.recorded_tree_percentage,
            ranked_species.median_height_m,
            ranked_species.median_canopy_width_m,
            CASE
                WHEN ranked_species.guidance_statuses IS NULL THEN 'not_in_loaded_guidance'
                ELSE ARRAY_TO_STRING(ranked_species.guidance_statuses, ',')
            END AS guidance_status,
            ranked_species.source_names,
            ranked_species.licences,
            ranked_species.latest_source_observed_on,
            'observed_public_tree_frequency'::TEXT AS status,
            'Popularity is frequency among latest application-ready council-maintained public-tree inventory records inside the LGA. It is not resident preference, planting approval, nursery availability, private-tree prevalence or property suitability. Council source completeness and dates vary.'::TEXT AS limitation
        FROM ranked_species
        WHERE ranked_species.popularity_rank <= p_result_limit
    )
    SELECT * FROM result_rows
    UNION ALL
    SELECT
        v_lga.lga_code,
        v_lga.lga_official_name,
        NULL::BIGINT,
        'unavailable'::TEXT,
        NULL::TEXT,
        NULL::TEXT,
        NULL::TEXT,
        0::BIGINT,
        NULL::NUMERIC,
        NULL::NUMERIC,
        NULL::NUMERIC,
        'unavailable'::TEXT,
        ARRAY[]::TEXT[],
        ARRAY[]::TEXT[],
        NULL::DATE,
        'unavailable_no_integrated_council_inventory'::TEXT,
        'No latest application-ready named public-tree inventory covers this council. Absence of an integrated source does not mean no trees exist.'::TEXT
    WHERE NOT EXISTS (SELECT 1 FROM result_rows)
    ORDER BY popularity_rank NULLS LAST;
END;
$function$;

COMMENT ON FUNCTION get_council_tree_species_popularity_by_address(TEXT, INTEGER) IS
    'Ranks species by frequency in latest application-ready council public-tree inventories within the address LGA; guidance status remains separate and frequency never implies planting approval or site suitability.';

COMMIT;
