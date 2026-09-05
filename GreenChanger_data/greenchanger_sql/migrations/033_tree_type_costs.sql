BEGIN;

ALTER TABLE cost_estimate
    ADD COLUMN IF NOT EXISTS tree_type TEXT,
    ADD COLUMN IF NOT EXISTS botanical_name TEXT;

COMMENT ON COLUMN cost_estimate.tree_type IS
    'Supplier-facing common tree type or cultivar; null for non-tree options.';

COMMENT ON COLUMN cost_estimate.botanical_name IS
    'Botanical name where the supplier identifies it; null when not published.';

CREATE INDEX IF NOT EXISTS idx_cost_estimate_tree_type
    ON cost_estimate (UPPER(tree_type), valid_from, valid_to)
    WHERE tree_type IS NOT NULL;

CREATE OR REPLACE VIEW application_ready_cost_estimate AS
SELECT
    ce.cost_estimate_id,
    go.option_code,
    go.option_name,
    go.option_category,
    go.cost_unit,
    ce.cost_context,
    ce.cost_basis,
    ce.tree_size_category,
    ce.planting_method,
    ce.stock_size,
    ce.minimum_cost,
    ce.maximum_cost,
    ce.material_min_cost,
    ce.material_max_cost,
    ce.installation_min_cost,
    ce.installation_max_cost,
    ce.delivery_min_cost,
    ce.delivery_max_cost,
    ce.setup_min_cost,
    ce.setup_max_cost,
    ce.currency,
    ce.gst_included,
    ce.includes_installation,
    ce.annual_maintenance_cost,
    ce.source_name,
    ce.source_reference,
    ce.source_url,
    ce.valid_from,
    ce.valid_to,
    ce.last_verified_at,
    ce.confidence_level,
    'indicative_not_quote'::TEXT AS estimate_status,
    'Indicative source-backed range only; confirm current price, availability, site conditions, delivery, installation and maintenance with the supplier.'::TEXT
        AS display_disclaimer,
    ce.tree_type,
    ce.botanical_name
FROM cost_estimate AS ce
JOIN greening_option AS go USING (greening_option_id)
WHERE go.active
  AND ce.valid_from <= CURRENT_DATE
  AND ce.valid_to >= CURRENT_DATE;

COMMENT ON VIEW application_ready_cost_estimate IS
    'Current source-backed greening cost contexts, including tree type where applicable, with confidence, provenance and mandatory indicative-estimate disclaimer.';

COMMIT;
