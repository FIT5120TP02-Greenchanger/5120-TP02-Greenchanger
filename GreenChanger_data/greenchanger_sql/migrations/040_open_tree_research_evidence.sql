BEGIN;

INSERT INTO dataset_source (
    source_name, publisher, source_url, licence, licence_status,
    source_category, geographic_coverage, access_method, update_frequency
)
VALUES
    (
        'AusTraits 7.0.0', 'AusTraits collaboration',
        'https://github.com/traitecoevo/austraits.build/releases/tag/v7.0.0',
        'Creative Commons Attribution 4.0 International', 'open_confirmed',
        'plant_traits', 'Australia', 'Versioned GitHub release ZIP',
        'versioned research release'
    ),
    (
        'Tree growth of 10 tree species planted in seven Australian cities',
        'Esperon-Rodriguez et al.',
        'https://figshare.com/articles/dataset/Tree_growth_of_10_urban_tree_species_in_seven_Australian_cities/28970981',
        'Creative Commons Attribution 4.0 International', 'open_confirmed',
        'urban_tree_growth',
        'Seven Australian cities, including Melbourne and Mildura',
        'Figshare version 2 XLSX downloads', 'static research deposit'
    )
ON CONFLICT (source_name, publisher) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    licence = EXCLUDED.licence,
    licence_status = EXCLUDED.licence_status,
    source_category = EXCLUDED.source_category,
    geographic_coverage = EXCLUDED.geographic_coverage,
    access_method = EXCLUDED.access_method,
    update_frequency = EXCLUDED.update_frequency;

CREATE TABLE plant_trait_observation (
    plant_trait_observation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    source_row_number BIGINT NOT NULL,
    dataset_id TEXT NOT NULL,
    observation_id TEXT,
    taxon_name TEXT NOT NULL,
    original_name TEXT,
    trait_name TEXT NOT NULL,
    value_text TEXT NOT NULL,
    value_numeric NUMERIC,
    unit TEXT,
    entity_type TEXT,
    value_type TEXT,
    basis_of_value TEXT,
    replicates NUMERIC,
    basis_of_record TEXT,
    life_stage TEXT,
    location_id TEXT,
    collection_date TEXT,
    source_dataset_id TEXT,
    measurement_remarks TEXT,
    quality_status TEXT NOT NULL DEFAULT 'passed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (dataset_version_id, source_row_number)
);

CREATE INDEX idx_plant_trait_taxon_trait
    ON plant_trait_observation(taxon_name, trait_name);
CREATE INDEX idx_plant_trait_version_trait
    ON plant_trait_observation(dataset_version_id, trait_name);

CREATE TABLE urban_tree_growth_observation (
    urban_tree_growth_observation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    source_row_number BIGINT NOT NULL,
    city TEXT NOT NULL,
    species_name_original TEXT NOT NULL,
    species_name TEXT NOT NULL,
    tree_number INTEGER NOT NULL,
    ring_sequence INTEGER NOT NULL CHECK (ring_sequence > 0),
    tree_ring_width_mm NUMERIC NOT NULL CHECK (tree_ring_width_mm > 0),
    basal_area_increment_cm2_year NUMERIC CHECK (
        basal_area_increment_cm2_year IS NULL
        OR basal_area_increment_cm2_year >= 0
    ),
    quality_status TEXT NOT NULL DEFAULT 'passed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (dataset_version_id, source_row_number),
    UNIQUE (dataset_version_id, city, species_name, tree_number, ring_sequence)
);

CREATE INDEX idx_tree_growth_species_city
    ON urban_tree_growth_observation(species_name, city);

CREATE TABLE urban_tree_growth_climate (
    urban_tree_growth_climate_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    source_row_number BIGINT NOT NULL,
    city TEXT NOT NULL,
    observation_year INTEGER NOT NULL CHECK (observation_year BETWEEN 1900 AND 2100),
    variant_number INTEGER NOT NULL CHECK (variant_number > 0),
    source_occurrence_count INTEGER NOT NULL CHECK (source_occurrence_count > 0),
    city_year_ambiguous BOOLEAN NOT NULL,
    annual_precipitation_mm NUMERIC,
    precipitation_driest_month_mm NUMERIC,
    precipitation_wettest_month_mm NUMERIC,
    precipitation_driest_quarter_mm NUMERIC,
    mean_temperature_warmest_month_c NUMERIC,
    mean_annual_temperature_c NUMERIC,
    mean_temperature_coldest_month_c NUMERIC,
    isothermality_divided_by_100 NUMERIC,
    precipitation_index NUMERIC,
    quality_status TEXT NOT NULL DEFAULT 'passed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (dataset_version_id, city, observation_year, variant_number)
);

CREATE INDEX idx_tree_growth_climate_city_year
    ON urban_tree_growth_climate(city, observation_year);

CREATE OR REPLACE VIEW latest_austraits_observation AS
WITH current_version AS (
    SELECT version.dataset_version_id
    FROM dataset_version AS version
    JOIN dataset_source AS source USING (source_id)
    WHERE source.source_name = 'AusTraits 7.0.0'
      AND source.publisher = 'AusTraits collaboration'
      AND version.integration_status = 'integrated'
      AND version.quality_status IN ('passed', 'passed_with_limitations')
    ORDER BY version.extracted_at DESC, version.dataset_version_id DESC
    LIMIT 1
)
SELECT observation.*
FROM plant_trait_observation AS observation
JOIN current_version USING (dataset_version_id)
WHERE observation.quality_status = 'passed';

