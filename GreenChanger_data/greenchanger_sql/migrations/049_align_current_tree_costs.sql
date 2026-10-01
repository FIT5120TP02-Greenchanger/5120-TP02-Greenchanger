BEGIN;

-- Tree costs created before named species support can otherwise remain visible
-- beside the Iteration 2 species-specific estimates.
UPDATE cost_estimate AS ce
SET valid_to = LEAST(COALESCE(ce.valid_to, DATE '2026-09-14'), DATE '2026-09-14')
FROM greening_option AS go
WHERE go.greening_option_id = ce.greening_option_id
  AND go.option_code IN ('backyard_tree_diy', 'backyard_tree_installed')
  AND ce.tree_type IS NULL;

CREATE OR REPLACE VIEW current_cost_estimate AS
SELECT ce.*
FROM cost_estimate AS ce
WHERE ce.valid_from <= (CURRENT_TIMESTAMP AT TIME ZONE 'Australia/Melbourne')::DATE
  AND (
      ce.valid_to IS NULL
      OR ce.valid_to >= (CURRENT_TIMESTAMP AT TIME ZONE 'Australia/Melbourne')::DATE
  );

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
  AND ce.valid_from <= (CURRENT_TIMESTAMP AT TIME ZONE 'Australia/Melbourne')::DATE
  AND (
      ce.valid_to IS NULL
      OR ce.valid_to >= (CURRENT_TIMESTAMP AT TIME ZONE 'Australia/Melbourne')::DATE
  );

COMMENT ON VIEW current_cost_estimate IS
    'Cost estimates valid on the current Australia/Melbourne calendar date.';

COMMENT ON VIEW application_ready_cost_estimate IS
    'Current Melbourne-date source-backed greening cost contexts with option labels, confidence and mandatory indicative-estimate disclaimer.';

COMMIT;
