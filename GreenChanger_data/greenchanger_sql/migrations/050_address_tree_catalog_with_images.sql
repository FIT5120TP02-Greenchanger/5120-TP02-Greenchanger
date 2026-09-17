BEGIN;

CREATE TABLE tree_species_image (
    tree_species_image_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tree_type TEXT NOT NULL,
    scientific_name TEXT NOT NULL,
    image_url TEXT NOT NULL CHECK (image_url ~ '^https://'),
    image_page_url TEXT NOT NULL CHECK (image_page_url ~ '^https://'),
    image_alt_text TEXT NOT NULL,
    image_creator TEXT NOT NULL,
    image_licence TEXT NOT NULL,
    image_licence_url TEXT NOT NULL CHECK (image_licence_url ~ '^https://'),
    image_attribution TEXT NOT NULL,
    source_name TEXT NOT NULL,
    last_verified_at TIMESTAMPTZ NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tree_type, scientific_name)
);

COMMENT ON TABLE tree_species_image IS
    'Curated tree catalogue images with reusable licence, creator and source-page attribution. Remote image availability is not guaranteed.';

INSERT INTO tree_species_image (
    tree_type, scientific_name, image_url, image_page_url, image_alt_text,
    image_creator, image_licence, image_licence_url, image_attribution,
    source_name, last_verified_at
)
VALUES
    ('Water Gum', 'Tristaniopsis laurina',
     'https://commons.wikimedia.org/wiki/Special:FilePath/Tristaniopsis_laurina-tree.jpg?width=800',
     'https://commons.wikimedia.org/wiki/File:Tristaniopsis_laurina-tree.jpg',
     'A mature Water Gum (Tristaniopsis laurina) growing as a street tree.',
     'Eug', 'Public domain',
     'https://creativecommons.org/publicdomain/mark/1.0/',
     'Water Gum photograph by Eug, public domain, via Wikimedia Commons.',
     'Wikimedia Commons', TIMESTAMPTZ '2026-09-15 00:00:00+10'),
    ('Lemon-scented Gum', 'Corymbia citriodora',
     'https://commons.wikimedia.org/wiki/Special:FilePath/Citirodora.jpg?width=800',
     'https://commons.wikimedia.org/wiki/File:Citirodora.jpg',
     'A mature Lemon-scented Gum (Corymbia citriodora) in Ringwood East, Victoria.',
     'HelloMojo', 'Public domain',
     'https://creativecommons.org/publicdomain/mark/1.0/',
     'Lemon-scented Gum photograph by HelloMojo, public domain, via Wikimedia Commons.',
     'Wikimedia Commons', TIMESTAMPTZ '2026-09-15 00:00:00+10'),
    ('Crepe Myrtle', 'Lagerstroemia indica',
     'https://commons.wikimedia.org/wiki/Special:FilePath/Lagerstroemia_indica.jpg?width=800',
     'https://commons.wikimedia.org/wiki/File:Lagerstroemia_indica.jpg',
     'A flowering Crepe Myrtle (Lagerstroemia indica).',
     'HelloMojo', 'Public domain',
     'https://creativecommons.org/publicdomain/mark/1.0/',
     'Crepe Myrtle photograph by HelloMojo, public domain, via Wikimedia Commons.',
     'Wikimedia Commons', TIMESTAMPTZ '2026-09-15 00:00:00+10');

CREATE OR REPLACE VIEW application_ready_tree_species_image AS
SELECT tree_species_image_id, tree_type, scientific_name, image_url,
       image_page_url, image_alt_text, image_creator, image_licence,
       image_licence_url, image_attribution, source_name, last_verified_at,
       'reference_image_not_exact_stock'::TEXT AS image_status,
       'Reference image only; appearance varies with age, season, cultivar and growing conditions. Verify remote availability and retain the supplied attribution.'::TEXT AS image_limitation
