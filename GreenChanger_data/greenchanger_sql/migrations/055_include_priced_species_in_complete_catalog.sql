BEGIN;

CREATE OR REPLACE VIEW complete_tree_species_catalog AS
WITH species_candidates AS (
    SELECT BTRIM(profile.scientific_name) AS scientific_name,
           NULLIF(BTRIM(profile.common_name), '') AS common_name
    FROM species_profile AS profile
    WHERE NULLIF(BTRIM(profile.scientific_name), '') IS NOT NULL
    UNION ALL
    SELECT BTRIM(estimate.botanical_name),
           NULLIF(BTRIM(estimate.tree_type), '')
    FROM application_ready_cost_estimate AS estimate
    WHERE NULLIF(BTRIM(estimate.botanical_name), '') IS NOT NULL
      AND estimate.option_code IN ('backyard_tree_diy', 'backyard_tree_installed')
), species AS (
    SELECT LOWER(scientific_name) AS species_key,
           MIN(scientific_name) AS scientific_name,
           MIN(common_name) AS common_name
    FROM species_candidates
    GROUP BY LOWER(scientific_name)
), exact_cost AS (
    SELECT LOWER(BTRIM(estimate.botanical_name)) AS species_key,
           MIN(estimate.tree_type) AS priced_tree_type,
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
           MIN(estimate.valid_to) AS cost_valid_to,
           ARRAY_AGG(DISTINCT estimate.source_name ORDER BY estimate.source_name)
               AS cost_source_names,
           ARRAY_AGG(DISTINCT estimate.source_url ORDER BY estimate.source_url)
               AS cost_source_urls
    FROM application_ready_cost_estimate AS estimate
    WHERE estimate.botanical_name IS NOT NULL
      AND estimate.option_code IN ('backyard_tree_diy', 'backyard_tree_installed')
    GROUP BY LOWER(BTRIM(estimate.botanical_name))
), generic_cost AS (
    SELECT MIN(estimate.minimum_cost) FILTER (
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
           MIN(estimate.valid_to) AS cost_valid_to,
           ARRAY_AGG(DISTINCT estimate.source_name ORDER BY estimate.source_name)
               AS cost_source_names,
           ARRAY_AGG(DISTINCT estimate.source_url ORDER BY estimate.source_url)
               AS cost_source_urls
    FROM application_ready_cost_estimate AS estimate
    WHERE estimate.botanical_name IS NOT NULL
      AND estimate.option_code IN ('backyard_tree_diy', 'backyard_tree_installed')
)
SELECT species.scientific_name,
       COALESCE(exact_cost.priced_tree_type, species.common_name,
                species.scientific_name) AS tree_type,
       species.common_name,
       COALESCE(exact_cost.supply_min_cost_aud,
                generic_cost.supply_min_cost_aud) AS supply_min_cost_aud,
       COALESCE(exact_cost.supply_max_cost_aud,
                generic_cost.supply_max_cost_aud) AS supply_max_cost_aud,
       COALESCE(exact_cost.installed_min_cost_aud,
                generic_cost.installed_min_cost_aud) AS installed_min_cost_aud,
       COALESCE(exact_cost.installed_max_cost_aud,
                generic_cost.installed_max_cost_aud) AS installed_max_cost_aud,
       'AUD'::TEXT AS currency,
       COALESCE(exact_cost.cost_valid_to, generic_cost.cost_valid_to)
           AS cost_valid_to,
       COALESCE(exact_cost.cost_source_names, generic_cost.cost_source_names)
           AS cost_source_names,
       COALESCE(exact_cost.cost_source_urls, generic_cost.cost_source_urls)
           AS cost_source_urls,
       CASE WHEN exact_cost.species_key IS NOT NULL
            THEN 'species_specific_current_source_range'
            ELSE 'generic_current_catalogue_range_not_species_quote' END
           AS cost_status,
       CASE WHEN exact_cost.species_key IS NOT NULL
            THEN 'Indicative source-backed species range only; confirm current price, stock, delivery, installation and site conditions with the supplier.'
            ELSE 'No current species-specific supplier price is loaded. This broad fallback is the minimum-to-maximum range across current priced catalogue trees and must not be represented as this species price or as a quote.' END
           AS cost_limitation,
       image.image_url, image.image_page_url, image.image_alt_text,
       image.image_creator, image.image_licence, image.image_licence_url,
       image.image_attribution,
       COALESCE(image.image_status,
                enrichment.enrichment_status,
                'image_enrichment_not_run') AS image_status,
       COALESCE(image.image_limitation, enrichment.limitation,
                'No verified openly licensed image is currently available for this scientific name. Do not substitute an unverified image.')
           AS image_limitation
FROM species
CROSS JOIN generic_cost
LEFT JOIN exact_cost USING (species_key)
LEFT JOIN application_ready_tree_species_image AS image
  ON LOWER(BTRIM(image.scientific_name)) = species.species_key
LEFT JOIN tree_species_image_enrichment AS enrichment
  ON LOWER(BTRIM(enrichment.scientific_name)) = species.species_key;

COMMENT ON VIEW complete_tree_species_catalog IS
    'All distinct named database or currently priced catalogue species. Exact costs and verified images are preserved; missing species prices use a prominently labelled generic current-catalogue range and missing images remain unavailable.';

COMMIT;
