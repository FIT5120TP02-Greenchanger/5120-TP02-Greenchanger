BEGIN;

DO $migration$
DECLARE
    v_definition TEXT;
    v_fixed_definition TEXT;
BEGIN
    SELECT pg_get_functiondef(
        'get_tree_planting_catalog_by_address(text,integer)'::REGPROCEDURE
    ) INTO v_definition;

    v_fixed_definition := REPLACE(
        v_definition,
        'MIN(estimate.currency) AS currency',
        'MIN(estimate.currency)::TEXT AS currency'
    );

    IF v_fixed_definition = v_definition THEN
        RAISE EXCEPTION
            'expected the migration 050 currency aggregation was not found';
    END IF;

    EXECUTE v_fixed_definition;
END;
$migration$;

COMMENT ON FUNCTION get_tree_planting_catalog_by_address(TEXT, INTEGER) IS
    'Resolves a Melbourne address to its LGA and returns cost-supported catalogue trees with council guidance status, current AUD supply and installed ranges, and licensed image attribution. Currency is returned as text for a stable API contract. A catalogue row is not proof of site suitability, nursery availability or council approval.';

COMMIT;
