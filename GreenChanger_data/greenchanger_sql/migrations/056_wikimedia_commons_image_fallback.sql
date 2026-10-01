BEGIN;

INSERT INTO dataset_source (
    source_name, publisher, source_url, licence, licence_status,
    source_category, geographic_coverage, access_method, update_frequency
)
VALUES (
    'Wikimedia Commons', 'Wikimedia Foundation',
    'https://commons.wikimedia.org/w/api.php',
    'Per-file public-domain, CC0, CC BY or CC BY-SA licence',
    'open_confirmed', 'species_reference_image', 'Global',
    'Wikimedia Commons API with exact Wikidata P225 taxon verification',
    'on demand'
)
ON CONFLICT (source_name, publisher) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    licence = EXCLUDED.licence,
    licence_status = EXCLUDED.licence_status,
    source_category = EXCLUDED.source_category,
    geographic_coverage = EXCLUDED.geographic_coverage,
    access_method = EXCLUDED.access_method,
    update_frequency = EXCLUDED.update_frequency;

ALTER TABLE tree_species_image_enrichment
    ADD COLUMN image_source_name TEXT NOT NULL
        DEFAULT 'GBIF occurrence media API',
    ADD COLUMN taxon_verification_id TEXT,
    ADD COLUMN commons_file_title TEXT;

UPDATE tree_species_image_enrichment
SET taxon_verification_id = gbif_taxon_key::TEXT
WHERE gbif_taxon_key IS NOT NULL
  AND taxon_verification_id IS NULL;

ALTER TABLE tree_species_image_enrichment
    ADD CONSTRAINT tree_species_image_enrichment_commons_verification_check
    CHECK (
        enrichment_status <> 'verified_open_image'
        OR image_source_name <> 'Wikimedia Commons'
        OR (
            taxon_verification_id ~ '^Q[0-9]+$'
            AND commons_file_title LIKE 'File:%'
            AND taxonomic_status = 'WIKIDATA_EXACT_P225'
            AND match_type = 'EXACT'
            AND match_confidence = 100
        )
    );

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
           enrichment.image_attribution, enrichment.image_source_name,
           enrichment.checked_at,
           CASE WHEN enrichment.image_source_name = 'Wikimedia Commons'
                THEN 'verified_wikimedia_commons_image'
                ELSE 'verified_gbif_open_image' END,
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

COMMENT ON TABLE tree_species_image_enrichment IS
    'One audited image-enrichment result per database scientific name. GBIF images require an exact high-confidence Plantae match; Wikimedia Commons fallbacks require an exact Wikidata P225 taxon match and retain the per-file open licence and attribution.';

COMMIT;
