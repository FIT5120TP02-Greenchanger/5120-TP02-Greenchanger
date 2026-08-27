BEGIN;

CREATE TABLE intervention_model_parameter (
    parameter_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_version_id UUID NOT NULL REFERENCES model_version(model_version_id),
    action_type TEXT NOT NULL CHECK (
        action_type IN ('tree', 'potted_plants', 'garden_bed', 'green_wall')
    ),
    parameter_code TEXT NOT NULL,
    parameter_name TEXT NOT NULL,
    parameter_values JSONB NOT NULL,
    output_metric TEXT,
    outcome_scope TEXT,
    parameter_role TEXT NOT NULL CHECK (
        parameter_role IN (
            'required_input', 'evidence_bound', 'supporting_evidence',
            'model_guardrail'
        )
    ),
    source_evidence_id UUID REFERENCES intervention_evidence(evidence_id),
    assumptions_and_limitations TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (model_version_id, action_type, parameter_code)
);

CREATE TABLE intervention_model_validation_run (
    validation_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_version_id UUID NOT NULL REFERENCES model_version(model_version_id),
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    case_count INTEGER NOT NULL CHECK (case_count > 0),
    passed_count INTEGER NOT NULL CHECK (passed_count >= 0),
    failed_count INTEGER NOT NULL CHECK (failed_count >= 0),
    all_passed BOOLEAN NOT NULL,
    validation_scope TEXT NOT NULL,
    CHECK (passed_count + failed_count = case_count)
);

CREATE TABLE intervention_model_validation_result (
    validation_result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    validation_run_id UUID NOT NULL REFERENCES intervention_model_validation_run(validation_run_id),
    case_code TEXT NOT NULL,
    source_keys TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    expected_output JSONB NOT NULL,
    actual_output JSONB NOT NULL,
    passed BOOLEAN NOT NULL,
    failure_messages TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    UNIQUE (validation_run_id, case_code)
);

INSERT INTO model_version (
    model_name,
    version_label,
    method_description,
    validation_status,
    validation_summary,
    output_precision,
    temperature_metric,
    spatial_scope,
    uncertainty_method,
    evidence_reviewed_at
)
VALUES (
    'GreenChanger literature-bounded intervention model',
    'literature-bounded-indicative-v1',
    'Calculates non-guaranteed impact ranges for trees, potted plants, garden beds and green walls. Temperature upper bounds retain the source metric and are scaled by intervention coverage; unsupported outcomes remain null.',
    'validation_in_progress',
    'Awaiting execution and persistence of all versioned published-evidence test cases.',
    'indicative_range',
    NULL,
    'Residential land-unit canopy/vegetation ranges and building-wall ranges; outcome metric is action-specific.',
    'Lower bound remains zero where cooling is not guaranteed. Upper bounds come from selected primary evidence and are capped at the reported evidence maximum.',
    DATE '2026-08-27'
)
ON CONFLICT (model_name, version_label) DO UPDATE SET
    method_description = EXCLUDED.method_description,
    output_precision = EXCLUDED.output_precision,
    spatial_scope = EXCLUDED.spatial_scope,
    uncertainty_method = EXCLUDED.uncertainty_method,
    evidence_reviewed_at = EXCLUDED.evidence_reviewed_at;

