BEGIN;

INSERT INTO tree_species_image (
    tree_type, scientific_name, image_url, image_page_url, image_alt_text,
    image_creator, image_licence, image_licence_url, image_attribution,
    source_name, last_verified_at, active
)
VALUES (
    'London Plane',
    'Platanus x acerifolia',
    'https://commons.wikimedia.org/wiki/Special:FilePath/Berkeley_Square_-_geograph.org.uk_-_911963.jpg?width=800',
    'https://commons.wikimedia.org/wiki/File:Berkeley_Square_-_geograph.org.uk_-_911963.jpg',
    'Mature London Plane trees (Platanus x acerifolia, accepted as Platanus × hispanica) in Berkeley Square, London.',
    'Richard Croft',
    'CC BY-SA 2.0',
    'https://creativecommons.org/licenses/by-sa/2.0/',
    'London Plane trees in Berkeley Square photograph by Richard Croft, CC BY-SA 2.0, via Wikimedia Commons (File:Berkeley Square - geograph.org.uk - 911963.jpg).',
    'Wikimedia Commons',
    TIMESTAMPTZ '2026-09-18 00:00:00+10',
    TRUE
)
ON CONFLICT (tree_type, scientific_name) DO UPDATE
SET image_url = EXCLUDED.image_url,
    image_page_url = EXCLUDED.image_page_url,
    image_alt_text = EXCLUDED.image_alt_text,
    image_creator = EXCLUDED.image_creator,
    image_licence = EXCLUDED.image_licence,
    image_licence_url = EXCLUDED.image_licence_url,
    image_attribution = EXCLUDED.image_attribution,
    source_name = EXCLUDED.source_name,
    last_verified_at = EXCLUDED.last_verified_at,
    active = TRUE;

COMMENT ON TABLE tree_species_image IS
    'Curated tree catalogue images keyed to the exact application scientific name, with reusable licence, creator and source-page attribution. Curated rows take priority over automated enrichment, including when an accepted taxon name differs from the inventory synonym.';

COMMIT;
