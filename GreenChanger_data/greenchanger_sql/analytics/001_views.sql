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

CREATE OR REPLACE VIEW current_cost_estimate AS
SELECT ce.*
FROM cost_estimate AS ce
WHERE ce.valid_from <= CURRENT_DATE
  AND (ce.valid_to IS NULL OR ce.valid_to >= CURRENT_DATE);

CREATE OR REPLACE VIEW latest_measure_test_result AS
SELECT DISTINCT ON (mtr.test_case_id, mtr.model_version_id)
    mtr.test_result_id,
    mtr.test_case_id,
    mtr.model_version_id,
    mtr.executed_at,
    mtr.actual_value,
    mtr.absolute_difference,
    mtr.passed,
    mtr.notes
FROM measure_test_result AS mtr
ORDER BY mtr.test_case_id, mtr.model_version_id, mtr.executed_at DESC;
