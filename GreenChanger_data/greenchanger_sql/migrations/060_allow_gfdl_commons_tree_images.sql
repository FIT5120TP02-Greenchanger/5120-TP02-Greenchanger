BEGIN;

ALTER TABLE tree_species_image_enrichment
    DROP CONSTRAINT tree_species_image_enrichment_approved_licence_check;

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
                ('GFDL 1.2', 'https://www.gnu.org/licenses/old-licenses/fdl-1.2.html'),
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

COMMENT ON CONSTRAINT tree_species_image_enrichment_approved_licence_check
    ON tree_species_image_enrichment IS
    'Allows only explicitly reviewed, commercially reusable media licences. GFDL 1.2 images require attribution and continued licence compliance.';

COMMIT;
