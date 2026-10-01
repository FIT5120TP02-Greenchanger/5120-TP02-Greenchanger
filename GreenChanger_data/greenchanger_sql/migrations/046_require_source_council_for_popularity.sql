BEGIN;

CREATE OR REPLACE FUNCTION normalize_greenchanger_council_name(p_name TEXT)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
RETURN NULLIF(
    REGEXP_REPLACE(
        REGEXP_REPLACE(UPPER(BTRIM(p_name)), '^CITY OF\s+', ''),
        '\s+(CITY COUNCIL|CITY)$',
        ''
    ),
    ''
);

DO $migration$
DECLARE
    v_definition TEXT;
    v_spatial_filter TEXT :=
        'WHERE ST_Covers(v_lga.boundary_geometry, tree.tree_location)';
    v_source_council_filter TEXT :=
        'WHERE ST_Covers(v_lga.boundary_geometry, tree.tree_location)
          AND normalize_greenchanger_council_name(tree.municipality) =
              normalize_greenchanger_council_name(v_lga.lga_official_name)';
BEGIN
    SELECT pg_get_functiondef(
        'get_council_tree_species_popularity_by_address(text,integer)'::REGPROCEDURE
    )
    INTO v_definition;

    IF STRPOS(v_definition, v_spatial_filter) = 0 THEN
        RAISE EXCEPTION
            'migration 046 expected the migration 044 inventory spatial filter';
    END IF;

    v_definition := REPLACE(
        v_definition,
        v_spatial_filter,
        v_source_council_filter
    );
    EXECUTE v_definition;
END;
$migration$;

COMMENT ON FUNCTION normalize_greenchanger_council_name(TEXT) IS
    'Normalises City of X, X City and X City Council labels for source-to-LGA equality checks.';
COMMENT ON FUNCTION get_council_tree_species_popularity_by_address(TEXT, INTEGER) IS
    'Ranks latest application-ready named public-tree species only when both the source municipality and authoritative address LGA match. Frequency never implies planting approval, availability or site suitability.';

COMMIT;