WITH parameter_rows (
    action_type, parameter_code, parameter_name, parameter_values,
    output_metric, outcome_scope, parameter_role, source_key,
    assumptions_and_limitations
) AS (
    VALUES
        ('tree', 'projected_canopy_m2', 'Projected crown-area range', '{"minimum":0,"maximum":null,"required_unless_growth_inputs_supplied":true}'::jsonb, 'canopy_area_proxy_for_shade', 'selected maturity horizon', 'required_input', NULL, 'Must come from a species/scenario crown estimate, or be calculated from starting crown and source-supported growth; no universal mature crown is assumed.'),
        ('tree', 'initial_canopy_m2', 'Starting crown-area range', '{"minimum":0,"maximum":null,"required_with_annual_growth":true}'::jsonb, 'canopy_area', 'scenario start', 'required_input', NULL, 'Alternative to a supplied projected crown area.'),
        ('tree', 'annual_crown_growth_m2_per_year', 'Annual crown-growth range', '{"minimum":0,"maximum":null,"required_with_initial_canopy":true}'::jsonb, 'canopy_area', 'selected maturity horizon', 'required_input', 'cybula_2026_melbourne_young_crowns', 'Must be species/source supported. The selected Melbourne study reports 2.3 m2/year as a mean plausibility case, not a universal default.'),
        ('tree', 'survival_probability', 'Establishment survival range', '{"minimum":0,"maximum":1,"required":true}'::jsonb, 'canopy_area_proxy_for_shade', 'selected maturity horizon', 'required_input', NULL, 'Valid probability bounds only, not an empirical project default.'),
        ('tree', 'site_suitability_factor', 'Site suitability range', '{"minimum":0,"maximum":1,"required":true}'::jsonb, 'canopy_area_proxy_for_shade', 'selected maturity horizon', 'required_input', NULL, 'Scenario input for space, soil and water constraints.'),
        ('tree', 'overlap_factor', 'Canopy overlap range', '{"minimum":0,"maximum":1,"required":true}'::jsonb, 'canopy_area_proxy_for_shade', 'selected maturity horizon', 'required_input', NULL, 'Prevents overlapping crown area from being counted twice.'),
        ('tree', 'maturity_horizon_years', 'Maturity horizon', '{"minimum_exclusive":0,"whole_number":true,"required":true}'::jsonb, 'canopy_area_proxy_for_shade', 'future scenario', 'model_guardrail', NULL, 'Prevents new plantings from being displayed as immediate mature shade.'),
        ('tree', 'young_crown_growth_m2_per_year', 'Observed mean young-tree crown growth', '{"reported_mean":2.3}'::jsonb, 'canopy_area', 'young trees measured over four years in Wyndham', 'supporting_evidence', 'cybula_2026_melbourne_young_crowns', 'Local plausibility check only; not a universal species growth rate.'),
        ('tree', 'daytime_land_unit_lst_reduction_c', 'Daytime land-unit LST evidence envelope', '{"minimum":0,"maximum":6}'::jsonb, 'land_surface_temperature', 'approximately 460 m2 Adelaide land units during one heatwave', 'evidence_bound', 'ossola_2021_adelaide_vegetated_patches', 'Observed association, not causal per-tree lift; the model scales only the upper envelope by canopy share.'),
        ('potted_plants', 'quantity', 'Number of pots', '{"minimum":0,"whole_number":true,"required":true}'::jsonb, 'projected_foliage_area', 'selected residential scenario', 'required_input', NULL, 'No default quantity.'),
        ('potted_plants', 'foliage_area_per_pot_m2', 'Foliage area per pot range', '{"minimum":0,"maximum":null,"required":true}'::jsonb, 'projected_foliage_area', 'selected residential scenario', 'required_input', NULL, 'Must be measured or supported by the selected plant/supplier; no generic default.'),
        ('potted_plants', 'temperature_effect_supported', 'Outdoor temperature evidence gate', '{"supported":false}'::jsonb, NULL, 'outdoor Melbourne residential temperature', 'model_guardrail', NULL, 'No fit-for-purpose primary evidence selected; temperature output must remain null.'),
        ('garden_bed', 'planted_area_m2', 'Garden-bed area range', '{"minimum":0,"maximum":null,"required":true}'::jsonb, 'established_vegetated_area', 'selected residential scenario', 'required_input', NULL, 'Uses installed area supplied by the scenario.'),
        ('garden_bed', 'established_cover_fraction', 'Established vegetation-cover range', '{"minimum":0,"maximum":1,"required":true}'::jsonb, 'established_vegetated_area', 'selected maturity horizon', 'required_input', NULL, 'Scenario input; no unsupported establishment guarantee.'),
        ('garden_bed', 'daytime_land_unit_lst_reduction_c', 'Conservative daytime LST evidence envelope', '{"minimum":0,"maximum":6}'::jsonb, 'land_surface_temperature', 'daytime land unit during comparable hot weather', 'evidence_bound', 'ossola_2021_adelaide_vegetated_patches', 'Combined vegetation upper envelope; grass was weaker than tree canopy and no causal garden-bed coefficient was reported.'),
        ('green_wall', 'installed_wall_area_m2', 'Installed green-wall area range', '{"minimum":0,"maximum":null,"required":true}'::jsonb, 'established_green_wall_area', 'selected wall', 'required_input', NULL, 'Uses installed area supplied by the scenario.'),
        ('green_wall', 'established_cover_fraction', 'Established wall-cover range', '{"minimum":0,"maximum":1,"required":true}'::jsonb, 'established_green_wall_area', 'selected wall and maturity horizon', 'required_input', NULL, 'Scenario input affected by species, irrigation and establishment.'),
        ('green_wall', 'exterior_wall_surface_reduction_c', 'Exterior wall-surface evidence envelope', '{"minimum":0,"maximum":15.5}'::jsonb, 'wall_surface_temperature', 'exterior wall during comparable hot summer conditions', 'evidence_bound', 'hoelscher_2016_facade_greening', 'Wall metric only; no street-canyon air cooling was detected and this must not become property LST.')
)
INSERT INTO intervention_model_parameter (
    model_version_id, action_type, parameter_code, parameter_name,
    parameter_values, output_metric, outcome_scope, parameter_role,
    source_evidence_id, assumptions_and_limitations
)
SELECT
    model.model_version_id,
    parameter.action_type,
    parameter.parameter_code,
    parameter.parameter_name,
    parameter.parameter_values,
    parameter.output_metric,
    parameter.outcome_scope,
    parameter.parameter_role,
    evidence.evidence_id,
    parameter.assumptions_and_limitations
