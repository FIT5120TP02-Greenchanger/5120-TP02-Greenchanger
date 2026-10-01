BEGIN;

DO $migration$
DECLARE
    v_definition TEXT;
    v_status_expression TEXT :=
        'SELECT ARRAY_AGG(DISTINCT status ORDER BY status) AS statuses';
    v_qualified_status_expression TEXT :=
        'SELECT ARRAY_AGG(DISTINCT matched.status ORDER BY matched.status) AS statuses';
    v_order_expression TEXT := 'ORDER BY popularity_rank NULLS LAST';
BEGIN
    SELECT pg_get_functiondef(
        'get_council_tree_species_popularity_by_address(text,integer)'::REGPROCEDURE
    )
    INTO v_definition;

    IF STRPOS(v_definition, v_status_expression) = 0 THEN
        RAISE EXCEPTION
            'migration 045 expected the migration 044 unqualified status expression';
    END IF;

    v_definition := REPLACE(
        v_definition,
        v_status_expression,
        v_qualified_status_expression
    );
    v_definition := REPLACE(
        v_definition,
        v_order_expression,
        'ORDER BY 3 NULLS LAST'
    );
    EXECUTE v_definition;
END;
$migration$;

COMMENT ON FUNCTION get_council_tree_species_popularity_by_address(TEXT, INTEGER) IS
    'Ranks species by frequency in latest application-ready council public-tree inventories within the address LGA. Internal aliases are qualified to avoid PL/pgSQL output-column ambiguity; frequency never implies planting approval or site suitability.';

COMMIT;
