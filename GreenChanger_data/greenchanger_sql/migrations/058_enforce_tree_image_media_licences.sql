BEGIN;

UPDATE tree_species_image_enrichment
SET image_url = NULL,
    image_page_url = NULL,
    image_alt_text = NULL,
    image_creator = NULL,
    image_rights_holder = NULL,
    image_licence = NULL,
    image_licence_url = NULL,
    image_attribution = NULL,
    enrichment_status = 'no_open_image',
    limitation = 'Quarantined: the stored media licence is not approved for catalogue publication. Re-enrich only after validating the licence on the individual media object.',
    checked_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP
WHERE enrichment_status = 'verified_open_image'
  AND (
      (image_source_name = 'GBIF occurrence media API' AND NOT (
          (image_licence = 'CC BY 4.0'
           AND image_licence_url = 'https://creativecommons.org/licenses/by/4.0/')
          OR
          (image_licence = 'CC0 1.0'
           AND image_licence_url = 'https://creativecommons.org/publicdomain/zero/1.0/')
      ))
      OR
      (image_source_name = 'Wikimedia Commons' AND NOT (
          (image_licence, image_licence_url) IN (
              ('Public domain', 'https://creativecommons.org/publicdomain/mark/1.0/'),
              ('CC0 1.0', 'https://creativecommons.org/publicdomain/zero/1.0/'),
              ('CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0/'),
              ('CC BY 2.5', 'https://creativecommons.org/licenses/by/2.5/'),
              ('CC BY 3.0', 'https://creativecommons.org/licenses/by/3.0/'),
              ('CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0/'),
              ('CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0/'),
              ('CC BY-SA 2.5', 'https://creativecommons.org/licenses/by-sa/2.5/'),
              ('CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0/'),
              ('CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0/')
          )
      ))
      OR image_source_name NOT IN ('GBIF occurrence media API', 'Wikimedia Commons')
  );

ALTER TABLE tree_species_image_enrichment
    ADD CONSTRAINT tree_species_image_enrichment_approved_licence_check
    CHECK (
        enrichment_status <> 'verified_open_image'
        OR (
            image_source_name = 'GBIF occurrence media API'
            AND (
                (image_licence = 'CC BY 4.0'
                 AND image_licence_url = 'https://creativecommons.org/licenses/by/4.0/')
                OR
                (image_licence = 'CC0 1.0'
                 AND image_licence_url = 'https://creativecommons.org/publicdomain/zero/1.0/')
            )
        )
        OR (
            image_source_name = 'Wikimedia Commons'
            AND (image_licence, image_licence_url) IN (
                ('Public domain', 'https://creativecommons.org/publicdomain/mark/1.0/'),
                ('CC0 1.0', 'https://creativecommons.org/publicdomain/zero/1.0/'),
                ('CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0/'),
                ('CC BY 2.5', 'https://creativecommons.org/licenses/by/2.5/'),
                ('CC BY 3.0', 'https://creativecommons.org/licenses/by/3.0/'),
                ('CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0/'),
                ('CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0/'),
                ('CC BY-SA 2.5', 'https://creativecommons.org/licenses/by-sa/2.5/'),
                ('CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0/'),
                ('CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0/')
            )
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
      AND (image.image_licence, image.image_licence_url) IN (
          ('Public domain', 'https://creativecommons.org/publicdomain/mark/1.0/'),
          ('CC0 1.0', 'https://creativecommons.org/publicdomain/zero/1.0/'),
          ('CC BY 2.0', 'https://creativecommons.org/licenses/by/2.0/'),
          ('CC BY 2.5', 'https://creativecommons.org/licenses/by/2.5/'),
          ('CC BY 3.0', 'https://creativecommons.org/licenses/by/3.0/'),
          ('CC BY 4.0', 'https://creativecommons.org/licenses/by/4.0/'),
          ('CC BY-SA 2.0', 'https://creativecommons.org/licenses/by-sa/2.0/'),
          ('CC BY-SA 2.5', 'https://creativecommons.org/licenses/by-sa/2.5/'),
          ('CC BY-SA 3.0', 'https://creativecommons.org/licenses/by-sa/3.0/'),
          ('CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0/')
      )
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

UPDATE dataset_source
SET licence = 'Individual media-level CC0 1.0 or CC BY 4.0 only',
    access_method = 'GBIF REST API with media-level licence validation'
WHERE source_name = 'GBIF occurrence media API'
  AND publisher = 'Global Biodiversity Information Facility';

COMMENT ON TABLE tree_species_image_enrichment IS
    'One audited image-enrichment result per scientific name. GBIF publication requires an approved licence on the individual media object; occurrence-level search filters alone are insufficient.';

COMMIT;
