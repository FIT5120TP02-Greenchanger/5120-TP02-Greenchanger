BEGIN;

ALTER TABLE model_version
    ADD COLUMN output_precision TEXT NOT NULL DEFAULT 'suppressed' CHECK (
        output_precision IN (
            'suppressed', 'indicative_range', 'precise_point_estimate'
        )
    ),
    ADD COLUMN temperature_metric TEXT CHECK (
        temperature_metric IS NULL OR temperature_metric IN (
            'land_surface_temperature', 'air_temperature',
            'wall_surface_temperature', 'mean_radiant_temperature',
            'thermal_comfort_index'
        )
    ),
    ADD COLUMN spatial_scope TEXT,
    ADD COLUMN uncertainty_method TEXT,
    ADD COLUMN evidence_reviewed_at DATE;

UPDATE model_version
SET output_precision = 'suppressed',
    temperature_metric = 'land_surface_temperature',
    spatial_scope = 'Melbourne 500 m neighbourhood baseline; intervention model not calibrated',
    uncertainty_method = 'No resident-facing temperature output until local calibration and held-out validation pass.',
    evidence_reviewed_at = DATE '2026-08-27',
    validation_status = 'validation_in_progress',
    validation_summary = 'Primary evidence selected for shade, canopy growth and surface-cooling plausibility. No transferable property-level Landsat coefficient has been validated.'
WHERE model_name = 'GreenShift scenario comparison'
  AND version_label = 'baseline-arithmetic-v1';

