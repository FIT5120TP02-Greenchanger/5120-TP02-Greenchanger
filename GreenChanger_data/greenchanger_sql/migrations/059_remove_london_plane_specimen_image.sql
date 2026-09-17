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
    gbif_occurrence_key = NULL,
    enrichment_status = 'no_open_image',
    limitation = 'Image removed after source copyright review; no replacement image has been verified.',
    checked_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP
WHERE image_url = 'https://sweetgum.nybg.org/images3/1967/024/02513824.jpg';

UPDATE tree_species_image
SET active = FALSE
WHERE image_url = 'https://sweetgum.nybg.org/images3/1967/024/02513824.jpg';

ALTER TABLE tree_species_image_enrichment
    ADD CONSTRAINT tree_species_image_enrichment_blocked_url_check
    CHECK (
        image_url IS NULL
        OR image_url <> 'https://sweetgum.nybg.org/images3/1967/024/02513824.jpg'
    );

ALTER TABLE tree_species_image
    ADD CONSTRAINT tree_species_image_blocked_url_check
    CHECK (
        image_url <> 'https://sweetgum.nybg.org/images3/1967/024/02513824.jpg'
    );

COMMIT;
