INSERT INTO dataset_source (
    source_name,
    publisher,
    source_url,
    licence,
    source_category,
    geographic_coverage,
    access_method,
    update_frequency
)
VALUES
    ('Vicmap Property', 'Victorian Government', 'https://data.gov.au/data/dataset/vicmap-property1', 'CC BY 4.0', 'property', 'Victoria', 'download and spatial web services', 'continuously maintained'),
    ('Vicmap Address', 'Victorian Government', 'https://www.data.gov.au/data/dataset/vicmap-address1', 'CC BY 4.0', 'address', 'Victoria', 'download and spatial web services', 'continuously maintained'),
    ('Vicmap Vegetation - Tree Urban Point', 'Victorian Government', 'https://discover.data.vic.gov.au/dataset/vicmap-vegetation-tree-urban-point', 'CC BY 4.0', 'canopy', 'Metropolitan Melbourne', 'WFS, WMS, REST and download', 'irregular'),
    ('Vicmap Vegetation - Tree Extent', 'Victorian Government', 'https://discover.data.vic.gov.au/dataset/vicmap-vegetation-tree-extent', 'CC BY 4.0', 'canopy', 'Victoria', 'GeoTIFF, REST and download', 'irregular'),
    ('Tree Canopies 2021 (Urban Forest)', 'City of Melbourne', 'https://discover.data.vic.gov.au/en_AU/dataset/tree-canopies-2021-urban-forest', 'CC BY 4.0', 'canopy', 'City of Melbourne municipality', 'API and download', 'unknown'),
    ('DEA Sentinel-2 Surface Reflectance', 'Geoscience Australia', 'https://knowledge.dea.ga.gov.au/data/product/dea-surface-reflectance-sentinel-2a-msi/', 'CC BY 4.0', 'vegetation', 'Australia', 'STAC, AWS, WMS and download', 'ongoing'),
    ('USGS Landsat Collection 2 Surface Temperature', 'United States Geological Survey', 'https://www.usgs.gov/landsat-missions/landsat-collection-2-surface-temperature', 'US public domain', 'heat', 'Global', 'STAC, EarthExplorer and cloud download', 'ongoing'),
    ('Metropolitan Melbourne Urban Heat Islands and Urban Vegetation 2018', 'Victorian Government', 'https://discover.data.vic.gov.au/en_AU/dataset/metropolitan-melbourne-urban-heat-islands-and-urban-vegetation-2018', 'CC BY 4.0', 'heat', 'Metropolitan Melbourne', 'spatial download', 'unknown'),
    ('BOM Melbourne Olympic Park observations', 'Bureau of Meteorology', 'https://www.bom.gov.au/fwo/IDV60901/IDV60901.95936.json', NULL, 'weather', 'Melbourne Olympic Park station', 'JSON feed', 'frequent')
ON CONFLICT (source_name, publisher) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    licence = EXCLUDED.licence,
    source_category = EXCLUDED.source_category,
    geographic_coverage = EXCLUDED.geographic_coverage,
    access_method = EXCLUDED.access_method,
    update_frequency = EXCLUDED.update_frequency;

INSERT INTO data_quality_rule (
    rule_code,
    rule_name,
    quality_dimension,
    target_table,
    target_column,
    rule_description,
    failure_severity,
    minimum_pass_rate
)
VALUES
    ('SOURCE_ID_REQUIRED', 'Source identifier is present', 'completeness', 'staging', 'source_id', 'Every source record must retain a source identifier.', 'critical', 100.00),
    ('GEOMETRY_REQUIRED', 'Geometry is present', 'completeness', 'spatial staging', 'geometry', 'Spatial records must contain geometry before integration.', 'critical', 95.00),
    ('GEOMETRY_VALID', 'Geometry is valid', 'validity', 'spatial staging', 'geometry', 'Geometry must pass the PostGIS validity check after repair.', 'high', 95.00),
    ('PERCENT_RANGE', 'Percentage is in range', 'validity', 'environment staging', NULL, 'Percentage values must be between zero and one hundred.', 'high', 100.00),
    ('BUSINESS_KEY_UNIQUE', 'Source business key is unique', 'uniqueness', 'staging', NULL, 'Unexpected duplicate source keys must be quarantined.', 'critical', 100.00),
    ('TARGET_SRID', 'Geometry uses target SRID', 'consistency', 'spatial staging', 'geometry', 'Integrated geometry must use the configured target SRID 7855.', 'high', 100.00),
    ('MELBOURNE_COVERAGE', 'Required Melbourne coverage', 'coverage', 'integrated spatial data', NULL, 'Required source layers must cover at least 95 percent of the supported study area.', 'high', 95.00)
ON CONFLICT (rule_code) DO UPDATE SET
    rule_name = EXCLUDED.rule_name,
    rule_description = EXCLUDED.rule_description,
    failure_severity = EXCLUDED.failure_severity,
    minimum_pass_rate = EXCLUDED.minimum_pass_rate,
    active = TRUE;