FROM tree_species_image
WHERE active;

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
      FROM ranked WHERE match_rank = 1;

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
    WITH current_catalog_cost AS (
        SELECT estimate.tree_type,
               estimate.botanical_name AS scientific_name,
               MIN(estimate.minimum_cost) FILTER (
                   WHERE estimate.option_code = 'backyard_tree_diy'
               ) AS supply_min_cost_aud,
               MAX(estimate.maximum_cost) FILTER (
                   WHERE estimate.option_code = 'backyard_tree_diy'
               ) AS supply_max_cost_aud,
               MIN(estimate.minimum_cost) FILTER (
                   WHERE estimate.option_code = 'backyard_tree_installed'
               ) AS installed_min_cost_aud,
               MAX(estimate.maximum_cost) FILTER (
                   WHERE estimate.option_code = 'backyard_tree_installed'
               ) AS installed_max_cost_aud,
               MIN(estimate.currency) AS currency,
               MIN(estimate.valid_to) AS cost_valid_to,
               ARRAY_AGG(DISTINCT estimate.source_name ORDER BY estimate.source_name)
                   AS cost_source_names,
               ARRAY_AGG(DISTINCT estimate.source_url ORDER BY estimate.source_url)
                   AS cost_source_urls,
               MIN(estimate.estimate_status) AS cost_status,
               MIN(estimate.display_disclaimer) AS cost_limitation
        FROM application_ready_cost_estimate AS estimate
        WHERE estimate.tree_type IS NOT NULL
          AND estimate.botanical_name IS NOT NULL
          AND estimate.option_code IN ('backyard_tree_diy', 'backyard_tree_installed')
        GROUP BY estimate.tree_type, estimate.botanical_name
        HAVING COUNT(*) FILTER (
                   WHERE estimate.option_code = 'backyard_tree_diy'
               ) > 0
           AND COUNT(*) FILTER (
                   WHERE estimate.option_code = 'backyard_tree_installed'
               ) > 0
    )
    SELECT v_lga.lga_code, v_lga.lga_official_name,
           CASE WHEN guidance.guidance_status IN ('approved', 'recommended')
                THEN 'available_now' ELSE 'council_approval_required' END,
           COALESCE(guidance.guidance_status, 'not_in_loaded_guidance'),
           cost.tree_type, cost.scientific_name, guidance.mature_size_class,
           cost.supply_min_cost_aud, cost.supply_max_cost_aud,
           cost.installed_min_cost_aud, cost.installed_max_cost_aud,
           cost.currency, cost.cost_valid_to, cost.cost_source_names,
           cost.cost_source_urls, cost.cost_status, cost.cost_limitation,
           image.image_url, image.image_page_url, image.image_alt_text,
           image.image_creator, image.image_licence, image.image_licence_url,
           image.image_attribution, image.image_status, image.image_limitation,
           guidance.source_url,
           COALESCE(
               guidance.limitation,
               'This species is not present in the latest loaded guidance for the address council. Confirm suitability, availability and any permit or approval requirement directly with the council before planting.'
           )
    FROM current_catalog_cost AS cost
    JOIN application_ready_tree_species_image AS image
      ON LOWER(BTRIM(image.tree_type)) = LOWER(BTRIM(cost.tree_type))
     AND LOWER(BTRIM(image.scientific_name)) = LOWER(BTRIM(cost.scientific_name))
    LEFT JOIN LATERAL (
        SELECT item.guidance_status, item.mature_size_class,
               item.source_url, item.limitation
        FROM latest_council_species_guidance AS item
        WHERE item.lga_code = v_lga.lga_code
          AND (
              LOWER(BTRIM(COALESCE(item.scientific_name, ''))) =
                  LOWER(BTRIM(cost.scientific_name))
              OR LOWER(BTRIM(COALESCE(item.common_name, ''))) =
                  LOWER(BTRIM(cost.tree_type))
              OR (
                  LOWER(BTRIM(cost.scientific_name)) = 'lagerstroemia indica'
                  AND LOWER(BTRIM(COALESCE(item.scientific_name, '')))
                      LIKE 'lagerstroemia%'
              )
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
    ORDER BY CASE WHEN guidance.guidance_status IN ('approved', 'recommended')
                  THEN 0 ELSE 1 END,
             cost.tree_type
    LIMIT p_result_limit;
END;
$function$;

COMMENT ON VIEW application_ready_tree_species_image IS
    'Active catalogue reference images with public reuse metadata and mandatory display limitation.';
COMMENT ON FUNCTION get_tree_planting_catalog_by_address(TEXT, INTEGER) IS
    'Resolves a Melbourne address to its LGA and returns cost-supported catalogue trees with council guidance status, current AUD supply and installed ranges, and licensed image attribution. A catalogue row is not proof of site suitability, nursery availability or council approval.';

COMMIT;