CREATE TABLE intervention_evidence (
    evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    citation_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    authors TEXT NOT NULL,
    publication_year INTEGER NOT NULL CHECK (publication_year BETWEEN 1900 AND 2100),
    doi TEXT UNIQUE,
    source_url TEXT NOT NULL,
    study_location TEXT NOT NULL,
    study_design TEXT NOT NULL,
    intervention_types TEXT[] NOT NULL,
    outcome_types TEXT[] NOT NULL,
    spatial_scale TEXT NOT NULL,
    reported_effects JSONB NOT NULL,
    evidence_grade TEXT NOT NULL CHECK (
        evidence_grade IN (
            'primary_field', 'primary_observational',
            'validated_simulation', 'growth_model'
        )
    ),
    transferability TEXT NOT NULL CHECK (
        transferability IN ('direct', 'supporting', 'context_only')
    ),
    approved_use TEXT NOT NULL,
    prohibited_use TEXT NOT NULL,
    limitations TEXT NOT NULL,
    selected_for_model BOOLEAN NOT NULL DEFAULT TRUE,
    reviewed_at DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE model_evidence (
    model_version_id UUID NOT NULL REFERENCES model_version(model_version_id),
    evidence_id UUID NOT NULL REFERENCES intervention_evidence(evidence_id),
    evidence_role TEXT NOT NULL CHECK (
        evidence_role IN (
            'candidate_validation', 'calibration', 'external_validation',
            'mechanism', 'limitation'
        )
    ),
    notes TEXT,
    PRIMARY KEY (model_version_id, evidence_id, evidence_role)
);

ALTER TABLE measure_result
    ALTER COLUMN result_value DROP NOT NULL,
    ADD COLUMN minimum_result_value NUMERIC,
    ADD COLUMN maximum_result_value NUMERIC,
    ADD COLUMN result_status TEXT NOT NULL DEFAULT 'internal_only' CHECK (
        result_status IN (
            'internal_only', 'indicative_range', 'validated_point_estimate'
        )
    ),
    ADD COLUMN display_disclaimer TEXT,
    ADD CONSTRAINT ck_measure_result_has_value CHECK (
        result_value IS NOT NULL
        OR (
            minimum_result_value IS NOT NULL
            AND maximum_result_value IS NOT NULL
            AND maximum_result_value >= minimum_result_value
        )
    );

INSERT INTO intervention_evidence (
    citation_key, title, authors, publication_year, doi, source_url,
    study_location, study_design, intervention_types, outcome_types,
    spatial_scale, reported_effects, evidence_grade, transferability,
    approved_use, prohibited_use, limitations, reviewed_at
)
VALUES
    (
        'coutts_2016_melbourne_street_trees',
        'Temperature and human thermal comfort effects of street trees across three contrasting street canyon environments',
        'Coutts, White, Tapper, Beringer and Livesley', 2016,
        '10.1007/s00704-015-1409-y',
        'https://doi.org/10.1007/s00704-015-1409-y',
        'Melbourne, Australia', 'Multi-site field monitoring during summer heat events',
        ARRAY['tree'], ARRAY['air_temperature', 'mean_radiant_temperature', 'thermal_comfort'],
        'street canyon',
        '{"average_daytime_air_cooling_c":[0.2,0.6],"maximum_daytime_air_cooling_c":1.5,"finding":"shade reduced radiant exposure and UTCI"}'::jsonb,
        'primary_field', 'supporting',
        'Validate the direction and local thermal-comfort benefit of tree shade.',
        'Do not use its air-temperature values as a Landsat land-surface-temperature coefficient.',
        'Street-canyon geometry and weather strongly affected results; this was not a residential parcel intervention.',
        DATE '2026-08-27'
    ),
    (
        'ossola_2021_adelaide_vegetated_patches',
        'Small vegetated patches greatly reduce urban surface temperature during a summer heatwave in Adelaide, Australia',
        'Ossola, Jenerette, McGrath, Chow, Hughes and Leishman', 2021,
        '10.1016/j.landurbplan.2021.104046',
        'https://doi.org/10.1016/j.landurbplan.2021.104046',
        'Adelaide, Australia', 'Aircraft thermal imagery and land-cover association during one heatwave',
        ARRAY['tree','garden_bed','grass'], ARRAY['land_surface_temperature'],
        'approximately 460 m2 land units and surrounding 30 m buffers',
        '{"maximum_associated_daytime_lst_reduction_c":6,"night_effect":"not detected","thermal_resolution_m":2}'::jsonb,
        'primary_observational', 'supporting',
        'Constrain the plausible upper range and spatial scale of daytime surface cooling.',
        'Do not treat the observed association or maximum as a causal per-tree coefficient.',
        'One Adelaide heatwave; vegetation effect varied by scale and distance from the coast.',
        DATE '2026-08-27'
    ),
    (
        'armson_2012_tree_shade_grass',
        'The effect of tree shade and grass on surface and globe temperatures in an urban area',
        'Armson, Stringer and Ennos', 2012,
        '10.1016/j.ufug.2012.05.002',
        'https://doi.org/10.1016/j.ufug.2012.05.002',
        'Manchester, United Kingdom', 'Repeated field experiment on sunlit and shaded grass, concrete and asphalt',
        ARRAY['tree','grass','garden_bed'], ARRAY['surface_temperature','globe_temperature'],
        'small plots and park surfaces',
        '{"maximum_grass_surface_reduction_c":24,"maximum_tree_shade_surface_reduction_c":19,"tree_shade_globe_reduction_c":[5,7]}'::jsonb,
        'primary_field', 'context_only',
        'Validate cooling mechanisms and provide a non-typical upper-envelope reasonableness check.',
        'Do not present maximum experimental surface differences as typical Melbourne property cooling.',
        'Temperate UK setting; reports maxima at directly observed surfaces rather than parcel-average Landsat cells.',
        DATE '2026-08-27'
    ),
    (
        'torquato_2025_melbourne_crown_models',
        'Insufficient space: Prioritizing large tree species and planting designs still fail to meet urban forest canopy targets',
        'Torquato, Szota, Hahs, Arndt and Livesley', 2025,
        '10.1016/j.landurbplan.2024.105287',
        'https://doi.org/10.1016/j.landurbplan.2024.105287',
        'Melbourne, Australia', 'Species-specific crown-growth modelling for residential development scenarios',
        ARRAY['tree'], ARRAY['canopy_area','shade_proxy'],
        'individual trees aggregated to development canopy over 30 years',
        '{"species_model_count":20,"horizon_years":30,"large_crown_canopy_cover_pct":[16,22],"default_canopy_cover_pct":[11,15],"low_rainfall_reduction_percentage_points":[4,6]}'::jsonb,
        'growth_model', 'direct',
        'Support species- and horizon-specific future crown area used as a shade proxy.',
        'Do not assume immediate mature canopy or apply one growth rate to all species and sites.',
        'Scenario results depend on available planting space, survival, species mix and rainfall.',
        DATE '2026-08-27'
    ),
    (
        'cybula_2026_melbourne_young_crowns',
        'Impervious Surfaces Do Not Impact Urban Tree Crown Growth',
        'Cybula, Torquato, Hahs and Arndt', 2026,
        '10.3390/f17010111',
        'https://doi.org/10.3390/f17010111',
        'Wyndham, Melbourne, Australia', 'High-resolution imagery measurements of young trees in 2014 and 2018',
        ARRAY['tree'], ARRAY['canopy_area','shade_proxy'],
        '320 young trees across eight species in streets and parks',
        '{"mean_absolute_crown_growth_m2_per_year":2.3,"measurement_period_years":4,"species_count":8}'::jsonb,
        'primary_observational', 'direct',
        'Use as a local plausibility check or prior for young-tree crown growth.',
        'Do not use 2.3 m2/year as a universal backyard, container-tree or mature-tree growth coefficient.',
        'Young trees in one low-rainfall LGA; substantial species and site variability remained.',
        DATE '2026-08-27'
    ),
    (
        'hoelscher_2016_facade_greening',
        'Quantifying cooling effects of facade greening: Shading, transpiration and insulation',
        'Hoelscher, Nehls, Janicke and Wessolek', 2016,
        '10.1016/j.enbuild.2015.06.047',
        'https://doi.org/10.1016/j.enbuild.2015.06.047',
        'Berlin, Germany', 'Outdoor experiments on three directly greened facades',
        ARRAY['green_wall'], ARRAY['wall_surface_temperature','air_temperature'],
        'building facade and adjacent street canyon',
        '{"maximum_exterior_wall_reduction_c":15.5,"maximum_interior_wall_reduction_c":1.7,"street_canyon_air_cooling":"not detected"}'::jsonb,
        'primary_field', 'supporting',
        'Support a separately labelled wall-surface benefit for irrigated facade greening.',
        'Do not translate wall-surface cooling into property, neighbourhood or ambient-air cooling.',
        'Berlin climate, three facades and species-dependent irrigation demand.',
        DATE '2026-08-27'
    ),
    (
        'balany_2022_melbourne_bgi',
        'Studying the Effect of Blue-Green Infrastructure on Microclimate and Human Thermal Comfort in Melbourne CBD',
        'Balany, Muttil, Muthukumaran, Wong and Ng', 2022,
        '10.3390/su14159057',
        'https://doi.org/10.3390/su14159057',
        'Melbourne CBD, Australia', 'ENVI-met scenarios validated against field air temperature and humidity',
        ARRAY['tree','green_wall','green_roof'], ARRAY['air_temperature','mean_radiant_temperature','thermal_comfort'],
        'dense high-rise CBD scenarios',
        '{"double_tree_max_air_cooling_c":0.69,"triple_tree_max_air_cooling_c":0.93,"double_tree_average_air_cooling_c":0.3,"triple_tree_average_air_cooling_c":0.5,"tree_mrt_reduction_c":[5.5,7.6],"green_wall_max_air_cooling_c":0.27}'::jsonb,
        'validated_simulation', 'context_only',
        'Cross-check Melbourne direction, ranking of actions and the importance of tree shade.',
        'Do not transfer CBD air-temperature scenario outputs to residential Landsat cells or individual interventions.',
        'Simulated mature plane trees and large proportional changes in a high-rise CBD geometry.',
        DATE '2026-08-27'
    )
ON CONFLICT (citation_key) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    reported_effects = EXCLUDED.reported_effects,
    approved_use = EXCLUDED.approved_use,
    prohibited_use = EXCLUDED.prohibited_use,
    limitations = EXCLUDED.limitations,
    reviewed_at = EXCLUDED.reviewed_at;

INSERT INTO model_evidence (model_version_id, evidence_id, evidence_role, notes)
SELECT
    model.model_version_id,
    evidence.evidence_id,
    'candidate_validation',
    'Selected evidence only; inclusion does not imply that a transferable temperature coefficient has been validated.'
FROM model_version AS model
CROSS JOIN intervention_evidence AS evidence
WHERE model.model_name = 'GreenShift scenario comparison'
  AND model.version_label = 'baseline-arithmetic-v1'
ON CONFLICT DO NOTHING;

INSERT INTO analytical_measure (
    measure_code, measure_name, description, formula_text, output_unit
)
VALUES (
    'projected_canopy_proxy_shade_m2',
    'Projected canopy proxy for shade',
    'Future crown area discounted for survival, site suitability and canopy overlap at an explicit maturity horizon.',
    'projected_canopy_m2 * survival_probability * site_suitability_factor * overlap_factor',
    'm2'
)
ON CONFLICT (measure_code) DO UPDATE SET
    measure_name = EXCLUDED.measure_name,
    description = EXCLUDED.description,
    formula_text = EXCLUDED.formula_text,
    output_unit = EXCLUDED.output_unit,
    active = TRUE;

CREATE OR REPLACE VIEW application_ready_measure_result AS
SELECT result.*
FROM measure_result AS result
JOIN analysis_run AS run USING (analysis_run_id)
JOIN model_version AS model USING (model_version_id)
JOIN analytical_measure AS measure USING (measure_id)
WHERE model.validation_status = 'validated'
  AND run.run_status = 'completed'
  AND result.result_status <> 'internal_only'
  AND (
      measure.measure_code <> 'estimated_heat_reduction_c'
      OR (
          model.output_precision = 'precise_point_estimate'
          AND result.result_status = 'validated_point_estimate'
      )
  );

CREATE OR REPLACE VIEW selected_intervention_evidence AS
SELECT
    evidence_id,
    citation_key,
    title,
    authors,
    publication_year,
    doi,
    source_url,
    study_location,
    study_design,
    intervention_types,
    outcome_types,
    spatial_scale,
    reported_effects,
    evidence_grade,
    transferability,
    approved_use,
    prohibited_use,
    limitations,
    reviewed_at
FROM intervention_evidence
WHERE selected_for_model;

COMMENT ON TABLE intervention_evidence IS
    'Reviewed primary studies and explicit rules for what each study may and may not support in the intervention model.';
COMMENT ON COLUMN model_version.output_precision IS
    'Separate from validation status so validated indicative ranges cannot expose precise after-temperatures.';
COMMENT ON VIEW selected_intervention_evidence IS
    'Traceable evidence register for the intervention-impact model; reported maxima are evidence, not default coefficients.';

COMMIT;