INSERT INTO greening_option (
    option_code,
    option_name,
    option_category,
    cost_unit,
    description
)
VALUES
    ('backyard_tree_diy', 'Small backyard tree - DIY', 'tree', 'per_tree', 'Small tree planted by the resident.'),
    ('backyard_tree_installed', 'Small backyard tree - installed', 'tree', 'per_tree', 'Small tree supplied and professionally installed.'),
    ('container_tree', 'Small container tree', 'tree', 'per_tree', 'Small tree grown in a suitable large container.'),
    ('potted_plants', 'Potted plants', 'plants', 'per_pot', 'Potted plants for constrained residential spaces.'),
    ('garden_bed', 'Garden bed', 'plants', 'per_m2', 'Mixed planting in a new or improved garden bed.'),
    ('green_wall', 'Green wall', 'vertical_greening', 'per_m2', 'Modular or climbing-system vertical greening.'),
    ('green_roof', 'Green roof', 'roof_greening', 'per_m2', 'Roof greening subject to structural suitability.'),
    ('community_tree', 'Community tree planting', 'tree', 'per_tree', 'Aggregated planting for a community proposal.')
ON CONFLICT (option_code) DO UPDATE SET
    option_name = EXCLUDED.option_name,
    option_category = EXCLUDED.option_category,
    cost_unit = EXCLUDED.cost_unit,
    description = EXCLUDED.description,
    active = TRUE;

INSERT INTO analytical_measure (
    measure_code,
    measure_name,
    description,
    formula_text,
    output_unit
)
VALUES
    ('canopy_gain_m2', 'Canopy gain', 'Projected canopy area minus baseline canopy area.', 'projected_canopy_m2 - baseline_canopy_m2', 'm2'),
    ('greening_gain_pct', 'Greening gain', 'Projected greenery percentage minus baseline greenery percentage.', 'projected_greenery_pct - baseline_greenery_pct', 'percentage_points'),
    ('estimated_heat_reduction_c', 'Estimated surface heat reduction', 'Baseline land-surface temperature minus modelled scenario land-surface temperature.', 'baseline_surface_temperature_c - projected_surface_temperature_c', 'degC'),
    ('cost_per_canopy_m2', 'Cost per canopy gain', 'Indicative scenario cost divided by positive canopy gain.', 'total_cost / canopy_gain_m2', 'AUD_per_m2')
ON CONFLICT (measure_code) DO UPDATE SET
    measure_name = EXCLUDED.measure_name,
    description = EXCLUDED.description,
    formula_text = EXCLUDED.formula_text,
    output_unit = EXCLUDED.output_unit,
    active = TRUE;

INSERT INTO model_version (
    model_name,
    version_label,
    method_description
)
VALUES (
    'GreenShift scenario comparison',
    'baseline-arithmetic-v1',
    'Transparent arithmetic test model. Heat projections must later be supplied by a separately validated environmental model.'
)
ON CONFLICT (model_name, version_label) DO UPDATE SET
    method_description = EXCLUDED.method_description;

INSERT INTO measure_test_case (
    measure_id,
    test_case_name,
    input_values,
    expected_value,
    tolerance
)
SELECT
    measure_id,
    'basic canopy gain',
    '{"baseline_canopy_m2": 25, "projected_canopy_m2": 40}'::jsonb,
    15,
    0
FROM analytical_measure
WHERE measure_code = 'canopy_gain_m2'
ON CONFLICT (measure_id, test_case_name) DO UPDATE SET
    input_values = EXCLUDED.input_values,
    expected_value = EXCLUDED.expected_value,
    tolerance = EXCLUDED.tolerance,
    active = TRUE;

INSERT INTO measure_test_case (
    measure_id,
    test_case_name,
    input_values,
    expected_value,
    tolerance
)
SELECT
    measure_id,
    'basic greening percentage-point gain',
    '{"baseline_greenery_pct": 18.5, "projected_greenery_pct": 31}'::jsonb,
    12.5,
    0
FROM analytical_measure
WHERE measure_code = 'greening_gain_pct'
ON CONFLICT (measure_id, test_case_name) DO UPDATE SET
    input_values = EXCLUDED.input_values,
    expected_value = EXCLUDED.expected_value,
    tolerance = EXCLUDED.tolerance,
    active = TRUE;

INSERT INTO measure_test_case (
    measure_id,
    test_case_name,
    input_values,
    expected_value,
    tolerance
)
SELECT
    measure_id,
    'basic modelled heat reduction',
    '{"baseline_surface_temperature_c": 43.2, "projected_surface_temperature_c": 40.7}'::jsonb,
    2.5,
    0.001
FROM analytical_measure
WHERE measure_code = 'estimated_heat_reduction_c'
ON CONFLICT (measure_id, test_case_name) DO UPDATE SET
    input_values = EXCLUDED.input_values,
    expected_value = EXCLUDED.expected_value,
    tolerance = EXCLUDED.tolerance,
    active = TRUE;