CREATE OR REPLACE VIEW austraits_adult_species_trait_summary AS
SELECT
    taxon_name, trait_name, unit,
    COUNT(*) AS observation_count,
    MIN(value_numeric) AS minimum_observed_value,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY value_numeric)
        FILTER (WHERE value_numeric IS NOT NULL) AS median_observed_value,
    MAX(value_numeric) AS maximum_observed_value
FROM latest_austraits_observation
WHERE entity_type = 'species'
  AND (life_stage IS NULL OR LOWER(life_stage) = 'adult')
GROUP BY taxon_name, trait_name, unit;

CREATE OR REPLACE VIEW latest_urban_tree_growth_observation AS
WITH current_version AS (
    SELECT version.dataset_version_id
    FROM dataset_version AS version
    JOIN dataset_source AS source USING (source_id)
    WHERE source.source_name = 'Tree growth of 10 tree species planted in seven Australian cities'
      AND source.publisher = 'Esperon-Rodriguez et al.'
      AND version.integration_status = 'integrated'
      AND version.quality_status IN ('passed', 'passed_with_limitations')
    ORDER BY version.extracted_at DESC, version.dataset_version_id DESC
    LIMIT 1
)
SELECT observation.*
FROM urban_tree_growth_observation AS observation
JOIN current_version USING (dataset_version_id)
WHERE observation.quality_status = 'passed';

CREATE OR REPLACE VIEW usable_urban_tree_growth_climate AS
WITH current_version AS (
    SELECT version.dataset_version_id
    FROM dataset_version AS version
    JOIN dataset_source AS source USING (source_id)
    WHERE source.source_name = 'Tree growth of 10 tree species planted in seven Australian cities'
      AND source.publisher = 'Esperon-Rodriguez et al.'
      AND version.integration_status = 'integrated'
      AND version.quality_status IN ('passed', 'passed_with_limitations')
    ORDER BY version.extracted_at DESC, version.dataset_version_id DESC
    LIMIT 1
)
SELECT climate.*
FROM urban_tree_growth_climate AS climate
JOIN current_version USING (dataset_version_id)
WHERE climate.quality_status = 'passed'
  AND NOT climate.city_year_ambiguous;

INSERT INTO predictive_model_source (
    model_code, source_id, source_role, required_for_training,
    training_use_allowed, licence_decision
)
SELECT
    'tree_canopy_growth', source.source_id,
    CASE source.source_name
        WHEN 'AusTraits 7.0.0'
            THEN 'optional species trait context; not horticultural site advice'
        ELSE 'optional observed Australian tree-ring growth evidence'
    END,
    FALSE, TRUE, 'CC BY 4.0 confirmed; attribution required'
FROM dataset_source AS source
WHERE (source.source_name = 'AusTraits 7.0.0'
       AND source.publisher = 'AusTraits collaboration')
   OR (source.source_name = 'Tree growth of 10 tree species planted in seven Australian cities'
       AND source.publisher = 'Esperon-Rodriguez et al.')
ON CONFLICT (model_code, source_id) DO UPDATE SET
    source_role = EXCLUDED.source_role,
    required_for_training = EXCLUDED.required_for_training,
    training_use_allowed = EXCLUDED.training_use_allowed,
    licence_decision = EXCLUDED.licence_decision;

UPDATE predictive_model_specification
SET feature_contract = feature_contract ||
        '["austraits_trait_context","tree_ring_growth_context"]'::jsonb,
    limitations = limitations ||
        ' AusTraits observations are not nursery maturity specifications, water-needs classes, root-risk ratings or allergen ratings. Tree-ring width and basal-area increment do not directly measure canopy area, and require a separately validated allometric link.',
    updated_at = CURRENT_TIMESTAMP
WHERE model_code = 'tree_canopy_growth'
  AND NOT feature_contract @> '["austraits_trait_context"]'::jsonb;

COMMENT ON TABLE plant_trait_observation IS
    'Selected, versioned AusTraits observations relevant to prototype research. Values retain their source context and are not direct planting recommendations.';
COMMENT ON VIEW austraits_adult_species_trait_summary IS
    'Descriptive adult/species observations only; observed height is not guaranteed mature nursery height and physiological water-use efficiency is not a horticultural water-needs rating.';
COMMENT ON TABLE urban_tree_growth_observation IS
    'Tree-ring width and basal-area increment from the seven-city study. ring_sequence is source row order within a tree, not age or calendar year.';
COMMENT ON TABLE urban_tree_growth_climate IS
    'Exact duplicate source rows are collapsed with a count. Conflicting city-year variants are retained and flagged rather than silently selected.';
COMMENT ON VIEW usable_urban_tree_growth_climate IS
    'Complete, unambiguous climate rows only. These cannot be joined to growth rings by year because the published growth workbook has no calendar-year field.';

COMMIT;
