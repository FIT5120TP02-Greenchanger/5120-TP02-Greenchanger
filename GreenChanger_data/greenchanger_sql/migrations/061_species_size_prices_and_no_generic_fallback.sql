BEGIN;

ALTER TABLE cost_estimate
    ADD COLUMN IF NOT EXISTS species_price_match_basis TEXT,
    ADD COLUMN IF NOT EXISTS size_price_status TEXT;

ALTER TABLE cost_estimate
    DROP CONSTRAINT IF EXISTS cost_estimate_species_price_match_basis_check,
    DROP CONSTRAINT IF EXISTS cost_estimate_size_price_status_check;

ALTER TABLE cost_estimate
    ADD CONSTRAINT cost_estimate_species_price_match_basis_check CHECK (
        species_price_match_basis IS NULL OR species_price_match_basis IN (
            'exact_catalogue_name', 'species_or_cultivar_listing'
        )
    ),
    ADD CONSTRAINT cost_estimate_size_price_status_check CHECK (
        size_price_status IS NULL OR size_price_status IN (
            'exact_variant_size_price', 'exact_listed_size_price',
            'single_product_price_with_size_label',
            'exact_variant_price_size_not_supplied',
            'single_product_price_size_not_supplied',
            'product_price_range_not_mapped_to_size'
        )
    );

COMMENT ON COLUMN cost_estimate.species_price_match_basis IS
    'Whether the supplier listing names the catalogue taxon exactly or is a named cultivar belonging to that species.';
COMMENT ON COLUMN cost_estimate.size_price_status IS
    'Whether the advertised price is mapped to an explicit supplier stock size or remains an unmapped product-level price.';

DROP INDEX IF EXISTS uq_cost_estimate_source_version;
CREATE UNIQUE INDEX uq_cost_estimate_source_version
    ON cost_estimate (
        greening_option_id, cost_context, cost_basis, tree_type, stock_size,
        source_name, valid_from, source_reference
    ) NULLS NOT DISTINCT;

CREATE OR REPLACE VIEW application_ready_cost_estimate AS
SELECT
    ce.cost_estimate_id,
    go.option_code,
    go.option_name,
    go.option_category,
    go.cost_unit,
    ce.cost_context,
    ce.cost_basis,
    ce.tree_size_category,
    ce.planting_method,
    ce.stock_size,
    ce.minimum_cost,
    ce.maximum_cost,
    ce.material_min_cost,
    ce.material_max_cost,
    ce.installation_min_cost,
    ce.installation_max_cost,
    ce.delivery_min_cost,
    ce.delivery_max_cost,
    ce.setup_min_cost,
    ce.setup_max_cost,
    ce.currency,
    ce.gst_included,
    ce.includes_installation,
    ce.annual_maintenance_cost,
    ce.source_name,
    ce.source_reference,
    ce.source_url,
    ce.valid_from,
    ce.valid_to,
    ce.last_verified_at,
    ce.confidence_level,
    'indicative_not_quote'::TEXT AS estimate_status,
    'Indicative source-backed range only; confirm current price, availability, site conditions, delivery, installation and maintenance with the supplier.'::TEXT
        AS display_disclaimer,
    ce.tree_type,
    ce.botanical_name,
    ce.species_price_match_basis,
    ce.size_price_status
FROM cost_estimate AS ce
JOIN greening_option AS go USING (greening_option_id)
WHERE go.active
  AND ce.valid_from <= (CURRENT_TIMESTAMP AT TIME ZONE 'Australia/Melbourne')::DATE
  AND (
      ce.valid_to IS NULL
      OR ce.valid_to >= (CURRENT_TIMESTAMP AT TIME ZONE 'Australia/Melbourne')::DATE
  );

CREATE OR REPLACE VIEW application_ready_tree_cost_by_size AS
SELECT
    cost_estimate_id, option_code, tree_type, botanical_name, stock_size,
    minimum_cost, maximum_cost, currency, source_name, source_reference,
    source_url, valid_from, valid_to, last_verified_at,
    species_price_match_basis, size_price_status, confidence_level,
    estimate_status, display_disclaimer