FROM model_version AS model
CROSS JOIN parameter_rows AS parameter
LEFT JOIN intervention_evidence AS evidence
  ON evidence.citation_key = parameter.source_key
WHERE model.model_name = 'GreenChanger literature-bounded intervention model'
  AND model.version_label = 'literature-bounded-indicative-v1'
ON CONFLICT (model_version_id, action_type, parameter_code) DO UPDATE SET
    parameter_name = EXCLUDED.parameter_name,
    parameter_values = EXCLUDED.parameter_values,
    output_metric = EXCLUDED.output_metric,
    outcome_scope = EXCLUDED.outcome_scope,
    parameter_role = EXCLUDED.parameter_role,
    source_evidence_id = EXCLUDED.source_evidence_id,
    assumptions_and_limitations = EXCLUDED.assumptions_and_limitations;

INSERT INTO model_evidence (model_version_id, evidence_id, evidence_role, notes)
SELECT
    model.model_version_id,
    evidence.evidence_id,
    'candidate_validation',
    'Constrains an indicative range or validates an output guardrail; does not establish a local causal coefficient.'
FROM model_version AS model
JOIN intervention_evidence AS evidence
  ON evidence.citation_key IN (
      'cybula_2026_melbourne_young_crowns',
      'ossola_2021_adelaide_vegetated_patches',
      'armson_2012_tree_shade_grass',
      'hoelscher_2016_facade_greening'
  )
WHERE model.model_name = 'GreenChanger literature-bounded intervention model'
  AND model.version_label = 'literature-bounded-indicative-v1'
ON CONFLICT DO NOTHING;

CREATE OR REPLACE VIEW current_intervention_model_parameter AS
SELECT
    model.model_name,
    model.version_label,
    model.validation_status,
    model.output_precision,
    parameter.action_type,
    parameter.parameter_code,
    parameter.parameter_name,
    parameter.parameter_values,
    parameter.output_metric,
    parameter.outcome_scope,
    parameter.parameter_role,
    evidence.citation_key AS source_key,
    evidence.source_url,
    parameter.assumptions_and_limitations
FROM intervention_model_parameter AS parameter
JOIN model_version AS model USING (model_version_id)
LEFT JOIN intervention_evidence AS evidence
  ON evidence.evidence_id = parameter.source_evidence_id
WHERE model.retired_at IS NULL;

COMMENT ON TABLE intervention_model_parameter IS
    'Versioned action parameters, evidence bounds and guardrails for range-only intervention outputs.';
COMMENT ON TABLE intervention_model_validation_run IS
    'Auditable validation runs; model status is promoted only when all recorded evidence cases pass.';
COMMENT ON VIEW current_intervention_model_parameter IS
    'Current source-traceable intervention parameter definitions and limitations.';

COMMIT;
