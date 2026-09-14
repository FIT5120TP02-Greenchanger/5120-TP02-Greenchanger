BEGIN;

-- Tree type is part of the source contract's business key. NULLS NOT DISTINCT
-- keeps non-tree options idempotent while allowing otherwise-identical prices
-- for different named tree types to coexist.
DROP INDEX IF EXISTS uq_cost_estimate_source_version;

CREATE UNIQUE INDEX uq_cost_estimate_source_version
    ON cost_estimate (
        greening_option_id,
        cost_context,
        cost_basis,
        tree_type,
        source_name,
        valid_from,
        source_reference
    ) NULLS NOT DISTINCT;

COMMENT ON INDEX uq_cost_estimate_source_version IS
    'Cost source-version business key including tree type; null tree types are not distinct so non-tree options remain deduplicated.';

COMMIT;
