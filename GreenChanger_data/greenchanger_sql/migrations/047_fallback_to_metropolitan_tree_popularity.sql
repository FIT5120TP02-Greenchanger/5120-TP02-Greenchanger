BEGIN;

DO $migration$
DECLARE
    v_definition TEXT;
    v_old_declaration TEXT := E'    v_exact_count INTEGER;\n    v_lga latest_victorian_lga_boundary%ROWTYPE;';
    v_new_declaration TEXT := E'    v_exact_count INTEGER;\n    v_has_council_inventory BOOLEAN;\n    v_lga latest_victorian_lga_boundary%ROWTYPE;';
    v_boundary_check TEXT := E'    IF NOT FOUND THEN\n        RAISE EXCEPTION ''matched address is outside the loaded Victorian LGA boundaries'';\n    END IF;';
    v_inventory_check TEXT := E'    IF NOT FOUND THEN\n        RAISE EXCEPTION ''matched address is outside the loaded Victorian LGA boundaries'';\n    END IF;\n\n    SELECT EXISTS (\n        SELECT 1\n        FROM latest_metropolitan_named_tree_inventory AS tree\n        WHERE ST_Covers(v_lga.boundary_geometry, tree.tree_location)\n          AND normalize_greenchanger_council_name(tree.municipality) =\n              normalize_greenchanger_council_name(v_lga.lga_official_name)\n          AND COALESCE(\n                  NULLIF(BTRIM(tree.scientific_name), ''''),\n                  NULLIF(BTRIM(tree.common_name), '''')\n              ) IS NOT NULL\n    ) INTO v_has_council_inventory;';
    v_old_filter TEXT := E'        WHERE ST_Covers(v_lga.boundary_geometry, tree.tree_location)\n          AND normalize_greenchanger_council_name(tree.municipality) =\n              normalize_greenchanger_council_name(v_lga.lga_official_name)';
    v_new_filter TEXT := E'        WHERE (\n                (v_has_council_inventory\n                 AND ST_Covers(v_lga.boundary_geometry, tree.tree_location)\n                 AND normalize_greenchanger_council_name(tree.municipality) =\n                     normalize_greenchanger_council_name(v_lga.lga_official_name))\n                OR NOT v_has_council_inventory\n              )';
    v_old_status TEXT := '''observed_public_tree_frequency''::TEXT AS status';
    v_new_status TEXT := E'CASE\n                WHEN v_has_council_inventory\n                    THEN ''observed_public_tree_frequency''\n                ELSE ''fallback_overall_observed_public_tree_frequency''\n            END::TEXT AS status';
    v_old_limitation TEXT := '''Popularity is frequency among latest application-ready council-maintained public-tree inventory records inside the LGA. It is not resident preference, planting approval, nursery availability, private-tree prevalence or property suitability. Council source completeness and dates vary.''::TEXT AS limitation';
    v_new_limitation TEXT := E'CASE\n                WHEN v_has_council_inventory THEN\n                    ''Popularity is frequency among latest application-ready council-maintained public-tree inventory records inside the LGA. It is not resident preference, planting approval, nursery availability, private-tree prevalence or property suitability. Council source completeness and dates vary.''\n                ELSE\n                    ''Warning: no latest application-ready named public-tree inventory covers this council. These fallback results are the ten most commonly recorded species across all integrated Melbourne council inventories, not evidence that the species is approved, available or suitable for this property. Confirm planting rules and site conditions with the local council.''\n            END::TEXT AS limitation';
    v_old_limit TEXT := 'WHERE ranked_species.popularity_rank <= p_result_limit';
    v_new_limit TEXT := E'WHERE ranked_species.popularity_rank <= CASE\n                WHEN v_has_council_inventory THEN p_result_limit\n                ELSE LEAST(p_result_limit, 10)\n            END';
BEGIN
    SELECT pg_get_functiondef(
        'get_council_tree_species_popularity_by_address(text,integer)'::REGPROCEDURE
    ) INTO v_definition;

    IF STRPOS(v_definition, v_old_declaration) = 0
       OR STRPOS(v_definition, v_boundary_check) = 0
       OR STRPOS(v_definition, v_old_filter) = 0
       OR STRPOS(v_definition, v_old_status) = 0
       OR STRPOS(v_definition, v_old_limitation) = 0
       OR STRPOS(v_definition, v_old_limit) = 0 THEN
        RAISE EXCEPTION
            'migration 047 expected the migration 046 popularity function definition';
    END IF;

    v_definition := REPLACE(v_definition, v_old_declaration, v_new_declaration);
    v_definition := REPLACE(v_definition, v_boundary_check, v_inventory_check);
    v_definition := REPLACE(v_definition, v_old_filter, v_new_filter);
    v_definition := REPLACE(v_definition, v_old_status, v_new_status);
    v_definition := REPLACE(v_definition, v_old_limitation, v_new_limitation);
    v_definition := REPLACE(v_definition, v_old_limit, v_new_limit);
    EXECUTE v_definition;
END;
$migration$;

COMMENT ON FUNCTION get_council_tree_species_popularity_by_address(TEXT, INTEGER) IS
    'Ranks council-specific named public-tree species when inventory is available; otherwise returns at most ten overall integrated-Melbourne frequency results with an explicit fallback warning. Frequency never implies planting approval, availability or site suitability.';

COMMIT;
