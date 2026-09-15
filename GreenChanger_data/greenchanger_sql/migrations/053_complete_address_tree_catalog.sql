BEGIN;

CREATE OR REPLACE FUNCTION get_tree_planting_catalog_by_address(
    p_address_search TEXT,
    p_result_limit INTEGER DEFAULT 20
)
RETURNS TABLE (
    council_code TEXT, council_name TEXT, list_category TEXT,
    guidance_status TEXT, tree_type TEXT, scientific_name TEXT,
    mature_size_class TEXT, supply_min_cost_aud NUMERIC,
    supply_max_cost_aud NUMERIC, installed_min_cost_aud NUMERIC,
    installed_max_cost_aud NUMERIC, currency TEXT, cost_valid_to DATE,
    cost_source_names TEXT[], cost_source_urls TEXT[], cost_status TEXT,
    cost_limitation TEXT, image_url TEXT, image_page_url TEXT,
    image_alt_text TEXT, image_creator TEXT, image_licence TEXT,
    image_licence_url TEXT, image_attribution TEXT, image_status TEXT,
    image_limitation TEXT, guidance_source_url TEXT,
    guidance_limitation TEXT
)
LANGUAGE SQL
STABLE
AS $function$
WITH popularity AS MATERIALIZED (
    SELECT *
    FROM get_council_tree_species_popularity_by_address(
        p_address_search, LEAST(p_result_limit, 100)
    )
), council AS (
    SELECT popularity.council_code, popularity.council_name
    FROM popularity
    LIMIT 1
), proposed AS (
    SELECT LOWER(BTRIM(popularity.scientific_name)) AS species_key,
           popularity.popularity_rank,
           popularity.list_category,
           popularity.guidance_status
    FROM popularity
    WHERE popularity.scientific_name IS NOT NULL
    UNION ALL
    SELECT LOWER(BTRIM(catalog.scientific_name)), NULL::BIGINT,
           'council_approval_required', 'not_in_loaded_guidance'
    FROM complete_tree_species_catalog AS catalog
    WHERE catalog.cost_status = 'species_specific_current_source_range'
), candidates AS (
    SELECT DISTINCT ON (proposed.species_key)
           proposed.species_key, proposed.popularity_rank,
           proposed.list_category, proposed.guidance_status
    FROM proposed
    ORDER BY proposed.species_key, proposed.popularity_rank NULLS LAST
)
SELECT council.council_code, council.council_name,
       CASE WHEN guidance.guidance_status IN ('approved', 'recommended')
            THEN 'available_now'
            ELSE candidates.list_category END AS list_category,
       COALESCE(guidance.guidance_status, candidates.guidance_status,
                'not_in_loaded_guidance') AS guidance_status,
       catalog.tree_type, catalog.scientific_name,
       guidance.mature_size_class,
       catalog.supply_min_cost_aud, catalog.supply_max_cost_aud,
       catalog.installed_min_cost_aud, catalog.installed_max_cost_aud,
       catalog.currency, catalog.cost_valid_to,
       catalog.cost_source_names, catalog.cost_source_urls,
       catalog.cost_status, catalog.cost_limitation,
       catalog.image_url, catalog.image_page_url, catalog.image_alt_text,
       catalog.image_creator, catalog.image_licence,
       catalog.image_licence_url, catalog.image_attribution,
       catalog.image_status, catalog.image_limitation,
       guidance.source_url,
       COALESCE(
           guidance.limitation,
           'This species is not present in the latest loaded guidance for the address council. Confirm suitability, availability and any permit or approval requirement directly with the council before planting.'
       ) AS guidance_limitation
FROM candidates
JOIN complete_tree_species_catalog AS catalog
  ON LOWER(BTRIM(catalog.scientific_name)) = candidates.species_key
CROSS JOIN council
LEFT JOIN LATERAL (
    SELECT item.guidance_status, item.mature_size_class,
           item.source_url, item.limitation
    FROM latest_council_species_guidance AS item
    WHERE item.lga_code = council.council_code
      AND (
          LOWER(BTRIM(COALESCE(item.scientific_name, ''))) =
              LOWER(BTRIM(catalog.scientific_name))
          OR LOWER(BTRIM(COALESCE(item.common_name, ''))) =
              LOWER(BTRIM(catalog.tree_type))
      )
    ORDER BY CASE item.guidance_status
                 WHEN 'approved' THEN 0 WHEN 'recommended' THEN 1
                 WHEN 'conditional' THEN 2
                 WHEN 'approval_required' THEN 3 ELSE 4
             END,
             item.effective_from DESC,
             item.council_species_guidance_id
    LIMIT 1
) AS guidance ON TRUE
ORDER BY
    CASE WHEN guidance.guidance_status IN ('approved', 'recommended')
         THEN 0 ELSE 1 END,
    CASE catalog.cost_status
         WHEN 'species_specific_current_source_range' THEN 0 ELSE 1 END,
    candidates.popularity_rank NULLS LAST,
    catalog.tree_type
LIMIT p_result_limit;
$function$;

COMMENT ON FUNCTION get_tree_planting_catalog_by_address(TEXT, INTEGER) IS
    'Frontend-ready address catalogue: exact-price catalogue stock plus locally popular or metropolitan-fallback species. Every row distinguishes species-specific from generic cost evidence and verified from unavailable image evidence; none implies site suitability or council approval.';

COMMIT;
