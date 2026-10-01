BEGIN;

DO $migration$
DECLARE
    v_definition TEXT;
    v_broken_check TEXT := E'    SELECT EXISTS (\n        SELECT 1\n        FROM latest_metropolitan_named_tree_inventory AS tree\n        WHERE (\n                (v_has_council_inventory\n                 AND ST_Covers(v_lga.boundary_geometry, tree.tree_location)\n                 AND normalize_greenchanger_council_name(tree.municipality) =\n                     normalize_greenchanger_council_name(v_lga.lga_official_name))\n                OR NOT v_has_council_inventory\n              )\n          AND COALESCE(\n                  NULLIF(BTRIM(tree.scientific_name), ''''),\n                  NULLIF(BTRIM(tree.common_name), '''')\n              ) IS NOT NULL\n    ) INTO v_has_council_inventory;';
    v_correct_check TEXT := E'    SELECT EXISTS (\n        SELECT 1\n        FROM latest_metropolitan_named_tree_inventory AS tree\n        WHERE ST_Covers(v_lga.boundary_geometry, tree.tree_location)\n          AND normalize_greenchanger_council_name(tree.municipality) =\n              normalize_greenchanger_council_name(v_lga.lga_official_name)\n          AND COALESCE(\n                  NULLIF(BTRIM(tree.scientific_name), ''''),\n                  NULLIF(BTRIM(tree.common_name), '''')\n              ) IS NOT NULL\n    ) INTO v_has_council_inventory;';
BEGIN
    SELECT pg_get_functiondef(
        'get_council_tree_species_popularity_by_address(text,integer)'::REGPROCEDURE
    ) INTO v_definition;

    IF STRPOS(v_definition, v_broken_check) = 0 THEN
        RAISE EXCEPTION
            'migration 048 expected the migration 047 recursive availability check';
    END IF;

    v_definition := REPLACE(v_definition, v_broken_check, v_correct_check);
    EXECUTE v_definition;
END;
$migration$;

COMMENT ON FUNCTION get_council_tree_species_popularity_by_address(TEXT, INTEGER) IS
    'Ranks council-specific named public-tree species when inventory is available; otherwise returns at most ten overall integrated-Melbourne frequency results with an explicit fallback warning. The availability test independently checks authoritative LGA coverage and matching source municipality.';

COMMIT;