FROM application_ready_cost_estimate
WHERE option_code = 'backyard_tree_diy'
  AND botanical_name IS NOT NULL
  AND size_price_status IN (
      'exact_variant_size_price', 'exact_listed_size_price',
      'single_product_price_with_size_label'
  );

COMMENT ON VIEW application_ready_tree_cost_by_size IS
    'Current supplier tree prices where an advertised AUD price is explicitly paired with a supplier stock size; generic tree prices and unmapped product ranges are excluded.';

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
           MAX(estimate.last_verified_at) AS cost_last_verified_at,
           ARRAY_AGG(DISTINCT estimate.source_name ORDER BY estimate.source_name)
               AS cost_source_names,
           ARRAY_AGG(DISTINCT estimate.source_url ORDER BY estimate.source_url)
               FILTER (WHERE estimate.source_url IS NOT NULL)
               AS cost_source_urls,
           ARRAY_AGG(DISTINCT estimate.stock_size ORDER BY estimate.stock_size)
               FILTER (WHERE estimate.stock_size IS NOT NULL)
               AS cost_stock_sizes,
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
       COALESCE(exact_cost.priced_tree_type, species.common_name,
                species.scientific_name) AS tree_type,
       species.common_name,
       exact_cost.supply_min_cost_aud,
       exact_cost.supply_max_cost_aud,
       exact_cost.installed_min_cost_aud,
       exact_cost.installed_max_cost_aud,
       CASE WHEN exact_cost.species_key IS NOT NULL THEN 'AUD'::TEXT END
           AS currency,
       exact_cost.cost_valid_to,
       exact_cost.cost_source_names,
       exact_cost.cost_source_urls,
       CASE WHEN exact_cost.species_key IS NOT NULL
            THEN 'species_specific_current_source_range'
            ELSE 'unavailable_no_species_quote' END AS cost_status,
       CASE
           WHEN exact_cost.has_size_specific_price
               THEN 'At least one current supplier price is mapped to an explicit stock size. Confirm current stock, delivery and site suitability with the supplier.'
           WHEN exact_cost.species_key IS NOT NULL
               THEN 'A current species or named-cultivar product price is available, but the supplier data does not map that price to an explicit stock size.'
           ELSE 'No current species-specific supplier quote is loaded. No generic tree price has been substituted.'
       END AS cost_limitation,
       image.image_url, image.image_page_url, image.image_alt_text,
       image.image_creator, image.image_licence, image.image_licence_url,
       image.image_attribution,
       COALESCE(image.image_status,
                enrichment.enrichment_status,
                'image_enrichment_not_run') AS image_status,
       COALESCE(image.image_limitation, enrichment.limitation,
                'No verified openly licensed image is currently available for this scientific name. Do not substitute an unverified image.')
           AS image_limitation,
       CASE
           WHEN exact_cost.has_size_specific_price
               THEN 'species_size_price_available'
           WHEN exact_cost.species_key IS NOT NULL
               THEN 'species_price_size_unmapped'
           ELSE 'unavailable_no_species_quote'
       END AS size_price_status,
       exact_cost.cost_stock_sizes,
       exact_cost.cost_last_verified_at
FROM species
LEFT JOIN exact_cost USING (species_key)
LEFT JOIN application_ready_tree_species_image AS image
  ON LOWER(BTRIM(image.scientific_name)) = species.species_key
LEFT JOIN tree_species_image_enrichment AS enrichment
  ON LOWER(BTRIM(enrichment.scientific_name)) = species.species_key;

COMMENT ON VIEW complete_tree_species_catalog IS
    'All distinct named database or priced catalogue species. Missing prices are NULL and explicitly unavailable; no generic catalogue-wide price is substituted. Size-specific and unmapped supplier prices are distinguished.';

COMMIT;
