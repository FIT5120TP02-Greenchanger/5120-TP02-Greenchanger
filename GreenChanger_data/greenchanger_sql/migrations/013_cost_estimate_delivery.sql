BEGIN;

CREATE OR REPLACE VIEW dataset_quality_summary AS
SELECT
    ds.source_name,
    dv.dataset_version_id,
    dv.extracted_at,
    dv.source_observed_from,
    dv.source_observed_to,
    dv.quality_pass_rate,
    dv.quality_status,
    dv.integration_status,
    CASE
        WHEN dv.quality_pass_rate >= 95 THEN TRUE
        ELSE FALSE
    END AS passed_quality_gate
FROM dataset_version AS dv
JOIN dataset_source AS ds ON ds.source_id = dv.source_id;

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
        AS display_disclaimer
FROM cost_estimate AS ce
JOIN greening_option AS go USING (greening_option_id)
WHERE go.active
  AND ce.valid_from <= CURRENT_DATE
  AND ce.valid_to >= CURRENT_DATE;

COMMENT ON VIEW application_ready_cost_estimate IS
    'Current source-backed greening cost contexts with option labels, confidence and mandatory indicative-estimate disclaimer.';

COMMIT;
