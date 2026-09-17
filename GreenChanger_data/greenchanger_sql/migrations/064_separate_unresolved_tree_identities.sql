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
), classified_species AS (
    SELECT species.*,
           NOT (
               scientific_name ~* '(^|[ ,])sp\.?($|[ ,])'
               OR scientific_name ~* '^(dead|stump)( |$)'
               OR scientific_name ~* '(^| )(unknown|unidentified)( |$)'
               OR scientific_name ~* '(^| )(species|cultivar|varieties)( |$)'
               OR scientific_name LIKE '%,%'
           ) AS has_resolved_tree_identity
    FROM species
), exact_cost AS (
    SELECT LOWER(BTRIM(estimate.botanical_name)) AS species_key,
           MIN(estimate.tree_type) AS priced_tree_type,
           MIN(estimate.minimum_cost) FILTER (WHERE estimate.option_code = 'backyard_tree_diy') AS supply_min_cost_aud,
           MAX(estimate.maximum_cost) FILTER (WHERE estimate.option_code = 'backyard_tree_diy') AS supply_max_cost_aud,
           MIN(estimate.minimum_cost) FILTER (WHERE estimate.option_code = 'backyard_tree_installed') AS installed_min_cost_aud,
           MAX(estimate.maximum_cost) FILTER (WHERE estimate.option_code = 'backyard_tree_installed') AS installed_max_cost_aud,
           MIN(estimate.valid_to) AS cost_valid_to,
           MAX(estimate.last_verified_at) AS cost_last_verified_at,
           ARRAY_AGG(DISTINCT estimate.source_name ORDER BY estimate.source_name) AS cost_source_names,
           ARRAY_AGG(DISTINCT estimate.source_url ORDER BY estimate.source_url)
               FILTER (WHERE estimate.source_url IS NOT NULL) AS cost_source_urls,
           ARRAY_AGG(DISTINCT estimate.stock_size ORDER BY estimate.stock_size)
               FILTER (WHERE estimate.stock_size IS NOT NULL) AS cost_stock_sizes,
           BOOL_OR(estimate.size_price_status IN (
               'exact_variant_size_price', 'exact_listed_size_price',
               'single_product_price_with_size_label'
           )) AS has_size_specific_price
    FROM application_ready_cost_estimate AS estimate
    WHERE estimate.botanical_name IS NOT NULL
      AND estimate.option_code IN ('backyard_tree_diy', 'backyard_tree_installed')
    GROUP BY LOWER(BTRIM(estimate.botanical_name))
)
SELECT species.scientific_name,
       COALESCE(exact_cost.priced_tree_type, species.common_name, species.scientific_name) AS tree_type,
       species.common_name,
       exact_cost.supply_min_cost_aud,
       exact_cost.supply_max_cost_aud,
       exact_cost.installed_min_cost_aud,
       exact_cost.installed_max_cost_aud,
       CASE WHEN exact_cost.species_key IS NOT NULL THEN 'AUD'::TEXT END AS currency,
       exact_cost.cost_valid_to,
       exact_cost.cost_source_names,
       exact_cost.cost_source_urls,
       CASE
           WHEN exact_cost.species_key IS NOT NULL THEN 'species_specific_current_source_range'
           WHEN NOT species.has_resolved_tree_identity THEN 'unavailable_unresolved_tree_identity'
           ELSE 'unavailable_no_species_quote'
       END AS cost_status,
       CASE
           WHEN exact_cost.has_size_specific_price
               THEN 'At least one current supplier price is mapped to an explicit stock size. Confirm current stock, delivery and site suitability with the supplier.'
           WHEN exact_cost.species_key IS NOT NULL
               THEN 'A current species or named-cultivar product price is available, but the supplier data does not map that price to an explicit stock size.'
           WHEN NOT species.has_resolved_tree_identity
               THEN 'The source value is a condition label, genus-only placeholder, duplicated comma label or unresolved identity. Resolve it to one named tree taxon before attaching a species quote.'
           ELSE 'No current species-specific supplier quote is loaded. No generic tree price has been substituted.'
       END AS cost_limitation,
       image.image_url, image.image_page_url, image.image_alt_text,
       image.image_creator, image.image_licence, image.image_licence_url,
       image.image_attribution,
       COALESCE(image.image_status, enrichment.enrichment_status, 'image_enrichment_not_run') AS image_status,
       COALESCE(image.image_limitation, enrichment.limitation,
                'No verified openly licensed image is currently available for this scientific name. Do not substitute an unverified image.') AS image_limitation,
       CASE
           WHEN exact_cost.has_size_specific_price THEN 'species_size_price_available'
           WHEN exact_cost.species_key IS NOT NULL THEN 'species_price_size_unmapped'
           WHEN NOT species.has_resolved_tree_identity THEN 'unavailable_unresolved_tree_identity'
           ELSE 'unavailable_no_species_quote'
       END AS size_price_status,
       exact_cost.cost_stock_sizes,
       exact_cost.cost_last_verified_at
FROM classified_species AS species
LEFT JOIN exact_cost USING (species_key)
LEFT JOIN application_ready_tree_species_image AS image
  ON LOWER(BTRIM(image.scientific_name)) = species.species_key
LEFT JOIN tree_species_image_enrichment AS enrichment
  ON LOWER(BTRIM(enrichment.scientific_name)) = species.species_key;

COMMENT ON VIEW complete_tree_species_catalog IS
    'All distinct named database or priced catalogue species. Missing prices are NULL and explicitly unavailable; unresolved source labels are separated from valid named taxa and no generic catalogue-wide price is substituted.';

COMMIT;
