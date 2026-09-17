BEGIN;

-- A distribution map, IIIF manifest or deep-zoom descriptor is not a
-- renderable tree photograph. Quarantine stale enrichment rows before adding
-- the constraint so old pipeline output cannot leak into the application view.
UPDATE tree_species_image_enrichment
SET image_url = NULL,
    image_page_url = NULL,
    image_alt_text = NULL,
    image_creator = NULL,
    image_rights_holder = NULL,
    image_licence = NULL,
    image_licence_url = NULL,
    image_attribution = NULL,
    commons_file_title = NULL,
    enrichment_status = 'no_open_image',
    limitation = 'Quarantined: the stored URL is a distribution map, non-image manifest, deep-zoom descriptor, or unreachable remote asset. Re-enrich only with a directly renderable licensed image.',
    checked_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP
WHERE enrichment_status = 'verified_open_image'
  AND (
      image_url ~* '(dist(map|[a-z]?[0-9]+)|distribution|range.?map)'
      OR COALESCE(commons_file_title, '') ~* '(dist(map|[a-z]?[0-9]+)|distribution|range.?map)'
      OR image_url ~* '(/manifest([?#]|$)|\.dzi([?#]|$))'
      OR image_url IN (
          'https://ibss-images.calacademy.org/static/botany/originals/be/99/be990872-82ef-450e-ba57-cb784cbfdffb.JPG',
          'https://media.canadensys.net/mt-specimens/large/MT00194244.jpg',
          'https://mediaphoto.mnhn.fr/media/1446828003557tuBw6250az1DTVL5'
      )
  );

ALTER TABLE tree_species_image_enrichment
    ADD CONSTRAINT tree_species_image_enrichment_renderable_asset_check
    CHECK (
        enrichment_status <> 'verified_open_image'
        OR (
            image_url !~* '(dist(map|[a-z]?[0-9]+)|distribution|range.?map)'
            AND COALESCE(commons_file_title, '') !~* '(dist(map|[a-z]?[0-9]+)|distribution|range.?map)'
            AND image_url !~* '(/manifest([?#]|$)|\.dzi([?#]|$))'
            AND image_url NOT IN (
                'https://ibss-images.calacademy.org/static/botany/originals/be/99/be990872-82ef-450e-ba57-cb784cbfdffb.JPG',
                'https://media.canadensys.net/mt-specimens/large/MT00194244.jpg',
                'https://mediaphoto.mnhn.fr/media/1446828003557tuBw6250az1DTVL5'
            )
        )
    );

INSERT INTO tree_species_image (
    tree_type, scientific_name, image_url, image_page_url, image_alt_text,
    image_creator, image_licence, image_licence_url, image_attribution,
    source_name, last_verified_at, active
)
VALUES
    (
        'Fern-leaved Wattle',
        'Acacia ficifolia',
        'https://commons.wikimedia.org/wiki/Special:FilePath/Acacia_filicifolia_(habit).jpg?width=800',
        'https://commons.wikimedia.org/wiki/File:Acacia_filicifolia_(habit).jpg',
        'Acacia filicifolia growing in the Imbota Nature Reserve near Armidale.',
        'Geoff Derrin',
        'CC BY-SA 4.0',
        'https://creativecommons.org/licenses/by-sa/4.0/',
        'Acacia filicifolia habit photograph by Geoff Derrin, CC BY-SA 4.0, via Wikimedia Commons.',
        'Wikimedia Commons',
        TIMESTAMPTZ '2026-09-18 00:00:00+10',
        TRUE
    ),
    (
        'Flinders Range Wattle',
        'Flinders Range Wattle, Acacia iteaphylla',
        'https://commons.wikimedia.org/wiki/Special:FilePath/Acacia_iteaphylla_1c.JPG?width=800',
        'https://commons.wikimedia.org/wiki/File:Acacia_iteaphylla_1c.JPG',
        'Flowering Acacia iteaphylla in the Barcelona Botanic Garden.',
        'Consultaplantas',
        'CC BY-SA 4.0',
        'https://creativecommons.org/licenses/by-sa/4.0/',
        'Acacia iteaphylla photograph by Consultaplantas, CC BY-SA 4.0, via Wikimedia Commons.',
        'Wikimedia Commons',
        TIMESTAMPTZ '2026-09-18 00:00:00+10',
        TRUE
    ),
    (
        'Creek Tea-tree',
        'Leptospermum obavatum',
        'https://commons.wikimedia.org/wiki/Special:FilePath/Leptospermum_obovatum.jpg?width=800',
        'https://commons.wikimedia.org/wiki/File:Leptospermum_obovatum.jpg',
        'Leptospermum obovatum foliage and seed capsules in the Barcelona Botanic Garden.',
        'Dinkum',
        'CC0 1.0',
        'https://creativecommons.org/publicdomain/zero/1.0/',
        'Leptospermum obovatum photograph by Dinkum, dedicated to the public domain under CC0 1.0, via Wikimedia Commons.',
        'Wikimedia Commons',
        TIMESTAMPTZ '2026-09-18 00:00:00+10',
        TRUE
    ),
    (
        'Weeping Tea-tree',
        'Weeping tea tree, Leptospermum madidum',
        'https://commons.wikimedia.org/wiki/Special:FilePath/Weeping_tea_tree_(Leptospermum_madidum).jpg?width=800',
        'https://commons.wikimedia.org/wiki/File:Weeping_tea_tree_(Leptospermum_madidum).jpg',
        'Weeping tea-tree (Leptospermum madidum) showing its mature growth habit.',
        'Mokkie',
        'CC BY-SA 3.0',
        'https://creativecommons.org/licenses/by-sa/3.0/',
        'Weeping tea-tree photograph by Mokkie, CC BY-SA 3.0, via Wikimedia Commons.',
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

COMMIT;
