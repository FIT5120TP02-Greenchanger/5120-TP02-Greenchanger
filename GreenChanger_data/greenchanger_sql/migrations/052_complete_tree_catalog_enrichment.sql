BEGIN;

INSERT INTO dataset_source (
    source_name, publisher, source_url, licence, licence_status,
    source_category, geographic_coverage, access_method, update_frequency
)
VALUES (
    'GBIF occurrence media API', 'Global Biodiversity Information Facility',
    'https://techdocs.gbif.org/en/openapi/v1/occurrence',
    'Record-level CC0, CC BY 4.0 or CC BY-SA 4.0 only', 'open_confirmed',
    'species_reference_image', 'Global', 'GBIF REST API', 'on demand'
)
ON CONFLICT (source_name, publisher) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    licence = EXCLUDED.licence,
    licence_status = EXCLUDED.licence_status,
    source_category = EXCLUDED.source_category,
    geographic_coverage = EXCLUDED.geographic_coverage,
    access_method = EXCLUDED.access_method,
    update_frequency = EXCLUDED.update_frequency;

CREATE TABLE tree_species_image_enrichment (
    scientific_name TEXT PRIMARY KEY,
    gbif_taxon_key BIGINT,
    matched_scientific_name TEXT,
    taxon_rank TEXT,
    taxonomic_status TEXT,
    match_type TEXT,
    match_confidence INTEGER CHECK (
        match_confidence IS NULL OR match_confidence BETWEEN 0 AND 100
    ),
    image_url TEXT CHECK (image_url IS NULL OR image_url ~ '^https://'),
    image_page_url TEXT CHECK (
        image_page_url IS NULL OR image_page_url ~ '^https://'
    ),
    image_alt_text TEXT,
    image_creator TEXT,
    image_rights_holder TEXT,
    image_licence TEXT,
    image_licence_url TEXT CHECK (
        image_licence_url IS NULL OR image_licence_url ~ '^https://'
    ),
    image_attribution TEXT,
    gbif_occurrence_key BIGINT,
    enrichment_status TEXT NOT NULL CHECK (
        enrichment_status IN (
            'verified_open_image', 'no_open_image',
            'taxon_unresolved', 'request_failed'
        )
    ),
    limitation TEXT NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        enrichment_status <> 'verified_open_image'
        OR (
            image_url IS NOT NULL AND image_page_url IS NOT NULL
            AND image_licence IS NOT NULL AND image_licence_url IS NOT NULL
            AND image_attribution IS NOT NULL AND match_type = 'EXACT'
            AND match_confidence >= 95
        )
    )
);

CREATE INDEX idx_tree_species_image_enrichment_status
    ON tree_species_image_enrichment(enrichment_status, checked_at);

CREATE OR REPLACE VIEW application_ready_tree_species_image AS
WITH combined AS (
    SELECT image.tree_species_image_id, image.tree_type,
           image.scientific_name, image.image_url,
           image.image_page_url, image.image_alt_text, image.image_creator,
           image.image_licence, image.image_licence_url,
           image.image_attribution, image.source_name,
           image.last_verified_at,
           'curated_reference_image'::TEXT AS image_status,
           'Reference image only; appearance varies with age, season, cultivar and growing conditions. Verify remote availability and retain the supplied attribution.'::TEXT AS image_limitation,
           1 AS source_priority
    FROM tree_species_image AS image
    WHERE image.active
    UNION ALL
    SELECT NULL::UUID, NULL::TEXT, enrichment.scientific_name,
           enrichment.image_url, enrichment.image_page_url,
           enrichment.image_alt_text, enrichment.image_creator,
           enrichment.image_licence, enrichment.image_licence_url,
           enrichment.image_attribution, 'GBIF occurrence media API',
           enrichment.checked_at, 'verified_gbif_open_image',
           enrichment.limitation, 2
    FROM tree_species_image_enrichment AS enrichment
    WHERE enrichment.enrichment_status = 'verified_open_image'
), ranked AS (
    SELECT combined.*,
           ROW_NUMBER() OVER (
               PARTITION BY LOWER(BTRIM(scientific_name))
               ORDER BY source_priority, last_verified_at DESC
           ) AS image_rank
    FROM combined
)
SELECT tree_species_image_id, tree_type, scientific_name,
       image_url, image_page_url,
       image_alt_text, image_creator, image_licence, image_licence_url,
       image_attribution, source_name, last_verified_at,
       image_status, image_limitation
FROM ranked
WHERE image_rank = 1;

CREATE OR REPLACE VIEW complete_tree_species_catalog AS
WITH species AS (
    SELECT LOWER(BTRIM(profile.scientific_name)) AS species_key,
           MIN(BTRIM(profile.scientific_name)) AS scientific_name,
           MIN(NULLIF(BTRIM(profile.common_name), '')) AS common_name
    FROM species_profile AS profile
    WHERE NULLIF(BTRIM(profile.scientific_name), '') IS NOT NULL
    GROUP BY LOWER(BTRIM(profile.scientific_name))
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

COMMENT ON TABLE tree_species_image_enrichment IS
    'One audited GBIF enrichment result per database scientific name, including explicit unresolved and no-open-image outcomes.';
COMMENT ON VIEW complete_tree_species_catalog IS
    'All distinct named database species. Exact costs and verified images are preserved; missing species prices use a prominently labelled generic current-catalogue range and missing images remain unavailable.';

COMMIT;
