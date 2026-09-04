BEGIN;

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS dataset_source (
    source_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name TEXT NOT NULL,
    publisher TEXT NOT NULL,
    source_url TEXT NOT NULL,
    licence TEXT,
    source_category TEXT NOT NULL,
    geographic_coverage TEXT,
    access_method TEXT,
    update_frequency TEXT,
    expected_spatial_resolution_m NUMERIC CHECK (
        expected_spatial_resolution_m IS NULL
        OR expected_spatial_resolution_m > 0
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_name, publisher)
);

CREATE TABLE IF NOT EXISTS dataset_version (
    dataset_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES dataset_source(source_id),
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_updated_at TIMESTAMPTZ,
    source_observed_from DATE,
    source_observed_to DATE,
    spatial_resolution_m NUMERIC CHECK (
        spatial_resolution_m IS NULL OR spatial_resolution_m > 0
    ),
    coverage_pass_rate NUMERIC(5, 2) CHECK (
        coverage_pass_rate IS NULL OR coverage_pass_rate BETWEEN 0 AND 100
    ),
    cloud_cover_pct NUMERIC(5, 2) CHECK (
        cloud_cover_pct IS NULL OR cloud_cover_pct BETWEEN 0 AND 100
    ),
    raw_row_count BIGINT CHECK (raw_row_count IS NULL OR raw_row_count >= 0),
    checksum TEXT,
    quality_pass_rate NUMERIC(5, 2) CHECK (
        quality_pass_rate IS NULL OR quality_pass_rate BETWEEN 0 AND 100
    ),
    quality_status TEXT NOT NULL DEFAULT 'pending' CHECK (
        quality_status IN ('pending', 'passed', 'failed', 'passed_with_limitations')
    ),
    integration_status TEXT NOT NULL DEFAULT 'not_started' CHECK (
        integration_status IN ('not_started', 'running', 'integrated', 'failed')
    ),
    publication_status TEXT NOT NULL DEFAULT 'internal' CHECK (
        publication_status IN ('internal', 'application_ready', 'retired')
    ),
    parent_version_id UUID REFERENCES dataset_version(dataset_version_id),
    analysis_area_id UUID,
    derivation_method TEXT,
    CHECK (
        source_observed_to IS NULL
        OR source_observed_from IS NULL
        OR source_observed_to >= source_observed_from
    )
);

CREATE TABLE IF NOT EXISTS spatial_asset (
    spatial_asset_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    asset_role TEXT NOT NULL,
    source_scene_id TEXT NOT NULL DEFAULT '',
    source_href TEXT,
    local_path TEXT,
    media_type TEXT,
    source_crs TEXT,
    target_srid INTEGER,
    pixel_size_m NUMERIC CHECK (pixel_size_m IS NULL OR pixel_size_m > 0),
    checksum TEXT,
    acquired_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (dataset_version_id, asset_role, source_scene_id)
);

CREATE TABLE IF NOT EXISTS data_quality_rule (
    quality_rule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_code TEXT NOT NULL UNIQUE,
    rule_name TEXT NOT NULL,
    quality_dimension TEXT NOT NULL CHECK (
        quality_dimension IN (
            'completeness',
            'validity',
            'consistency',
            'uniqueness',
            'integrity',
            'timeliness',
            'coverage'
        )
    ),
    target_table TEXT NOT NULL,
    target_column TEXT,
    rule_description TEXT NOT NULL,
    failure_severity TEXT NOT NULL DEFAULT 'high' CHECK (
        failure_severity IN ('low', 'medium', 'high', 'critical')
    ),
    minimum_pass_rate NUMERIC(5, 2) NOT NULL DEFAULT 95.00 CHECK (
        minimum_pass_rate BETWEEN 0 AND 100
    ),
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS data_quality_run (
    quality_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    assessed_record_count BIGINT CHECK (
        assessed_record_count IS NULL OR assessed_record_count >= 0
    ),
    passing_record_count BIGINT CHECK (
        passing_record_count IS NULL OR passing_record_count >= 0
    ),
    failing_record_count BIGINT CHECK (
        failing_record_count IS NULL OR failing_record_count >= 0
    ),
    overall_pass_rate NUMERIC(5, 2) CHECK (
        overall_pass_rate IS NULL OR overall_pass_rate BETWEEN 0 AND 100
    ),
    run_status TEXT NOT NULL DEFAULT 'running' CHECK (
        run_status IN ('running', 'passed', 'failed', 'cancelled')
    ),
    CHECK (completed_at IS NULL OR completed_at >= started_at),
    CHECK (
        assessed_record_count IS NULL
        OR passing_record_count IS NULL
        OR failing_record_count IS NULL
        OR assessed_record_count = passing_record_count + failing_record_count
    )
);

CREATE TABLE IF NOT EXISTS data_quality_result (
    quality_result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quality_run_id UUID NOT NULL REFERENCES data_quality_run(quality_run_id),
    quality_rule_id UUID NOT NULL REFERENCES data_quality_rule(quality_rule_id),
    assessed_count BIGINT NOT NULL CHECK (assessed_count >= 0),
    passed_count BIGINT NOT NULL CHECK (passed_count >= 0),
    failed_count BIGINT NOT NULL CHECK (failed_count >= 0),
    pass_rate NUMERIC(5, 2) NOT NULL CHECK (pass_rate BETWEEN 0 AND 100),
    sample_failure JSONB,
    result_status TEXT NOT NULL CHECK (
        result_status IN ('passed', 'failed', 'warning')
    ),
    UNIQUE (quality_run_id, quality_rule_id),
    CHECK (assessed_count = passed_count + failed_count)
);

CREATE TABLE IF NOT EXISTS transformation_run (
    transformation_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    input_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    output_version_id UUID REFERENCES dataset_version(dataset_version_id),
    transformation_name TEXT NOT NULL,
    script_version TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    input_record_count BIGINT CHECK (input_record_count IS NULL OR input_record_count >= 0),
    output_record_count BIGINT CHECK (output_record_count IS NULL OR output_record_count >= 0),
    rejected_record_count BIGINT CHECK (rejected_record_count IS NULL OR rejected_record_count >= 0),
    run_status TEXT NOT NULL DEFAULT 'running' CHECK (
        run_status IN ('running', 'completed', 'failed')
    ),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS integration_run (
    integration_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    target_table TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    inserted_count BIGINT CHECK (inserted_count IS NULL OR inserted_count >= 0),
    updated_count BIGINT CHECK (updated_count IS NULL OR updated_count >= 0),
    rejected_count BIGINT CHECK (rejected_count IS NULL OR rejected_count >= 0),
    run_status TEXT NOT NULL DEFAULT 'running' CHECK (
        run_status IN ('running', 'completed', 'failed')
    ),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS data_limitation (
    limitation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    limitation_type TEXT NOT NULL,
    description TEXT NOT NULL,
    affected_area TEXT,
    analytical_impact TEXT,
    mitigation TEXT,
    documented_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS analysis_area (
    analysis_area_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID REFERENCES dataset_version(dataset_version_id),
    area_name TEXT NOT NULL,
    area_type TEXT NOT NULL,
    boundary_geometry geometry(MultiPolygon, 7855) NOT NULL,
    area_m2 NUMERIC CHECK (area_m2 IS NULL OR area_m2 > 0),
    support_status TEXT NOT NULL DEFAULT 'supported',
    supported_from DATE,
    supported_to DATE,
    source_area_code TEXT,
    source_year SMALLINT,
    source_area_sqkm NUMERIC,
    source_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (area_name, area_type)
);

ALTER TABLE dataset_version
    ADD CONSTRAINT fk_dataset_version_analysis_area
    FOREIGN KEY (analysis_area_id) REFERENCES analysis_area(analysis_area_id);

CREATE TABLE IF NOT EXISTS analysis_area_tile (
    analysis_area_tile_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    analysis_area_id UUID NOT NULL REFERENCES analysis_area(analysis_area_id) ON DELETE CASCADE,
    tile_geometry geometry(Geometry, 7855) NOT NULL
);

CREATE TABLE IF NOT EXISTS address (
    address_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    source_address_id TEXT,
    source_property_id TEXT,
    full_address TEXT NOT NULL,
    locality_name TEXT,
    postcode TEXT,
    lga_code TEXT,
    is_primary TEXT,
    address_class TEXT,
    address_location geometry(Point, 7855) NOT NULL,
    UNIQUE (dataset_version_id, source_address_id)
);

CREATE TABLE IF NOT EXISTS parcel (
    parcel_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    source_parcel_id TEXT NOT NULL,
    property_number TEXT,
    property_type TEXT,
    property_status TEXT,
    lga_code TEXT,
    parcel_geometry geometry(MultiPolygon, 7855) NOT NULL,
    parcel_area_m2 NUMERIC CHECK (parcel_area_m2 IS NULL OR parcel_area_m2 > 0),
    UNIQUE (dataset_version_id, source_parcel_id)
);

CREATE TABLE IF NOT EXISTS site (
    site_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_area_id UUID NOT NULL REFERENCES analysis_area(analysis_area_id),
    address_id UUID REFERENCES address(address_id),
    parcel_id UUID REFERENCES parcel(parcel_id),
    site_name TEXT,
    site_type TEXT NOT NULL DEFAULT 'residential',
    site_geometry geometry(Geometry, 7855) NOT NULL,
    total_area_m2 NUMERIC CHECK (total_area_m2 IS NULL OR total_area_m2 > 0),
    active_status TEXT NOT NULL DEFAULT 'active' CHECK (
        active_status IN ('active', 'inactive')
    )
);

CREATE TABLE IF NOT EXISTS species_profile (
    species_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scientific_name TEXT NOT NULL UNIQUE,
    common_name TEXT,
    mature_height_m NUMERIC CHECK (mature_height_m IS NULL OR mature_height_m > 0),
    mature_canopy_radius_m NUMERIC CHECK (
        mature_canopy_radius_m IS NULL OR mature_canopy_radius_m > 0
    ),
    root_risk_class TEXT,
    water_need_class TEXT,
    suitable_for_container BOOLEAN,
    source_reference TEXT
);

CREATE TABLE IF NOT EXISTS weather_observation (
    weather_observation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    station_code TEXT NOT NULL,
    station_name TEXT,
    observation_location geometry(Point, 7855),
    observed_at TIMESTAMPTZ NOT NULL,
    air_temperature_c NUMERIC,
    apparent_temperature_c NUMERIC,
    humidity_pct NUMERIC(5, 2) CHECK (
        humidity_pct IS NULL OR humidity_pct BETWEEN 0 AND 100
    ),
    wind_speed_ms NUMERIC CHECK (wind_speed_ms IS NULL OR wind_speed_ms >= 0),
    rainfall_since_9am_mm NUMERIC CHECK (
        rainfall_since_9am_mm IS NULL OR rainfall_since_9am_mm >= 0
    ),
    quality_status TEXT NOT NULL DEFAULT 'unreviewed',
    UNIQUE (dataset_version_id, station_code, observed_at)
);

CREATE TABLE IF NOT EXISTS heat_observation (
    heat_observation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    site_id UUID REFERENCES site(site_id),
    observation_geometry geometry(Geometry, 7855) NOT NULL,
    observed_on DATE NOT NULL,
    observed_at TIMESTAMPTZ,
    heat_value NUMERIC NOT NULL,
    measurement_type TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT 'degC',
    source_scene_id TEXT,
    cloud_cover_pct NUMERIC(5, 2) CHECK (
        cloud_cover_pct IS NULL OR cloud_cover_pct BETWEEN 0 AND 100
    ),
    quality_status TEXT NOT NULL DEFAULT 'unreviewed'
);

CREATE TABLE IF NOT EXISTS heat_baseline_cell (
    heat_baseline_cell_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    analysis_area_id UUID NOT NULL REFERENCES analysis_area(analysis_area_id),
    cell_geometry geometry(Polygon, 7855) NOT NULL,
    baseline_surface_temperature_c NUMERIC NOT NULL CHECK (
        baseline_surface_temperature_c BETWEEN -50 AND 80
    ),
    observed_on DATE NOT NULL,
    observation_count INTEGER NOT NULL CHECK (observation_count > 0),
    scene_count INTEGER NOT NULL CHECK (scene_count > 0),
    source_scene_ids TEXT[] NOT NULL,
    mean_cloud_cover_pct NUMERIC(5, 2) CHECK (
        mean_cloud_cover_pct IS NULL OR mean_cloud_cover_pct BETWEEN 0 AND 100
    ),
    minimum_contributing_temperature_c NUMERIC NOT NULL,
    maximum_contributing_temperature_c NUMERIC NOT NULL,
    same_day_spread_c NUMERIC NOT NULL CHECK (same_day_spread_c >= 0),
    baseline_method TEXT NOT NULL,
    quality_status TEXT NOT NULL DEFAULT 'unreviewed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (minimum_contributing_temperature_c <= baseline_surface_temperature_c),
    CHECK (maximum_contributing_temperature_c >= baseline_surface_temperature_c),
    UNIQUE (dataset_version_id, cell_geometry)
);

CREATE TABLE IF NOT EXISTS canopy_baseline_cell (
    canopy_baseline_cell_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    analysis_area_id UUID NOT NULL REFERENCES analysis_area(analysis_area_id),
    cell_geometry geometry(Polygon, 7855) NOT NULL,
    canopy_percentage NUMERIC(5, 2) NOT NULL CHECK (canopy_percentage BETWEEN 0 AND 100),
    observed_on DATE NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('analytical_geotiff', 'api_tile_proxy')),
    source_pixel_size_m NUMERIC NOT NULL CHECK (source_pixel_size_m > 0),
    grid_size_m NUMERIC NOT NULL CHECK (grid_size_m > 0),
    source_is_proxy BOOLEAN NOT NULL,
    coverage_confidence_pct NUMERIC(5, 2) CHECK (
        coverage_confidence_pct IS NULL OR coverage_confidence_pct BETWEEN 0 AND 100
    ),
    baseline_method TEXT NOT NULL,
    quality_status TEXT NOT NULL DEFAULT 'unreviewed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (dataset_version_id, cell_geometry)
);

CREATE TABLE IF NOT EXISTS vegetation_observation (
    vegetation_observation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    site_id UUID REFERENCES site(site_id),
    observation_geometry geometry(Geometry, 7855) NOT NULL,
    observed_on DATE NOT NULL,
    vegetation_type TEXT,
    vegetation_percentage NUMERIC(5, 2) CHECK (
        vegetation_percentage IS NULL OR vegetation_percentage BETWEEN 0 AND 100
    ),
    vegetation_index_type TEXT,
    vegetation_index_value NUMERIC,
    calculation_method TEXT,
    spatial_resolution_m NUMERIC CHECK (
        spatial_resolution_m IS NULL OR spatial_resolution_m > 0
    ),
    confidence_score NUMERIC(5, 2) CHECK (
        confidence_score IS NULL OR confidence_score BETWEEN 0 AND 100
    ),
    quality_status TEXT NOT NULL DEFAULT 'unreviewed'
);

CREATE TABLE IF NOT EXISTS canopy_patch (
    canopy_patch_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    site_id UUID REFERENCES site(site_id),
    canopy_geometry geometry(MultiPolygon, 7855) NOT NULL,
    canopy_area_m2 NUMERIC NOT NULL CHECK (canopy_area_m2 > 0),
    observed_on DATE NOT NULL,
    canopy_source_type TEXT NOT NULL,
    confidence_score NUMERIC(5, 2) CHECK (
        confidence_score IS NULL OR confidence_score BETWEEN 0 AND 100
    ),
    quality_status TEXT NOT NULL DEFAULT 'unreviewed'
);

CREATE TABLE IF NOT EXISTS urban_tree (
    tree_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    site_id UUID REFERENCES site(site_id),
    species_id UUID REFERENCES species_profile(species_id),
    source_tree_id TEXT,
    feature_type TEXT,
    feature_subtype TEXT,
    dense_canopy BOOLEAN,
    tree_location geometry(Point, 7855) NOT NULL,
    canopy_radius_m NUMERIC CHECK (canopy_radius_m IS NULL OR canopy_radius_m > 0),
    height_m NUMERIC CHECK (height_m IS NULL OR height_m > 0),
    diameter_cm NUMERIC CHECK (diameter_cm IS NULL OR diameter_cm > 0),
    planting_year INTEGER CHECK (planting_year IS NULL OR planting_year >= 1800),
    health_status TEXT,
    source_observed_from DATE,
    source_observed_to DATE,
    confidence_score NUMERIC(5, 2) CHECK (
        confidence_score IS NULL OR confidence_score BETWEEN 0 AND 100
    ),
    quality_status TEXT NOT NULL DEFAULT 'unreviewed' CHECK (
        quality_status IN ('unreviewed', 'passed', 'failed')
    ),
    UNIQUE (dataset_version_id, source_tree_id)
);

CREATE TABLE IF NOT EXISTS greening_option (
    greening_option_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    option_code TEXT NOT NULL UNIQUE,
    option_name TEXT NOT NULL,
    option_category TEXT NOT NULL,
    cost_unit TEXT NOT NULL,
    description TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS cost_estimate (
    cost_estimate_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    greening_option_id UUID NOT NULL REFERENCES greening_option(greening_option_id),
    analysis_area_id UUID REFERENCES analysis_area(analysis_area_id),
    cost_context TEXT NOT NULL,
    cost_basis TEXT NOT NULL,
    tree_size_category TEXT,
    planting_method TEXT,
    stock_size TEXT,
    minimum_cost NUMERIC(12, 2) NOT NULL CHECK (minimum_cost >= 0),
    maximum_cost NUMERIC(12, 2) NOT NULL CHECK (maximum_cost >= minimum_cost),
    material_min_cost NUMERIC(12, 2) CHECK (material_min_cost IS NULL OR material_min_cost >= 0),
    material_max_cost NUMERIC(12, 2) CHECK (material_max_cost IS NULL OR material_max_cost >= 0),
    installation_min_cost NUMERIC(12, 2) CHECK (installation_min_cost IS NULL OR installation_min_cost >= 0),
    installation_max_cost NUMERIC(12, 2) CHECK (installation_max_cost IS NULL OR installation_max_cost >= 0),
    delivery_min_cost NUMERIC(12, 2) CHECK (delivery_min_cost IS NULL OR delivery_min_cost >= 0),
    delivery_max_cost NUMERIC(12, 2) CHECK (delivery_max_cost IS NULL OR delivery_max_cost >= 0),
    setup_min_cost NUMERIC(12, 2) CHECK (setup_min_cost IS NULL OR setup_min_cost >= 0),
    setup_max_cost NUMERIC(12, 2) CHECK (setup_max_cost IS NULL OR setup_max_cost >= 0),
    currency CHAR(3) NOT NULL DEFAULT 'AUD',
    gst_included BOOLEAN,
    includes_installation BOOLEAN NOT NULL DEFAULT FALSE,
    annual_maintenance_cost NUMERIC(12, 2) CHECK (
        annual_maintenance_cost IS NULL OR annual_maintenance_cost >= 0
    ),
    source_name TEXT NOT NULL,
    source_reference TEXT,
    source_url TEXT,
    valid_from DATE NOT NULL,
    valid_to DATE,
    last_verified_at TIMESTAMPTZ NOT NULL,
    confidence_level TEXT NOT NULL CHECK (
        confidence_level IN ('low', 'medium', 'high')
    ),
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE TABLE IF NOT EXISTS analytical_measure (
    measure_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    measure_code TEXT NOT NULL UNIQUE,
    measure_name TEXT NOT NULL,
    description TEXT NOT NULL,
    formula_text TEXT NOT NULL,
    output_unit TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS model_version (
    model_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name TEXT NOT NULL,
    version_label TEXT NOT NULL,
    method_description TEXT NOT NULL,
    validation_status TEXT NOT NULL DEFAULT 'draft' CHECK (
        validation_status IN (
            'draft', 'prototype_only', 'validation_in_progress',
            'validated', 'retired'
        )
    ),
    validation_completed_at TIMESTAMPTZ,
    validation_summary TEXT,
    output_precision TEXT NOT NULL DEFAULT 'suppressed' CHECK (
        output_precision IN (
            'suppressed', 'indicative_range', 'precise_point_estimate'
        )
    ),
    temperature_metric TEXT CHECK (
        temperature_metric IS NULL OR temperature_metric IN (
            'land_surface_temperature', 'air_temperature',
            'wall_surface_temperature', 'mean_radiant_temperature',
            'thermal_comfort_index'
        )
    ),
    spatial_scope TEXT,
    uncertainty_method TEXT,
    evidence_reviewed_at DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    retired_at TIMESTAMPTZ,
    UNIQUE (model_name, version_label)
);

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

CREATE TABLE IF NOT EXISTS analysis_run (
    analysis_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES site(site_id),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    model_version_id UUID REFERENCES model_version(model_version_id),
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,
    run_status TEXT NOT NULL DEFAULT 'running' CHECK (
        run_status IN ('running', 'completed', 'failed')
    ),
    input_summary JSONB,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS measure_result (
    measure_result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_run_id UUID NOT NULL REFERENCES analysis_run(analysis_run_id),
    measure_id UUID NOT NULL REFERENCES analytical_measure(measure_id),
    baseline_value NUMERIC,
    projected_value NUMERIC,
    result_value NUMERIC,
    minimum_result_value NUMERIC,
    maximum_result_value NUMERIC,
    output_unit TEXT NOT NULL,
    confidence_level TEXT CHECK (confidence_level IN ('low', 'medium', 'high')),
    result_status TEXT NOT NULL DEFAULT 'internal_only' CHECK (
        result_status IN (
            'internal_only', 'indicative_range', 'validated_point_estimate'
        )
    ),
    display_disclaimer TEXT,
    calculation_details JSONB,
    CHECK (
        result_value IS NOT NULL
        OR (
            minimum_result_value IS NOT NULL
            AND maximum_result_value IS NOT NULL
            AND maximum_result_value >= minimum_result_value
        )
    ),
    UNIQUE (analysis_run_id, measure_id)
);

CREATE TABLE IF NOT EXISTS measure_test_case (
    test_case_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    measure_id UUID NOT NULL REFERENCES analytical_measure(measure_id),
    test_case_name TEXT NOT NULL,
    input_values JSONB NOT NULL,
    expected_value NUMERIC NOT NULL,
    tolerance NUMERIC NOT NULL DEFAULT 0 CHECK (tolerance >= 0),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (measure_id, test_case_name)
);

CREATE TABLE IF NOT EXISTS measure_test_result (
    test_result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    test_case_id UUID NOT NULL REFERENCES measure_test_case(test_case_id),
    model_version_id UUID REFERENCES model_version(model_version_id),
    executed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actual_value NUMERIC NOT NULL,
    absolute_difference NUMERIC NOT NULL CHECK (absolute_difference >= 0),
    passed BOOLEAN NOT NULL,
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_dataset_version_source
    ON dataset_version(source_id);
CREATE INDEX IF NOT EXISTS idx_address_source_property
    ON address(source_property_id);
CREATE INDEX IF NOT EXISTS idx_parcel_source_id
    ON parcel(source_parcel_id);
CREATE INDEX IF NOT EXISTS idx_quality_run_version
    ON data_quality_run(dataset_version_id);
CREATE INDEX IF NOT EXISTS idx_quality_result_run
    ON data_quality_result(quality_run_id);
CREATE INDEX IF NOT EXISTS idx_site_analysis_area
    ON site(analysis_area_id);
CREATE INDEX IF NOT EXISTS idx_weather_observed_at
    ON weather_observation(observed_at);
CREATE INDEX IF NOT EXISTS idx_heat_observed_on
    ON heat_observation(observed_on);
CREATE INDEX IF NOT EXISTS idx_vegetation_observed_on
    ON vegetation_observation(observed_on);
CREATE INDEX IF NOT EXISTS idx_cost_estimate_validity
    ON cost_estimate(greening_option_id, valid_from, valid_to);
CREATE UNIQUE INDEX IF NOT EXISTS uq_cost_estimate_source_version
    ON cost_estimate (
        greening_option_id,
        cost_context,
        cost_basis,
        source_name,
        valid_from,
        source_reference
    ) NULLS NOT DISTINCT;

CREATE INDEX IF NOT EXISTS idx_analysis_area_geometry
    ON analysis_area USING GIST(boundary_geometry);
CREATE INDEX IF NOT EXISTS idx_analysis_area_dataset_version
    ON analysis_area(dataset_version_id);
CREATE INDEX IF NOT EXISTS idx_dataset_version_parent
    ON dataset_version(parent_version_id);
CREATE INDEX IF NOT EXISTS idx_dataset_version_analysis_area
    ON dataset_version(analysis_area_id);
CREATE INDEX IF NOT EXISTS idx_analysis_area_tile_area
    ON analysis_area_tile(analysis_area_id);
CREATE INDEX IF NOT EXISTS idx_analysis_area_tile_geometry
    ON analysis_area_tile USING GIST(tile_geometry);
CREATE UNIQUE INDEX IF NOT EXISTS uq_analysis_area_source_version
    ON analysis_area(source_area_code, source_year)
    WHERE source_area_code IS NOT NULL AND source_year IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_address_location
    ON address USING GIST(address_location);
CREATE INDEX IF NOT EXISTS idx_parcel_geometry
    ON parcel USING GIST(parcel_geometry);
CREATE INDEX IF NOT EXISTS idx_site_geometry
    ON site USING GIST(site_geometry);
CREATE INDEX IF NOT EXISTS idx_weather_location
    ON weather_observation USING GIST(observation_location);
CREATE INDEX IF NOT EXISTS idx_heat_geometry
    ON heat_observation USING GIST(observation_geometry);
CREATE INDEX IF NOT EXISTS idx_heat_baseline_version
    ON heat_baseline_cell(dataset_version_id);
CREATE INDEX IF NOT EXISTS idx_heat_baseline_area
    ON heat_baseline_cell(analysis_area_id);
CREATE INDEX IF NOT EXISTS idx_heat_baseline_observed_on
    ON heat_baseline_cell(observed_on);
CREATE INDEX IF NOT EXISTS idx_heat_baseline_geometry
    ON heat_baseline_cell USING GIST(cell_geometry);
CREATE INDEX IF NOT EXISTS idx_canopy_baseline_version
    ON canopy_baseline_cell(dataset_version_id);
CREATE INDEX IF NOT EXISTS idx_canopy_baseline_area
    ON canopy_baseline_cell(analysis_area_id);
CREATE INDEX IF NOT EXISTS idx_canopy_baseline_observed_on
    ON canopy_baseline_cell(observed_on);
CREATE INDEX IF NOT EXISTS idx_canopy_baseline_geometry
    ON canopy_baseline_cell USING GIST(cell_geometry);
CREATE INDEX IF NOT EXISTS idx_vegetation_geometry
    ON vegetation_observation USING GIST(observation_geometry);
CREATE INDEX IF NOT EXISTS idx_canopy_geometry
    ON canopy_patch USING GIST(canopy_geometry);
CREATE INDEX IF NOT EXISTS idx_tree_location
    ON urban_tree USING GIST(tree_location);
CREATE INDEX IF NOT EXISTS idx_tree_dataset_version
    ON urban_tree(dataset_version_id);

CREATE OR REPLACE VIEW latest_dataset_version AS
SELECT DISTINCT ON (source_id)
    dataset_version_id,
    source_id,
    extracted_at,
    source_observed_from,
    source_observed_to,
    quality_pass_rate,
    quality_status,
    integration_status
FROM dataset_version
ORDER BY source_id, extracted_at DESC;

CREATE OR REPLACE VIEW latest_greater_melbourne_heat_baseline AS
SELECT cells.*
FROM heat_baseline_cell AS cells
JOIN dataset_version AS versions USING (dataset_version_id)
JOIN analysis_area AS areas ON areas.analysis_area_id = cells.analysis_area_id
WHERE areas.source_area_code = '2GMEL'
  AND areas.source_year = 2026
  AND versions.integration_status = 'integrated'
  AND versions.publication_status = 'application_ready'
  AND versions.dataset_version_id = (
      SELECT candidate.dataset_version_id
      FROM dataset_version AS candidate
      WHERE candidate.analysis_area_id = versions.analysis_area_id
        AND candidate.derivation_method = 'landsat_latest_daily_mosaic_v1'
        AND candidate.integration_status = 'integrated'
        AND candidate.publication_status = 'application_ready'
      ORDER BY candidate.extracted_at DESC
      LIMIT 1
  );

CREATE OR REPLACE VIEW latest_greater_melbourne_canopy_baseline AS
SELECT cells.*
FROM canopy_baseline_cell AS cells
JOIN dataset_version AS versions USING (dataset_version_id)
JOIN analysis_area AS areas ON areas.analysis_area_id = cells.analysis_area_id
WHERE areas.source_area_code = '2GMEL'
  AND areas.source_year = 2026
  AND versions.integration_status = 'integrated'
  AND versions.publication_status = 'application_ready'
  AND versions.dataset_version_id = (
      SELECT candidate.dataset_version_id
      FROM dataset_version AS candidate
      WHERE candidate.analysis_area_id = versions.analysis_area_id
        AND candidate.derivation_method = 'vicmap_canopy_baseline_500m_v1'
        AND candidate.integration_status = 'integrated'
        AND candidate.publication_status = 'application_ready'
      ORDER BY candidate.extracted_at DESC
      LIMIT 1
  );

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

CREATE OR REPLACE FUNCTION classify_residential_lot_size(p_area_m2 NUMERIC)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
RETURN CASE
    WHEN p_area_m2 IS NULL OR p_area_m2 <= 0 THEN 'unknown'
    WHEN p_area_m2 < 400 THEN 'small'
    WHEN p_area_m2 <= 800 THEN 'medium'
    ELSE 'large'
END;

COMMENT ON FUNCTION classify_residential_lot_size(NUMERIC) IS
    'Project-defined prototype categories: small <400 m2, medium 400-800 m2, large >800 m2. Not a statutory classification.';

CREATE TABLE IF NOT EXISTS environmental_classification_scheme (
    classification_scheme_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_label TEXT NOT NULL UNIQUE,
    analysis_area_id UUID NOT NULL REFERENCES analysis_area(analysis_area_id),
    method TEXT NOT NULL CHECK (method = 'tercile_percentile_cont'),
    classification_scope TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'active', 'retired')),
    calculated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS environmental_classification_one_active_area
    ON environmental_classification_scheme(analysis_area_id)
    WHERE status = 'active';

CREATE TABLE IF NOT EXISTS environmental_classification_threshold (
    classification_threshold_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    classification_scheme_id UUID NOT NULL
        REFERENCES environmental_classification_scheme(classification_scheme_id)
        ON DELETE CASCADE,
    metric_code TEXT NOT NULL CHECK (metric_code IN ('heat', 'canopy')),
    source_dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    lower_threshold NUMERIC NOT NULL,
    upper_threshold NUMERIC NOT NULL,
    unit TEXT NOT NULL,
    sample_count BIGINT NOT NULL CHECK (sample_count > 0),
    low_label TEXT NOT NULL DEFAULT 'Low',
    medium_label TEXT NOT NULL DEFAULT 'Medium',
    high_label TEXT NOT NULL DEFAULT 'High',
    missing_label TEXT NOT NULL DEFAULT 'Unavailable',
    explanation TEXT NOT NULL,
    CHECK (lower_threshold <= upper_threshold),
    UNIQUE (classification_scheme_id, metric_code)
);

CREATE OR REPLACE VIEW current_environmental_classification_threshold AS
SELECT
    scheme.classification_scheme_id,
    scheme.version_label,
    scheme.analysis_area_id,
    CASE WHEN threshold.metric_code = 'heat'
         THEN 'fixed_temperature_display_bands'
         ELSE scheme.method END AS method,
    CASE WHEN threshold.metric_code = 'heat'
         THEN 'application_defined_temperature_display_band'
         ELSE scheme.classification_scope END AS classification_scope,
    scheme.calculated_at,
    threshold.metric_code,
    threshold.source_dataset_version_id,
    CASE WHEN threshold.metric_code = 'heat' THEN 27.0
         ELSE threshold.lower_threshold END AS lower_threshold,
    CASE WHEN threshold.metric_code = 'heat' THEN 30.0
         ELSE threshold.upper_threshold END AS upper_threshold,
    threshold.unit,
    threshold.sample_count,
    threshold.low_label,
    threshold.medium_label,
    threshold.high_label,
    threshold.missing_label,
    CASE WHEN threshold.metric_code = 'heat' THEN
        'GreenChanger display bands: Low <=27 C, Medium >27 C and <=30 C, High >30 C. Application-defined only; not a BOM heatwave, health-risk or comfort classification.'
    ELSE threshold.explanation END AS explanation
FROM environmental_classification_scheme AS scheme
JOIN environmental_classification_threshold AS threshold
  USING (classification_scheme_id)
WHERE scheme.status = 'active';

CREATE OR REPLACE FUNCTION refresh_environmental_classifications(p_version_label TEXT)
RETURNS UUID
LANGUAGE plpgsql
AS $function$
DECLARE
    v_scheme_id UUID;
    v_analysis_area_id UUID;
    v_threshold_count INTEGER;
BEGIN
    IF p_version_label IS NULL OR BTRIM(p_version_label) = '' THEN
        RAISE EXCEPTION 'classification version label is required';
    END IF;
    IF EXISTS (
        SELECT 1 FROM environmental_classification_scheme
        WHERE version_label = BTRIM(p_version_label)
    ) THEN
        RAISE EXCEPTION 'classification version % already exists', BTRIM(p_version_label);
    END IF;

    SELECT analysis_area_id INTO STRICT v_analysis_area_id
    FROM analysis_area
    WHERE source_area_code = '2GMEL' AND source_year = 2026;

    INSERT INTO environmental_classification_scheme (
        version_label, analysis_area_id, method, classification_scope, status, notes
    ) VALUES (
        BTRIM(p_version_label), v_analysis_area_id, 'tercile_percentile_cont',
        'relative_to_greater_melbourne_application_ready_baseline', 'draft',
        'Low is the bottom third, Medium the middle third and High the top third. Missing values are Unavailable.'
    ) RETURNING classification_scheme_id INTO v_scheme_id;

    INSERT INTO environmental_classification_threshold (
        classification_scheme_id, metric_code, source_dataset_version_id,
        lower_threshold, upper_threshold, unit, sample_count, explanation
    )
    SELECT v_scheme_id, 'heat', dataset_version_id,
           PERCENTILE_CONT(1.0 / 3.0) WITHIN GROUP (ORDER BY baseline_surface_temperature_c)::NUMERIC,
           PERCENTILE_CONT(2.0 / 3.0) WITHIN GROUP (ORDER BY baseline_surface_temperature_c)::NUMERIC,
           'degC_land_surface_temperature', COUNT(*),
           'Relative to application-ready Melbourne Landsat 500 m baseline cells; land-surface temperature, not air temperature.'
    FROM latest_greater_melbourne_heat_baseline
    WHERE baseline_surface_temperature_c IS NOT NULL
    GROUP BY dataset_version_id;

    INSERT INTO environmental_classification_threshold (
        classification_scheme_id, metric_code, source_dataset_version_id,
        lower_threshold, upper_threshold, unit, sample_count, explanation
    )
    SELECT v_scheme_id, 'canopy', dataset_version_id,
           PERCENTILE_CONT(1.0 / 3.0) WITHIN GROUP (ORDER BY canopy_percentage)::NUMERIC,
           PERCENTILE_CONT(2.0 / 3.0) WITHIN GROUP (ORDER BY canopy_percentage)::NUMERIC,
           'percent_neighbourhood_canopy', COUNT(*),
           'Relative to application-ready Melbourne 500 m neighbourhood canopy cells; current source is a proxy.'
    FROM latest_greater_melbourne_canopy_baseline
    WHERE canopy_percentage IS NOT NULL
    GROUP BY dataset_version_id;

    SELECT COUNT(*) INTO v_threshold_count
    FROM environmental_classification_threshold
    WHERE classification_scheme_id = v_scheme_id;
    IF v_threshold_count <> 2 THEN
        RAISE EXCEPTION 'expected heat and canopy thresholds but calculated % row(s)', v_threshold_count;
    END IF;

    UPDATE environmental_classification_scheme
    SET status = 'retired'
    WHERE analysis_area_id = v_analysis_area_id AND status = 'active';
    UPDATE environmental_classification_scheme
    SET status = 'active', calculated_at = CURRENT_TIMESTAMP
    WHERE classification_scheme_id = v_scheme_id;
    RETURN v_scheme_id;
END;
$function$;

CREATE OR REPLACE FUNCTION classify_temperature_band(p_temperature_c NUMERIC)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
RETURN CASE
    WHEN p_temperature_c IS NULL
      OR p_temperature_c::TEXT IN ('NaN', 'Infinity', '-Infinity')
        THEN 'Unavailable'
    WHEN p_temperature_c <= 27.0 THEN 'Low'
    WHEN p_temperature_c <= 30.0 THEN 'Medium'
    ELSE 'High'
END;

COMMENT ON FUNCTION classify_temperature_band(NUMERIC) IS
    'GreenChanger product display bands: Low <=27 C, Medium >27 C and <=30 C, High >30 C. These are application-defined display bands, not BOM heatwave, health-risk or comfort classifications.';

CREATE OR REPLACE FUNCTION classify_environmental_value(
    p_metric_code TEXT, p_value NUMERIC, p_version_label TEXT DEFAULT NULL
)
RETURNS TEXT
LANGUAGE SQL
STABLE
PARALLEL SAFE
RETURN CASE
    WHEN p_value IS NULL OR p_value::TEXT IN ('NaN', 'Infinity', '-Infinity')
        THEN 'Unavailable'
    WHEN p_metric_code = 'heat' THEN classify_temperature_band(p_value)
    ELSE COALESCE((
        SELECT CASE
            WHEN p_value <= threshold.lower_threshold THEN threshold.low_label
            WHEN p_value <= threshold.upper_threshold THEN threshold.medium_label
            ELSE threshold.high_label
        END
        FROM current_environmental_classification_threshold AS threshold
        WHERE threshold.metric_code = p_metric_code
          AND (p_version_label IS NULL OR threshold.version_label = p_version_label)
        LIMIT 1
    ), 'Unavailable')
END;

COMMENT ON FUNCTION classify_environmental_value(TEXT, NUMERIC, TEXT) IS
    'Uses fixed GreenChanger 27/30 C display bands for heat and the active versioned Melbourne threshold scheme for canopy. Missing and non-finite values return Unavailable.';

CREATE OR REPLACE VIEW latest_greater_melbourne_address_property AS
WITH latest_address_version AS (
    SELECT dv.dataset_version_id
    FROM dataset_version AS dv
    JOIN dataset_source AS ds USING (source_id)
    JOIN analysis_area AS aa USING (analysis_area_id)
    WHERE ds.source_name = 'Vicmap Address'
      AND aa.source_area_code = '2GMEL'
      AND aa.source_year = 2026
      AND dv.integration_status = 'integrated'
      AND dv.publication_status = 'application_ready'
      AND dv.derivation_method LIKE 'clip_to_abs_gccsa_2GMEL_2026_v1:%'
    ORDER BY dv.extracted_at DESC
    LIMIT 1
), latest_property_version AS (
    SELECT dv.dataset_version_id
    FROM dataset_version AS dv
    JOIN dataset_source AS ds USING (source_id)
    JOIN analysis_area AS aa USING (analysis_area_id)
    WHERE ds.source_name = 'Vicmap Property'
      AND aa.source_area_code = '2GMEL'
      AND aa.source_year = 2026
      AND dv.integration_status = 'integrated'
      AND dv.publication_status = 'application_ready'
      AND dv.derivation_method LIKE 'clip_to_abs_gccsa_2GMEL_2026_v1:%'
    ORDER BY dv.extracted_at DESC
    LIMIT 1
)
SELECT
    a.address_id,
    a.dataset_version_id AS address_dataset_version_id,
    a.source_address_id,
    a.source_property_id,
    a.full_address,
    a.locality_name,
    a.postcode,
    a.lga_code,
    a.is_primary,
    a.address_class,
    a.address_location,
    p.parcel_id,
    p.dataset_version_id AS property_dataset_version_id,
    p.source_parcel_id,
    p.property_number,
    p.property_type,
    p.property_status,
    p.parcel_geometry,
    COALESCE(p.parcel_area_m2, ST_Area(p.parcel_geometry)) AS parcel_area_m2,
    classify_residential_lot_size(
        COALESCE(p.parcel_area_m2, ST_Area(p.parcel_geometry))::NUMERIC
    ) AS lot_size_category,
    COALESCE(ST_PointOnSurface(p.parcel_geometry), a.address_location) AS reference_point
FROM address AS a
CROSS JOIN latest_address_version AS av
CROSS JOIN latest_property_version AS pv
LEFT JOIN parcel AS p
  ON p.dataset_version_id = pv.dataset_version_id
 AND p.source_parcel_id = a.source_property_id
WHERE a.dataset_version_id = av.dataset_version_id;

CREATE OR REPLACE FUNCTION get_property_baseline(
    p_address_search TEXT,
    p_result_limit INTEGER DEFAULT 10
)
RETURNS TABLE (
    address_id UUID,
    parcel_id UUID,
    full_address TEXT,
    locality_name TEXT,
    postcode TEXT,
    source_property_id TEXT,
    parcel_area_m2 NUMERIC,
    lot_size_category TEXT,
    property_type TEXT,
    property_status TEXT,
    longitude NUMERIC,
    latitude NUMERIC,
    parcel_geometry_geojson JSONB,
    land_surface_temperature_c NUMERIC,
    surface_temperature_observed_on DATE,
    temperature_measurement_type TEXT,
    heat_baseline_method TEXT,
    heat_cell_geojson JSONB,
    current_air_temperature_c NUMERIC,
    current_apparent_temperature_c NUMERIC,
    weather_station_name TEXT,
    weather_observed_at TIMESTAMPTZ,
    weather_station_distance_km NUMERIC,
    air_temperature_context_status TEXT,
    neighbourhood_canopy_percentage NUMERIC,
    property_canopy_percentage NUMERIC,
    canopy_analysis_scope TEXT,
    canopy_observed_on DATE,
    canopy_source_type TEXT,
    canopy_source_is_proxy BOOLEAN,
    canopy_cell_geojson JSONB,
    mapped_property_tree_count BIGINT,
    property_tree_data_status TEXT,
    data_quality_status TEXT,
    limitations JSONB,
    heat_classification TEXT,
    canopy_classification TEXT,
    classification_scheme_version TEXT,
    classification_scope TEXT
)
LANGUAGE SQL
STABLE
PARALLEL SAFE
AS $function$
WITH latest_tree_version AS (
    SELECT dv.dataset_version_id, dv.source_observed_to
    FROM dataset_version AS dv
    JOIN dataset_source AS ds USING (source_id)
    JOIN analysis_area AS aa USING (analysis_area_id)
    WHERE ds.source_name = 'Vicmap Vegetation - Tree Urban Point'
      AND aa.source_area_code = '2GMEL'
      AND aa.source_year = 2026
      AND dv.integration_status = 'integrated'
      AND dv.publication_status = 'application_ready'
    ORDER BY dv.extracted_at DESC
    LIMIT 1
), candidates AS (
    SELECT property.*
    FROM latest_greater_melbourne_address_property AS property
    WHERE p_address_search IS NOT NULL
      AND BTRIM(p_address_search) <> ''
      AND UPPER(property.full_address) LIKE UPPER(BTRIM(p_address_search)) || '%'
    ORDER BY
        CASE WHEN UPPER(property.full_address) = UPPER(BTRIM(p_address_search)) THEN 0 ELSE 1 END,
        CASE WHEN property.is_primary = 'Y' THEN 0 ELSE 1 END,
        property.full_address,
        property.source_address_id
    LIMIT LEAST(GREATEST(COALESCE(p_result_limit, 10), 1), 50)
)
SELECT
    candidate.address_id,
    candidate.parcel_id,
    candidate.full_address,
    candidate.locality_name,
    candidate.postcode,
    candidate.source_property_id,
    candidate.parcel_area_m2,
    candidate.lot_size_category,
    candidate.property_type,
    candidate.property_status,
    ST_X(ST_Transform(candidate.address_location, 4326))::NUMERIC AS longitude,
    ST_Y(ST_Transform(candidate.address_location, 4326))::NUMERIC AS latitude,
    CASE WHEN candidate.parcel_geometry IS NULL THEN NULL
         ELSE ST_AsGeoJSON(ST_Transform(candidate.parcel_geometry, 4326), 6)::JSONB
    END AS parcel_geometry_geojson,
    heat.baseline_surface_temperature_c AS land_surface_temperature_c,
    heat.observed_on AS surface_temperature_observed_on,
    CASE WHEN heat.heat_baseline_cell_id IS NOT NULL
         THEN 'land_surface_temperature' END AS temperature_measurement_type,
    heat.baseline_method AS heat_baseline_method,
    CASE WHEN heat.cell_geometry IS NULL THEN NULL
         ELSE ST_AsGeoJSON(ST_Transform(heat.cell_geometry, 4326), 6)::JSONB
    END AS heat_cell_geojson,
    CASE WHEN weather.distance_m <= 25000
         THEN weather.air_temperature_c END AS current_air_temperature_c,
    CASE WHEN weather.distance_m <= 25000
         THEN weather.apparent_temperature_c END AS current_apparent_temperature_c,
    weather.station_name AS weather_station_name,
    weather.observed_at AS weather_observed_at,
    weather.distance_m / 1000.0 AS weather_station_distance_km,
    CASE
        WHEN weather.weather_observation_id IS NULL
            THEN 'unavailable_no_observation_within_3_hours'
        WHEN weather.distance_m <= 10000 THEN 'good_local_context'
        WHEN weather.distance_m <= 25000 THEN 'regional_context_warning'
        ELSE 'too_distant_temperature_suppressed'
    END AS air_temperature_context_status,
    canopy.canopy_percentage AS neighbourhood_canopy_percentage,
    NULL::NUMERIC AS property_canopy_percentage,
    CASE WHEN canopy.canopy_baseline_cell_id IS NOT NULL
         THEN 'neighbourhood_500m' END AS canopy_analysis_scope,
    canopy.observed_on AS canopy_observed_on,
    canopy.source_type AS canopy_source_type,
    canopy.source_is_proxy AS canopy_source_is_proxy,
    CASE WHEN canopy.cell_geometry IS NULL THEN NULL
         ELSE ST_AsGeoJSON(ST_Transform(canopy.cell_geometry, 4326), 6)::JSONB
    END AS canopy_cell_geojson,
    property_trees.tree_count AS mapped_property_tree_count,
    CASE
        WHEN candidate.parcel_id IS NULL THEN 'unavailable_missing_property'
        WHEN property_trees.tree_dataset_version_id IS NULL
            THEN 'not_loaded_neighbourhood_canopy_only'
        ELSE 'mapped_tree_points_available'
    END AS property_tree_data_status,
    CASE
        WHEN candidate.parcel_id IS NULL THEN 'partial_missing_property'
        WHEN heat.heat_baseline_cell_id IS NULL AND canopy.canopy_baseline_cell_id IS NULL
            THEN 'partial_missing_environmental_baselines'
        WHEN heat.heat_baseline_cell_id IS NULL THEN 'partial_missing_heat'
        WHEN canopy.canopy_baseline_cell_id IS NULL THEN 'partial_missing_canopy'
        ELSE 'passed'
    END AS data_quality_status,
    JSONB_STRIP_NULLS(JSONB_BUILD_OBJECT(
        'lot_size_category', 'Project-defined; not a statutory property classification.',
        'heat', CASE WHEN heat.heat_baseline_cell_id IS NOT NULL
                     THEN 'Landsat land-surface temperature, not residential air temperature.' END,
        'air_temperature', CASE
            WHEN weather.weather_observation_id IS NULL
                THEN 'No integrated BOM station observation is available within the three-hour freshness window.'
            WHEN weather.distance_m <= 10000
                THEN 'Nearest BOM observation within 10 km; local station context, not a property-level estimate.'
            WHEN weather.distance_m <= 25000
                THEN 'Nearest BOM observation is 10-25 km away; regional context only, not a property-level estimate.'
            ELSE 'Nearest recent BOM station is more than 25 km away; air and apparent temperatures are suppressed.'
        END,
        'canopy', CASE WHEN canopy.source_is_proxy
                       THEN 'Neighbourhood-only rendered API proxy; property canopy percentage is deliberately suppressed.' END,
        'property_trees', CASE WHEN property_trees.tree_dataset_version_id IS NULL
                       THEN 'Load Vicmap Tree Urban Point before showing mapped individual-tree context.'
                       ELSE 'Machine-derived mapped points from the 2019-2020 mapping program; not a current field inventory or proof of tree condition.' END,
        'canopy_source_period', CASE WHEN canopy.canopy_baseline_cell_id IS NOT NULL
                                     THEN 'Source imagery varies by location from 2013-12-07 to 2020-11-02.' END
    )) AS limitations,
    classify_environmental_value(
        'heat', heat.baseline_surface_temperature_c
    ) AS heat_classification,
    classify_environmental_value(
        'canopy', canopy.canopy_percentage
    ) AS canopy_classification,
    (
        SELECT version_label
        FROM current_environmental_classification_threshold
        LIMIT 1
    ) AS classification_scheme_version,
    (
        SELECT classification_scope
        FROM current_environmental_classification_threshold
        LIMIT 1
    ) AS classification_scope
FROM candidates AS candidate
LEFT JOIN LATERAL (
    SELECT cell.*
    FROM latest_greater_melbourne_heat_baseline AS cell
    WHERE cell.cell_geometry && candidate.reference_point
      AND ST_Covers(cell.cell_geometry, candidate.reference_point)
    ORDER BY cell.observed_on DESC, cell.heat_baseline_cell_id
    LIMIT 1
) AS heat ON TRUE
LEFT JOIN LATERAL (
    SELECT cell.*
    FROM latest_greater_melbourne_canopy_baseline AS cell
    WHERE cell.cell_geometry && candidate.reference_point
      AND ST_Covers(cell.cell_geometry, candidate.reference_point)
    ORDER BY cell.observed_on DESC, cell.canopy_baseline_cell_id
    LIMIT 1
) AS canopy ON TRUE
LEFT JOIN LATERAL (
    SELECT observation.*,
           ST_Distance(observation.observation_location, candidate.reference_point) AS distance_m
    FROM (
        SELECT DISTINCT ON (weather.station_code)
               weather.*
        FROM weather_observation AS weather
        JOIN dataset_version AS version USING (dataset_version_id)
        WHERE version.integration_status = 'integrated'
          AND version.publication_status = 'application_ready'
          AND weather.observation_location IS NOT NULL
          AND weather.observed_at >= CURRENT_TIMESTAMP - INTERVAL '3 hours'
          AND weather.observed_at <= CURRENT_TIMESTAMP + INTERVAL '5 minutes'
        ORDER BY
            weather.station_code,
            weather.observed_at DESC,
            version.extracted_at DESC
    ) AS observation
    ORDER BY observation.observation_location <-> candidate.reference_point
    LIMIT 1
) AS weather ON TRUE
LEFT JOIN LATERAL (
    SELECT tree_version.dataset_version_id AS tree_dataset_version_id,
           tree_version.source_observed_to,
           COUNT(tree.tree_id)::BIGINT AS tree_count
    FROM latest_tree_version AS tree_version
    LEFT JOIN urban_tree AS tree
      ON tree.dataset_version_id = tree_version.dataset_version_id
     AND candidate.parcel_geometry IS NOT NULL
     AND tree.tree_location && candidate.parcel_geometry
     AND ST_Covers(candidate.parcel_geometry, tree.tree_location)
    GROUP BY tree_version.dataset_version_id, tree_version.source_observed_to
) AS property_trees ON TRUE;
$function$;

COMMENT ON FUNCTION get_property_baseline(TEXT, INTEGER) IS
    'Returns nearest application-ready BOM station context no older than three hours; air temperature is suppressed beyond 25 km and remains separate from Landsat land-surface temperature.';

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

CREATE OR REPLACE FUNCTION get_environment_context(
    p_longitude DOUBLE PRECISION,
    p_latitude DOUBLE PRECISION,
    p_radius_m DOUBLE PRECISION DEFAULT 500.0,
    p_layers TEXT[] DEFAULT ARRAY['trees', 'heat']::TEXT[],
    p_result_limit INTEGER DEFAULT 1000
)
RETURNS TABLE (
    layer TEXT,
    feature_id TEXT,
    dataset_version_id UUID,
    distance_m NUMERIC,
    observed_on DATE,
    properties JSONB,
    geometry_geojson JSONB
)
LANGUAGE plpgsql
STABLE
PARALLEL SAFE
AS $function$
DECLARE
    v_point geometry(Point, 7855);
    v_search_area geometry(Polygon, 7855);
    v_layers TEXT[];
    v_invalid_layers TEXT;
BEGIN
    IF p_longitude IS NULL
       OR p_longitude::TEXT IN ('NaN', 'Infinity', '-Infinity')
       OR p_longitude < -180 OR p_longitude > 180 THEN
        RAISE EXCEPTION 'longitude must be a finite number between -180 and 180';
    END IF;
    IF p_latitude IS NULL
       OR p_latitude::TEXT IN ('NaN', 'Infinity', '-Infinity')
       OR p_latitude < -90 OR p_latitude > 90 THEN
        RAISE EXCEPTION 'latitude must be a finite number between -90 and 90';
    END IF;
    IF p_radius_m IS NULL
       OR p_radius_m::TEXT IN ('NaN', 'Infinity', '-Infinity')
       OR p_radius_m <= 0 OR p_radius_m > 2000 THEN
        RAISE EXCEPTION 'radius_m must be greater than 0 and no more than 2000 metres';
    END IF;
    IF p_result_limit IS NULL OR p_result_limit < 1 OR p_result_limit > 2000 THEN
        RAISE EXCEPTION 'result_limit must be between 1 and 2000 per layer';
    END IF;

    SELECT COALESCE(
        ARRAY_AGG(DISTINCT LOWER(BTRIM(requested_layer))),
        ARRAY[]::TEXT[]
    )
    INTO v_layers
    FROM UNNEST(COALESCE(p_layers, ARRAY[]::TEXT[])) AS requested(requested_layer)
    WHERE requested_layer IS NOT NULL
      AND BTRIM(requested_layer) <> '';

    IF CARDINALITY(v_layers) = 0 THEN
        RAISE EXCEPTION 'at least one layer is required: trees or heat';
    END IF;

    SELECT STRING_AGG(requested_layer, ', ' ORDER BY requested_layer)
    INTO v_invalid_layers
    FROM UNNEST(v_layers) AS requested(requested_layer)
    WHERE NOT (requested_layer = ANY (ARRAY['trees', 'heat']::TEXT[]));

    IF v_invalid_layers IS NOT NULL THEN
        RAISE EXCEPTION 'unsupported layer(s): %. Allowed layers are trees and heat',
            v_invalid_layers;
    END IF;

    v_point := ST_Transform(
        ST_SetSRID(ST_MakePoint(p_longitude, p_latitude), 4326),
        7855
    );
    v_search_area := ST_Buffer(v_point, p_radius_m);

    IF NOT EXISTS (
        SELECT 1
        FROM analysis_area AS area
        WHERE area.source_area_code = '2GMEL'
          AND area.source_year = 2026
          AND area.boundary_geometry && v_point
          AND ST_Covers(area.boundary_geometry, v_point)
    ) THEN
        RAISE EXCEPTION 'selected coordinate is outside the supported Melbourne boundary';
    END IF;

    RETURN QUERY
    WITH latest_tree_version AS (
        SELECT version.dataset_version_id
        FROM dataset_version AS version
        JOIN dataset_source AS source USING (source_id)
        JOIN analysis_area AS area USING (analysis_area_id)
        WHERE source.source_name = 'Vicmap Vegetation - Tree Urban Point'
          AND area.source_area_code = '2GMEL'
          AND area.source_year = 2026
          AND version.integration_status = 'integrated'
          AND version.publication_status = 'application_ready'
        ORDER BY version.extracted_at DESC, version.dataset_version_id
        LIMIT 1
    ), nearby_trees AS (
        SELECT
            'trees'::TEXT AS result_layer,
            tree.tree_id::TEXT AS result_feature_id,
            tree.dataset_version_id AS result_dataset_version_id,
            ST_Distance(tree.tree_location, v_point) AS result_distance_m,
            tree.source_observed_to AS result_observed_on,
            JSONB_STRIP_NULLS(JSONB_BUILD_OBJECT(
                'source_tree_id', tree.source_tree_id,
                'feature_type', tree.feature_type,
                'feature_subtype', tree.feature_subtype,
                'canopy_radius_m', tree.canopy_radius_m,
                'height_m', tree.height_m,
                'dense_canopy', tree.dense_canopy,
                'source_observed_from', tree.source_observed_from,
                'source_observed_to', tree.source_observed_to,
                'quality_status', tree.quality_status,
                'data_scope', 'machine_derived_mapped_tree_point_not_field_inventory'
            )) AS result_properties,
            ST_AsGeoJSON(ST_Transform(tree.tree_location, 4326), 6)::JSONB
                AS result_geometry
        FROM urban_tree AS tree
        JOIN latest_tree_version AS version USING (dataset_version_id)
        WHERE 'trees' = ANY (v_layers)
          AND tree.quality_status = 'passed'
          AND ST_DWithin(tree.tree_location, v_point, p_radius_m)
        ORDER BY tree.tree_location <-> v_point, tree.tree_id
        LIMIT p_result_limit
    ), nearby_heat AS (
        SELECT
            'heat'::TEXT AS result_layer,
            heat.heat_baseline_cell_id::TEXT AS result_feature_id,
            heat.dataset_version_id AS result_dataset_version_id,
            ST_Distance(heat.cell_geometry, v_point) AS result_distance_m,
            heat.observed_on AS result_observed_on,
            JSONB_STRIP_NULLS(JSONB_BUILD_OBJECT(
                'land_surface_temperature_c', heat.baseline_surface_temperature_c,
                'heat_classification', classify_environmental_value(
                    'heat', heat.baseline_surface_temperature_c
                ),
                'measurement_type', 'land_surface_temperature',
                'unit', 'degC',
                'observation_count', heat.observation_count,
                'scene_count', heat.scene_count,
                'mean_cloud_cover_pct', heat.mean_cloud_cover_pct,
                'baseline_method', heat.baseline_method,
                'quality_status', heat.quality_status,
                'grid_scope', '500m_baseline_cell',
                'limitation', 'Landsat land-surface temperature, not air temperature.'
            )) AS result_properties,
            ST_AsGeoJSON(
                ST_Transform(ST_Intersection(heat.cell_geometry, v_search_area), 4326),
                6
            )::JSONB AS result_geometry
        FROM latest_greater_melbourne_heat_baseline AS heat
        WHERE 'heat' = ANY (v_layers)
          AND heat.quality_status = 'passed'
          AND ST_DWithin(heat.cell_geometry, v_point, p_radius_m)
        ORDER BY heat.cell_geometry <-> v_point, heat.heat_baseline_cell_id
        LIMIT p_result_limit
    )
    SELECT
        result.layer,
        result.feature_id,
        result.dataset_version_id,
        ROUND(result.distance_m::NUMERIC, 2),
        result.observed_on,
        result.properties,
        result.geometry_geojson
    FROM (
        SELECT
            result_layer AS layer,
            result_feature_id AS feature_id,
            result_dataset_version_id AS dataset_version_id,
            result_distance_m AS distance_m,
            result_observed_on AS observed_on,
            result_properties AS properties,
            result_geometry AS geometry_geojson
        FROM nearby_trees
        UNION ALL
        SELECT
            result_layer,
            result_feature_id,
            result_dataset_version_id,
            result_distance_m,
            result_observed_on,
            result_properties,
            result_geometry
        FROM nearby_heat
    ) AS result
    ORDER BY result.layer, result.distance_m, result.feature_id;
END;
$function$;

COMMENT ON FUNCTION get_environment_context(
    DOUBLE PRECISION, DOUBLE PRECISION, DOUBLE PRECISION, TEXT[], INTEGER
) IS
    'Returns application-ready mapped-tree points and clipped 500 m Landsat heat cells within a validated Melbourne radius. The result limit applies separately to each requested layer.';

CREATE OR REPLACE FUNCTION get_environment_context_by_address(
    p_address_search TEXT,
    p_radius_m DOUBLE PRECISION DEFAULT 500.0,
    p_layers TEXT[] DEFAULT ARRAY['trees', 'heat']::TEXT[],
    p_result_limit INTEGER DEFAULT 1000
)
RETURNS TABLE (
    layer TEXT,
    feature_id TEXT,
    dataset_version_id UUID,
    distance_m NUMERIC,
    observed_on DATE,
    properties JSONB,
    geometry_geojson JSONB
)
LANGUAGE plpgsql
STABLE
PARALLEL SAFE
AS $function$
DECLARE
    v_matched_address TEXT;
    v_longitude DOUBLE PRECISION;
    v_latitude DOUBLE PRECISION;
    v_match_count INTEGER;
    v_exact_match_count INTEGER;
BEGIN
    IF p_address_search IS NULL OR BTRIM(p_address_search) = '' THEN
        RAISE EXCEPTION 'address search is required';
    END IF;

    WITH matches AS MATERIALIZED (
        SELECT baseline.*,
               UPPER(BTRIM(baseline.full_address)) =
                   UPPER(BTRIM(p_address_search)) AS is_exact
        FROM get_property_baseline(p_address_search, 2) AS baseline
    ), ranked AS (
        SELECT
            matches.*,
            COUNT(*) OVER ()::INTEGER AS match_count,
            COUNT(*) FILTER (WHERE is_exact) OVER ()::INTEGER
                AS exact_match_count,
            ROW_NUMBER() OVER (
                ORDER BY
                    CASE WHEN is_exact THEN 0 ELSE 1 END,
                    full_address,
                    address_id
            ) AS match_rank
        FROM matches
    )
    SELECT
        ranked.full_address,
        ranked.longitude::DOUBLE PRECISION,
        ranked.latitude::DOUBLE PRECISION,
        ranked.match_count,
        ranked.exact_match_count
    INTO
        v_matched_address,
        v_longitude,
        v_latitude,
        v_match_count,
        v_exact_match_count
    FROM ranked
    WHERE match_rank = 1;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'no Melbourne address matched: %', BTRIM(p_address_search);
    END IF;

    IF v_exact_match_count > 1
       OR (v_exact_match_count = 0 AND v_match_count > 1) THEN
        RAISE EXCEPTION
            'address search is ambiguous: %. Supply the complete address and postcode',
            BTRIM(p_address_search);
    END IF;

    IF v_longitude IS NULL OR v_latitude IS NULL THEN
        RAISE EXCEPTION 'matched address has no usable coordinate: %', v_matched_address;
    END IF;

    RETURN QUERY
    SELECT context.*
    FROM get_environment_context(
        v_longitude,
        v_latitude,
        p_radius_m,
        p_layers,
        p_result_limit
    ) AS context;
END;
$function$;

COMMENT ON FUNCTION get_environment_context_by_address(
    TEXT, DOUBLE PRECISION, TEXT[], INTEGER
) IS
    'Resolves one unambiguous Melbourne property address and returns the application-ready mapped-tree and Landsat heat context within the requested radius.';

CREATE TABLE environmental_classification_reference (
    classification_reference_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    metric_code TEXT NOT NULL CHECK (
        metric_code IN ('daily_mean_air_temperature', 'canopy_progress')
    ),
    threshold_code TEXT NOT NULL,
    threshold_value NUMERIC NOT NULL,
    unit TEXT NOT NULL,
    classification_label TEXT NOT NULL CHECK (
        classification_label IN ('Medium', 'High')
    ),
    source_title TEXT NOT NULL,
    source_publisher TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_locator TEXT NOT NULL,
    evidence_scope TEXT NOT NULL,
    limitation TEXT NOT NULL,
    reviewed_on DATE NOT NULL,
    UNIQUE (metric_code, threshold_code, source_url)
);

INSERT INTO environmental_classification_reference (
    metric_code, threshold_code, threshold_value, unit,
    classification_label, source_title, source_publisher, source_url,
    source_locator, evidence_scope, limitation, reviewed_on
) VALUES
(
    'daily_mean_air_temperature', 'elevated_daily_mean', 27.2, 'degC',
    'Medium',
    'The impact of heatwaves on mortality in Australia: a multicity study',
    'BMJ Open',
    'https://pmc.ncbi.nlm.nih.gov/articles/PMC3931989/',
    'Table 2: Heatwave days and threshold',
    'Melbourne 95th-percentile summer daily-mean threshold.',
    'The study definition requires two or more consecutive summer days; this is not an instantaneous reading.',
    DATE '2026-09-01'
),
(
    'daily_mean_air_temperature', 'historical_central_heat_health', 30.0, 'degC',
    'High',
    'Planning for extreme heat and heatwaves',
    'Victorian Department of Health',
    'https://www.health.vic.gov.au/environmental-health/planning-for-extreme-heat-and-heatwaves',
    'Weather forecast districts; Calculating the average temperature; Figure 1',
    'Historical Central District threshold calculated from forecast maximum and following overnight minimum.',
    'The page states this Victorian system ended in 2021-22 and is not comparable with the current BOM national warning trigger.',
    DATE '2026-09-01'
),
(
    'canopy_progress', 'official_2018_metro_baseline', 15.3, 'percent',
    'Medium',
    'Melbourne''s vegetation, heat and land use data',
    'Victorian Government Department of Transport and Planning',
    'https://www.planning.vic.gov.au/guides-and-resources/Data-spatial-and-insights/melbournes-vegetation-heat-and-land-use-data',
    '2018 tree cover',
    'Official metropolitan Melbourne 2018 urban tree-canopy baseline of 15.3 percent.',
    'Metropolitan baseline context, not proof of property-level compliance.',
    DATE '2026-09-01'
),
(
    'canopy_progress', 'plan_for_victoria_urban_target', 30.0, 'percent',
    'High',
    'Action 12: Protect and enhance our canopy trees',
    'Victorian Government Department of Transport and Planning',
    'https://www.planning.vic.gov.au/planforvictoria/measuring-success/actions-and-outcomes/action-12-protect-and-enhance-our-canopy-trees',
    'What we''ll do',
    'Official Plan for Victoria target of 30 percent tree-canopy cover in urban areas.',
    'Urban-area target context, not proof of property-level compliance; do not apply to the rendered canopy proxy.',
    DATE '2026-09-01'
);

CREATE OR REPLACE FUNCTION classify_melbourne_daily_mean_air_temperature(
    p_forecast_maximum_c NUMERIC,
    p_following_overnight_minimum_c NUMERIC
)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
RETURN CASE
    WHEN p_forecast_maximum_c IS NULL
      OR p_following_overnight_minimum_c IS NULL
      OR p_forecast_maximum_c::TEXT IN ('NaN', 'Infinity', '-Infinity')
      OR p_following_overnight_minimum_c::TEXT IN ('NaN', 'Infinity', '-Infinity')
        THEN 'Unavailable'
    WHEN (
        p_forecast_maximum_c + p_following_overnight_minimum_c
    ) / 2.0 >= 30.0 THEN 'High'
    WHEN (
        p_forecast_maximum_c + p_following_overnight_minimum_c
    ) / 2.0 >= 27.2 THEN 'Medium'
    ELSE 'Low'
END;

COMMENT ON FUNCTION classify_melbourne_daily_mean_air_temperature(NUMERIC, NUMERIC) IS
    'Evidence-backed historical Melbourne daily-mean air-heat category. Uses forecast maximum plus following overnight minimum divided by two. Not valid for instantaneous BOM observations, Landsat LST or current BOM heatwave warnings.';

CREATE OR REPLACE FUNCTION classify_canopy_benchmark(
    p_canopy_percentage NUMERIC
)
RETURNS TEXT
LANGUAGE plpgsql
IMMUTABLE
PARALLEL SAFE
AS $function$
BEGIN
    IF p_canopy_percentage IS NULL
       OR p_canopy_percentage::TEXT IN ('NaN', 'Infinity', '-Infinity') THEN
        RETURN 'Unavailable';
    END IF;
    IF p_canopy_percentage < 0 OR p_canopy_percentage > 100 THEN
        RAISE EXCEPTION 'canopy percentage must be between 0 and 100';
    END IF;
    IF p_canopy_percentage >= 30.0 THEN
        RETURN 'High';
    END IF;
    IF p_canopy_percentage >= 15.3 THEN
        RETURN 'Medium';
    END IF;
    RETURN 'Low';
END;
$function$;

COMMENT ON FUNCTION classify_canopy_benchmark(NUMERIC) IS
    'Evidence-backed canopy progress against the official 15.3 percent metropolitan baseline and current 30 percent Victorian urban-area target. Not valid for the rendered Vicmap proxy or proof of property-level compliance.';

COMMIT;

-- Current multi-station BOM source (migration 025). The earlier Olympic Park
-- record is retained for provenance of historical versions.
INSERT INTO dataset_source (
    source_name, publisher, source_url, licence, source_category,
    geographic_coverage, access_method, update_frequency
) VALUES (
    'BOM Melbourne station observations', 'Bureau of Meteorology',
    'https://www.bom.gov.au/fwo/IDV60901/', NULL, 'weather', 'Melbourne',
    'Official station-specific JSON feeds listed in config/bom_stations.json',
    'frequent'
)
ON CONFLICT (source_name, publisher) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    licence = EXCLUDED.licence,
    source_category = EXCLUDED.source_category,
    geographic_coverage = EXCLUDED.geographic_coverage,
    access_method = EXCLUDED.access_method,
    update_frequency = EXCLUDED.update_frequency;

-- Defined here before the property-canopy function; migration 022 later
-- replaces it with the same current implementation in the cumulative schema.
CREATE OR REPLACE FUNCTION normalize_melbourne_address_search(p_address TEXT)
RETURNS TEXT
LANGUAGE plpgsql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $function$
DECLARE
    v_address TEXT;
BEGIN
    v_address := REGEXP_REPLACE(UPPER(BTRIM(p_address)), '[[:space:]]+', ' ', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mRD\M', 'ROAD', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mAVE\M', 'AVENUE', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mAV\M', 'AVENUE', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mBLVD\M', 'BOULEVARD', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mCRES\M', 'CRESCENT', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mCT\M', 'COURT', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mDR\M', 'DRIVE', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mHWY\M', 'HIGHWAY', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mLN\M', 'LANE', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mPDE\M', 'PARADE', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mPL\M', 'PLACE', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mTCE\M', 'TERRACE', 'g');
    RETURN v_address;
END;
$function$;

-- Property-level canopy (migration 023)
BEGIN;

CREATE TABLE property_canopy_summary (
    property_canopy_summary_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    source_canopy_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    parcel_id UUID NOT NULL REFERENCES parcel(parcel_id),
    observed_on DATE NOT NULL,
    canopy_area_m2 NUMERIC CHECK (canopy_area_m2 IS NULL OR canopy_area_m2 >= 0),
    parcel_area_m2 NUMERIC NOT NULL CHECK (parcel_area_m2 > 0),
    raster_covered_area_m2 NUMERIC NOT NULL CHECK (raster_covered_area_m2 >= 0),
    canopy_percentage NUMERIC(6, 2) CHECK (
        canopy_percentage IS NULL OR canopy_percentage BETWEEN 0 AND 100
    ),
    coverage_percentage NUMERIC(6, 2) NOT NULL CHECK (
        coverage_percentage BETWEEN 0 AND 100
    ),
    source_pixel_size_m NUMERIC NOT NULL CHECK (
        source_pixel_size_m > 0 AND source_pixel_size_m <= 2
    ),
    calculation_method TEXT NOT NULL DEFAULT 'parcel_clip_pixel_centre_v1',
    quality_status TEXT NOT NULL CHECK (quality_status IN ('passed', 'failed')),
    failure_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (dataset_version_id, parcel_id),
    CHECK (
        (quality_status = 'passed' AND canopy_percentage IS NOT NULL
         AND canopy_area_m2 IS NOT NULL AND coverage_percentage >= 95)
        OR
        (quality_status = 'failed' AND canopy_percentage IS NULL
         AND failure_reason IS NOT NULL)
    )
);

CREATE INDEX idx_property_canopy_parcel_version
    ON property_canopy_summary(parcel_id, dataset_version_id);
CREATE INDEX idx_property_canopy_source_version
    ON property_canopy_summary(source_canopy_version_id);

CREATE OR REPLACE VIEW latest_melbourne_property_canopy AS
WITH latest_version AS (
    SELECT dv.dataset_version_id
    FROM dataset_version AS dv
    JOIN dataset_source AS ds USING (source_id)
    JOIN analysis_area AS aa USING (analysis_area_id)
    WHERE ds.source_name = 'Vicmap Vegetation - Tree Extent'
      AND aa.source_area_code = '2GMEL'
      AND aa.source_year = 2026
      AND dv.integration_status = 'integrated'
      AND dv.publication_status = 'application_ready'
      AND dv.quality_pass_rate >= 95
      AND dv.derivation_method = 'property_canopy_raster_clip_v1'
    ORDER BY dv.extracted_at DESC
    LIMIT 1
)
SELECT summary.*
FROM property_canopy_summary AS summary
JOIN latest_version USING (dataset_version_id)
WHERE summary.quality_status = 'passed';

CREATE OR REPLACE FUNCTION get_property_canopy_by_address(
    p_address_search TEXT,
    p_result_limit INTEGER DEFAULT 10
)
RETURNS TABLE (
    address_id UUID,
    parcel_id UUID,
    full_address TEXT,
    parcel_area_m2 NUMERIC,
    canopy_area_m2 NUMERIC,
    property_canopy_percentage NUMERIC,
    raster_coverage_percentage NUMERIC,
    observed_on DATE,
    source_pixel_size_m NUMERIC,
    calculation_method TEXT,
    data_status TEXT,
    limitation TEXT
)
LANGUAGE SQL
STABLE
PARALLEL SAFE
AS $function$
WITH candidates AS (
    SELECT property.*
    FROM latest_greater_melbourne_address_property AS property
    WHERE p_address_search IS NOT NULL
      AND BTRIM(p_address_search) <> ''
      AND normalize_melbourne_address_search(property.full_address)
          LIKE normalize_melbourne_address_search(p_address_search) || '%'
    ORDER BY
        CASE WHEN normalize_melbourne_address_search(property.full_address) =
                  normalize_melbourne_address_search(p_address_search) THEN 0 ELSE 1 END,
        property.full_address,
        property.source_address_id
    LIMIT LEAST(GREATEST(COALESCE(p_result_limit, 10), 1), 50)
)
SELECT
    candidate.address_id,
    candidate.parcel_id,
    candidate.full_address,
    candidate.parcel_area_m2,
    canopy.canopy_area_m2,
    canopy.canopy_percentage,
    canopy.coverage_percentage,
    canopy.observed_on,
    canopy.source_pixel_size_m,
    canopy.calculation_method,
    CASE
        WHEN candidate.parcel_id IS NULL THEN 'Unavailable'
        WHEN canopy.property_canopy_summary_id IS NULL THEN 'Unavailable'
        ELSE 'Available'
    END AS data_status,
    CASE
        WHEN candidate.parcel_id IS NULL THEN 'No parcel geometry is linked to this address.'
        WHEN canopy.property_canopy_summary_id IS NULL THEN
            'No application-ready analytical property-canopy result is loaded; missing data is not zero canopy.'
        ELSE 'Machine-derived canopy from source imagery; not a current field survey.'
    END AS limitation
FROM candidates AS candidate
LEFT JOIN latest_melbourne_property_canopy AS canopy
  ON canopy.parcel_id = candidate.parcel_id;
$function$;

COMMENT ON TABLE property_canopy_summary IS
    'Versioned parcel-clipped canopy measures from a <=2 m analytical Tree Extent GeoTIFF. Rendered API proxy mosaics are prohibited.';
COMMENT ON FUNCTION get_property_canopy_by_address(TEXT, INTEGER) IS
    'Returns canopy clipped to the matched Melbourne parcel. Missing analytical results return Unavailable, never zero canopy.';

COMMIT;

-- Migration 021: correct the historical temperature contract without changing
-- the checksum of already-applied migration 020.
BEGIN;

ALTER TABLE environmental_classification_reference
    -- PostgreSQL shortens migration 020's generated name to 63 characters.
    DROP CONSTRAINT environmental_classification_referen_classification_label_check;

ALTER TABLE environmental_classification_reference
    ALTER COLUMN classification_label DROP NOT NULL,
    ADD COLUMN evidence_role TEXT NOT NULL DEFAULT 'classification_threshold'
        CHECK (evidence_role IN (
            'classification_threshold', 'historical_percentile_context_only'
        )),
    ADD COLUMN minimum_consecutive_days INTEGER
        CHECK (minimum_consecutive_days IS NULL OR minimum_consecutive_days > 0),
    ADD COLUMN status TEXT NOT NULL DEFAULT 'historical_context';

UPDATE environmental_classification_reference
SET classification_label = NULL,
    evidence_role = 'historical_percentile_context_only',
    minimum_consecutive_days = 2,
    status = 'historical_context',
    limitation = 'The 27.2 C percentile requires two or more consecutive summer days. It is historical percentile context only and is not used to classify a single forecast pair.'
WHERE metric_code = 'daily_mean_air_temperature'
  AND threshold_code = 'elevated_daily_mean';

UPDATE environmental_classification_reference
SET classification_label = 'At or above historical 30 C threshold',
    evidence_role = 'classification_threshold',
    status = 'historical_context',
    limitation = 'Historical Victorian Central District context only. The system ended in 2021-22 and is not comparable with the current BOM national heatwave warning.'
WHERE metric_code = 'daily_mean_air_temperature'
  AND threshold_code = 'historical_central_heat_health';

DROP FUNCTION classify_melbourne_daily_mean_air_temperature(NUMERIC, NUMERIC);

CREATE FUNCTION classify_melbourne_daily_mean_air_temperature(
    p_forecast_maximum_c NUMERIC,
    p_following_overnight_minimum_c NUMERIC
)
RETURNS JSONB
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
RETURN JSONB_BUILD_OBJECT(
    'classification', CASE
        WHEN p_forecast_maximum_c IS NULL
          OR p_following_overnight_minimum_c IS NULL
          OR p_forecast_maximum_c::TEXT IN ('NaN', 'Infinity', '-Infinity')
          OR p_following_overnight_minimum_c::TEXT IN ('NaN', 'Infinity', '-Infinity')
            THEN 'Unavailable'
        WHEN (p_forecast_maximum_c + p_following_overnight_minimum_c) / 2.0 >= 30.0
            THEN 'At or above historical 30 C threshold'
        ELSE 'Below historical 30 C threshold'
    END,
    'daily_mean_c', CASE
        WHEN p_forecast_maximum_c IS NULL
          OR p_following_overnight_minimum_c IS NULL
          OR p_forecast_maximum_c::TEXT IN ('NaN', 'Infinity', '-Infinity')
          OR p_following_overnight_minimum_c::TEXT IN ('NaN', 'Infinity', '-Infinity')
            THEN NULL
        ELSE ROUND((p_forecast_maximum_c + p_following_overnight_minimum_c) / 2.0, 3)
    END,
    'method', 'historical_victorian_central_daily_mean_threshold',
    'status', 'historical_context',
    'limitation', 'Historical Victorian Central District context only. The system ended in 2021-22 and is not comparable with the current BOM heatwave warning. The 27.2 C research percentile requires two or more consecutive days and is not used to classify this one-day pair.',
    'source', JSONB_BUILD_OBJECT(
        'title', 'Planning for extreme heat and heatwaves',
        'publisher', 'Victorian Department of Health',
        'url', 'https://www.health.vic.gov.au/environmental-health/planning-for-extreme-heat-and-heatwaves',
        'locator', 'Calculating the average temperature; Figure 1'
    ),
    'historical_percentile_context', JSONB_BUILD_OBJECT(
        'threshold_c', 27.2,
        'minimum_consecutive_days', 2,
        'used_for_this_classification', FALSE,
        'source', JSONB_BUILD_OBJECT(
            'title', 'The impact of heatwaves on mortality in Australia: a multicity study',
            'publisher', 'BMJ Open',
            'url', 'https://pmc.ncbi.nlm.nih.gov/articles/PMC3931989/',
            'locator', 'Table 2: Heatwave days and threshold'
        )
    )
);

COMMENT ON FUNCTION classify_melbourne_daily_mean_air_temperature(NUMERIC, NUMERIC) IS
    'Returns structured historical context for one forecast maximum/following-minimum pair. It never returns a current heat warning; 27.2 C is recorded only as two-consecutive-day percentile context.';

COMMIT;

-- Migration 022: address abbreviation normalisation and query indexes.
BEGIN;

-- Cover missing foreign-key and high-frequency filter columns. Primary-key and
-- existing unique/GiST indexes are deliberately not duplicated.
CREATE INDEX IF NOT EXISTS idx_dataset_source_category
    ON dataset_source(source_category);
CREATE INDEX IF NOT EXISTS idx_dataset_version_application_lookup
    ON dataset_version(
        source_id, analysis_area_id, integration_status,
        publication_status, extracted_at DESC
    );
CREATE INDEX IF NOT EXISTS idx_quality_result_rule
    ON data_quality_result(quality_rule_id);
CREATE INDEX IF NOT EXISTS idx_transformation_input_version
    ON transformation_run(input_version_id);
CREATE INDEX IF NOT EXISTS idx_transformation_output_version
    ON transformation_run(output_version_id)
    WHERE output_version_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_integration_run_version
    ON integration_run(dataset_version_id);
CREATE INDEX IF NOT EXISTS idx_data_limitation_version
    ON data_limitation(dataset_version_id);

CREATE INDEX IF NOT EXISTS idx_address_dataset_version
    ON address(dataset_version_id);
CREATE INDEX IF NOT EXISTS idx_address_upper_full_address_prefix
    ON address(UPPER(full_address) text_pattern_ops);
CREATE INDEX IF NOT EXISTS idx_address_postcode_locality
    ON address(postcode, locality_name);
CREATE INDEX IF NOT EXISTS idx_parcel_dataset_version
    ON parcel(dataset_version_id);
CREATE INDEX IF NOT EXISTS idx_site_address
    ON site(address_id) WHERE address_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_site_parcel
    ON site(parcel_id) WHERE parcel_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_weather_version_station_time
    ON weather_observation(dataset_version_id, station_code, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_heat_observation_version
    ON heat_observation(dataset_version_id);
CREATE INDEX IF NOT EXISTS idx_heat_observation_site
    ON heat_observation(site_id) WHERE site_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_vegetation_observation_version
    ON vegetation_observation(dataset_version_id);
CREATE INDEX IF NOT EXISTS idx_vegetation_observation_site
    ON vegetation_observation(site_id) WHERE site_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_canopy_patch_version
    ON canopy_patch(dataset_version_id);
CREATE INDEX IF NOT EXISTS idx_canopy_patch_site
    ON canopy_patch(site_id) WHERE site_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_urban_tree_version_quality
    ON urban_tree(dataset_version_id, quality_status);
CREATE INDEX IF NOT EXISTS idx_urban_tree_site
    ON urban_tree(site_id) WHERE site_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_urban_tree_species
    ON urban_tree(species_id) WHERE species_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_cost_estimate_analysis_area
    ON cost_estimate(analysis_area_id) WHERE analysis_area_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_analysis_run_site_time
    ON analysis_run(site_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_run_dataset_version
    ON analysis_run(dataset_version_id);
CREATE INDEX IF NOT EXISTS idx_analysis_run_model_version
    ON analysis_run(model_version_id) WHERE model_version_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_measure_result_measure
    ON measure_result(measure_id);
CREATE INDEX IF NOT EXISTS idx_measure_test_result_case
    ON measure_test_result(test_case_id);
CREATE INDEX IF NOT EXISTS idx_measure_test_result_model
    ON measure_test_result(model_version_id)
    WHERE model_version_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_model_evidence_evidence
    ON model_evidence(evidence_id);
CREATE INDEX IF NOT EXISTS idx_intervention_parameter_source_evidence
    ON intervention_model_parameter(source_evidence_id)
    WHERE source_evidence_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_intervention_validation_run_model
    ON intervention_model_validation_run(model_version_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_classification_scheme_area_status
    ON environmental_classification_scheme(analysis_area_id, status);
CREATE INDEX IF NOT EXISTS idx_classification_threshold_source_version
    ON environmental_classification_threshold(source_dataset_version_id);
CREATE INDEX IF NOT EXISTS idx_classification_reference_metric
    ON environmental_classification_reference(metric_code, threshold_value);

CREATE OR REPLACE FUNCTION normalize_melbourne_address_search(p_address TEXT)
RETURNS TEXT
LANGUAGE plpgsql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $function$
DECLARE
    v_address TEXT;
BEGIN
    v_address := REGEXP_REPLACE(UPPER(BTRIM(p_address)), '[[:space:]]+', ' ', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mRD\M', 'ROAD', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mAVE\M', 'AVENUE', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mAV\M', 'AVENUE', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mBLVD\M', 'BOULEVARD', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mCRES\M', 'CRESCENT', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mCT\M', 'COURT', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mDR\M', 'DRIVE', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mHWY\M', 'HIGHWAY', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mLN\M', 'LANE', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mPDE\M', 'PARADE', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mPL\M', 'PLACE', 'g');
    v_address := REGEXP_REPLACE(v_address, '\mTCE\M', 'TERRACE', 'g');
    RETURN v_address;
END;
$function$;

COMMENT ON FUNCTION normalize_melbourne_address_search(TEXT) IS
    'Normalises case/whitespace and expands unambiguous Australian street-type abbreviations before Vicmap prefix matching. ST is intentionally not expanded because it can mean Saint, as in St Kilda.';

CREATE OR REPLACE FUNCTION get_property_baseline(
    p_address_search TEXT,
    p_result_limit INTEGER DEFAULT 10
)
RETURNS TABLE (
    address_id UUID,
    parcel_id UUID,
    full_address TEXT,
    locality_name TEXT,
    postcode TEXT,
    source_property_id TEXT,
    parcel_area_m2 NUMERIC,
    lot_size_category TEXT,
    property_type TEXT,
    property_status TEXT,
    longitude NUMERIC,
    latitude NUMERIC,
    parcel_geometry_geojson JSONB,
    land_surface_temperature_c NUMERIC,
    surface_temperature_observed_on DATE,
    temperature_measurement_type TEXT,
    heat_baseline_method TEXT,
    heat_cell_geojson JSONB,
    current_air_temperature_c NUMERIC,
    current_apparent_temperature_c NUMERIC,
    weather_station_name TEXT,
    weather_observed_at TIMESTAMPTZ,
    weather_station_distance_km NUMERIC,
    air_temperature_context_status TEXT,
    neighbourhood_canopy_percentage NUMERIC,
    property_canopy_percentage NUMERIC,
    canopy_analysis_scope TEXT,
    canopy_observed_on DATE,
    canopy_source_type TEXT,
    canopy_source_is_proxy BOOLEAN,
    canopy_cell_geojson JSONB,
    mapped_property_tree_count BIGINT,
    property_tree_data_status TEXT,
    data_quality_status TEXT,
    limitations JSONB,
    heat_classification TEXT,
    canopy_classification TEXT,
    classification_scheme_version TEXT,
    classification_scope TEXT
)
LANGUAGE SQL
STABLE
PARALLEL SAFE
AS $function$
WITH baseline AS (
    SELECT *
    FROM get_property_baseline_pre_classification_legacy(
        normalize_melbourne_address_search(p_address_search), p_result_limit
    )
), current_scheme AS (
    SELECT DISTINCT version_label, classification_scope
    FROM current_environmental_classification_threshold
)
SELECT
    baseline.*,
    classify_environmental_value(
        'heat', baseline.land_surface_temperature_c, scheme.version_label
    ) AS heat_classification,
    classify_environmental_value(
        'canopy', baseline.neighbourhood_canopy_percentage, scheme.version_label
    ) AS canopy_classification,
    scheme.version_label AS classification_scheme_version,
    scheme.classification_scope
FROM baseline
LEFT JOIN current_scheme AS scheme ON TRUE;
$function$;

COMMENT ON FUNCTION get_property_baseline(TEXT, INTEGER) IS
    'Returns the property baseline with versioned classifications after expanding supported Australian street-type abbreviations such as RD to ROAD.';

CREATE OR REPLACE FUNCTION get_environment_context_by_address(
    p_address_search TEXT,
    p_radius_m DOUBLE PRECISION DEFAULT 500.0,
    p_layers TEXT[] DEFAULT ARRAY['trees', 'heat']::TEXT[],
    p_result_limit INTEGER DEFAULT 1000
)
RETURNS TABLE (
    layer TEXT,
    feature_id TEXT,
    dataset_version_id UUID,
    distance_m NUMERIC,
    observed_on DATE,
    properties JSONB,
    geometry_geojson JSONB
)
LANGUAGE plpgsql
STABLE
PARALLEL SAFE
AS $function$
DECLARE
    v_normalized_search TEXT;
    v_matched_address TEXT;
    v_longitude DOUBLE PRECISION;
    v_latitude DOUBLE PRECISION;
    v_match_count INTEGER;
    v_exact_match_count INTEGER;
BEGIN
    IF p_address_search IS NULL OR BTRIM(p_address_search) = '' THEN
        RAISE EXCEPTION 'address search is required';
    END IF;
    v_normalized_search := normalize_melbourne_address_search(p_address_search);

    WITH matches AS MATERIALIZED (
        SELECT baseline.*,
               normalize_melbourne_address_search(baseline.full_address) =
                   v_normalized_search AS is_exact
        FROM get_property_baseline(v_normalized_search, 2) AS baseline
    ), ranked AS (
        SELECT
            matches.*,
            COUNT(*) OVER ()::INTEGER AS match_count,
            COUNT(*) FILTER (WHERE is_exact) OVER ()::INTEGER
                AS exact_match_count,
            ROW_NUMBER() OVER (
                ORDER BY
                    CASE WHEN is_exact THEN 0 ELSE 1 END,
                    full_address,
                    address_id
            ) AS match_rank
        FROM matches
    )
    SELECT
        ranked.full_address,
        ranked.longitude::DOUBLE PRECISION,
        ranked.latitude::DOUBLE PRECISION,
        ranked.match_count,
        ranked.exact_match_count
    INTO
        v_matched_address,
        v_longitude,
        v_latitude,
        v_match_count,
        v_exact_match_count
    FROM ranked
    WHERE match_rank = 1;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'no Melbourne address matched: %', BTRIM(p_address_search);
    END IF;
    IF v_exact_match_count > 1
       OR (v_exact_match_count = 0 AND v_match_count > 1) THEN
        RAISE EXCEPTION
            'address search is ambiguous: %. Supply the complete address and postcode',
            BTRIM(p_address_search);
    END IF;
    IF v_longitude IS NULL OR v_latitude IS NULL THEN
        RAISE EXCEPTION 'matched address has no usable coordinate: %', v_matched_address;
    END IF;

    RETURN QUERY
    SELECT context.*
    FROM get_environment_context(
        v_longitude, v_latitude, p_radius_m, p_layers, p_result_limit
    ) AS context;
END;
$function$;

COMMENT ON FUNCTION get_environment_context_by_address(
    TEXT, DOUBLE PRECISION, TEXT[], INTEGER
) IS
    'Normalises supported street abbreviations, resolves one unambiguous Melbourne property address and returns bounded application-ready tree and heat context.';

COMMIT;

-- Integrate migration 023 property canopy into the current baseline contract.
BEGIN;

ALTER FUNCTION get_property_baseline(TEXT, INTEGER)
    RENAME TO get_property_baseline_pre_property_canopy_legacy;

CREATE OR REPLACE FUNCTION get_property_baseline(
    p_address_search TEXT,
    p_result_limit INTEGER DEFAULT 10
)
RETURNS TABLE (
    address_id UUID, parcel_id UUID, full_address TEXT, locality_name TEXT,
    postcode TEXT, source_property_id TEXT, parcel_area_m2 NUMERIC,
    lot_size_category TEXT, property_type TEXT, property_status TEXT,
    longitude NUMERIC, latitude NUMERIC, parcel_geometry_geojson JSONB,
    land_surface_temperature_c NUMERIC, surface_temperature_observed_on DATE,
    temperature_measurement_type TEXT, heat_baseline_method TEXT,
    heat_cell_geojson JSONB, current_air_temperature_c NUMERIC,
    current_apparent_temperature_c NUMERIC, weather_station_name TEXT,
    weather_observed_at TIMESTAMPTZ, weather_station_distance_km NUMERIC,
    air_temperature_context_status TEXT, neighbourhood_canopy_percentage NUMERIC,
    property_canopy_percentage NUMERIC, canopy_analysis_scope TEXT,
    canopy_observed_on DATE, canopy_source_type TEXT,
    canopy_source_is_proxy BOOLEAN, canopy_cell_geojson JSONB,
    mapped_property_tree_count BIGINT, property_tree_data_status TEXT,
    data_quality_status TEXT, limitations JSONB, heat_classification TEXT,
    canopy_classification TEXT, classification_scheme_version TEXT,
    classification_scope TEXT
)
LANGUAGE SQL
STABLE
PARALLEL SAFE
AS $function$
WITH baseline AS (
    SELECT *
    FROM get_property_baseline_pre_property_canopy_legacy(
        p_address_search, p_result_limit
    )
)
SELECT
    baseline.address_id, baseline.parcel_id, baseline.full_address,
    baseline.locality_name, baseline.postcode, baseline.source_property_id,
    baseline.parcel_area_m2, baseline.lot_size_category, baseline.property_type,
    baseline.property_status, baseline.longitude, baseline.latitude,
    baseline.parcel_geometry_geojson, baseline.land_surface_temperature_c,
    baseline.surface_temperature_observed_on, baseline.temperature_measurement_type,
    baseline.heat_baseline_method, baseline.heat_cell_geojson,
    baseline.current_air_temperature_c, baseline.current_apparent_temperature_c,
    baseline.weather_station_name, baseline.weather_observed_at,
    baseline.weather_station_distance_km, baseline.air_temperature_context_status,
    baseline.neighbourhood_canopy_percentage,
    property_canopy.canopy_percentage AS property_canopy_percentage,
    CASE WHEN property_canopy.property_canopy_summary_id IS NOT NULL
         THEN 'property_raster_clip'
         ELSE baseline.canopy_analysis_scope END AS canopy_analysis_scope,
    COALESCE(property_canopy.observed_on, baseline.canopy_observed_on),
    CASE WHEN property_canopy.property_canopy_summary_id IS NOT NULL
         THEN 'analytical_geotiff_property_clip'
         ELSE baseline.canopy_source_type END AS canopy_source_type,
    CASE WHEN property_canopy.property_canopy_summary_id IS NOT NULL
         THEN FALSE ELSE baseline.canopy_source_is_proxy END AS canopy_source_is_proxy,
    baseline.canopy_cell_geojson, baseline.mapped_property_tree_count,
    baseline.property_tree_data_status, baseline.data_quality_status,
    baseline.limitations || JSONB_BUILD_OBJECT(
        'property_canopy',
        CASE WHEN property_canopy.property_canopy_summary_id IS NOT NULL THEN
            FORMAT(
                'Parcel-clipped analytical Tree Extent at %s m source resolution; %s%% raster coverage. Machine-derived, not a current field survey.',
                property_canopy.source_pixel_size_m,
                property_canopy.coverage_percentage
            )
        ELSE
            'Unavailable until a quality-passed analytical Tree Extent result covers this parcel; missing is not zero canopy.'
        END
    ) AS limitations,
    baseline.heat_classification,
    baseline.canopy_classification,
    baseline.classification_scheme_version,
    baseline.classification_scope
FROM baseline
LEFT JOIN latest_melbourne_property_canopy AS property_canopy
  ON property_canopy.parcel_id = baseline.parcel_id;
$function$;

COMMENT ON FUNCTION get_property_baseline(TEXT, INTEGER) IS
    'Returns existing heat, weather and 500 m canopy context plus parcel-clipped analytical property canopy when an application-ready result exists. The canopy classification remains neighbourhood-relative.';

COMMIT;

-- Property current air temperature (migration 024)
BEGIN;

CREATE INDEX IF NOT EXISTS idx_weather_current_property_lookup
    ON weather_observation(observed_at DESC, station_code)
    INCLUDE (air_temperature_c, apparent_temperature_c, station_name)
    WHERE observation_location IS NOT NULL
      AND air_temperature_c IS NOT NULL
      AND quality_status = 'passed';

CREATE OR REPLACE FUNCTION get_property_air_temperature_by_address(
    p_address_search TEXT,
    p_result_limit INTEGER DEFAULT 10
)
RETURNS TABLE (
    address_id UUID, parcel_id UUID, full_address TEXT,
    air_temperature_c NUMERIC, apparent_temperature_c NUMERIC,
    temperature_unit TEXT, station_code TEXT, station_name TEXT,
    observed_at TIMESTAMPTZ, observation_age_minutes NUMERIC,
    station_distance_km NUMERIC, context_status TEXT, data_status TEXT,
    measurement_type TEXT, source_dataset_version_id UUID, source_name TEXT,
    source_publisher TEXT, source_url TEXT, limitation TEXT
)
LANGUAGE SQL
STABLE
PARALLEL SAFE
AS $function$
WITH candidates AS (
    SELECT property.*
    FROM latest_greater_melbourne_address_property AS property
    WHERE p_address_search IS NOT NULL
      AND BTRIM(p_address_search) <> ''
      AND normalize_melbourne_address_search(property.full_address)
          LIKE normalize_melbourne_address_search(p_address_search) || '%'
    ORDER BY
        CASE WHEN normalize_melbourne_address_search(property.full_address) =
                  normalize_melbourne_address_search(p_address_search) THEN 0 ELSE 1 END,
        CASE WHEN property.is_primary = 'Y' THEN 0 ELSE 1 END,
        property.full_address,
        property.source_address_id
    LIMIT LEAST(GREATEST(COALESCE(p_result_limit, 10), 1), 50)
)
SELECT
    candidate.address_id, candidate.parcel_id, candidate.full_address,
    CASE WHEN weather.distance_m <= 25000
         THEN weather.air_temperature_c END,
    CASE WHEN weather.distance_m <= 25000
         THEN weather.apparent_temperature_c END,
    'degC'::TEXT, weather.station_code, weather.station_name, weather.observed_at,
    CASE WHEN weather.observed_at IS NULL THEN NULL
         ELSE ROUND(GREATEST(
             0, EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - weather.observed_at)) / 60
         )::NUMERIC, 1) END,
    CASE WHEN weather.distance_m IS NULL THEN NULL
         ELSE ROUND((weather.distance_m / 1000.0)::NUMERIC, 2) END,
    CASE
        WHEN weather.weather_observation_id IS NULL
            THEN 'unavailable_no_observation_within_3_hours'
        WHEN weather.distance_m <= 10000 THEN 'good_local_context'
        WHEN weather.distance_m <= 25000 THEN 'regional_context_warning'
        ELSE 'too_distant_temperature_suppressed'
    END,
    CASE
        WHEN weather.weather_observation_id IS NULL OR weather.distance_m > 25000
            THEN 'Unavailable'
        ELSE 'Available'
    END,
    'nearest_recent_bom_station_air_temperature_context'::TEXT,
    weather.dataset_version_id, weather.source_name, weather.publisher,
    weather.source_url,
    CASE
        WHEN weather.weather_observation_id IS NULL THEN
            'No application-ready BOM station observation is available within the three-hour freshness window; missing temperature is not zero.'
        WHEN weather.distance_m <= 10000 THEN
            'Nearest BOM observation within 10 km; local station context, not a temperature measured at the property.'
        WHEN weather.distance_m <= 25000 THEN
            'Nearest BOM observation is 10-25 km away; regional context only, not a temperature measured at the property.'
        ELSE
            'Nearest recent BOM station is more than 25 km away; temperature is suppressed rather than presented as property context.'
    END
FROM candidates AS candidate
LEFT JOIN LATERAL (
    SELECT observation.*,
           ST_Distance(observation.observation_location, candidate.address_location) AS distance_m
    FROM (
        SELECT DISTINCT ON (weather.station_code)
               weather.*, source.source_name, source.publisher,
               source.source_url, version.extracted_at
        FROM weather_observation AS weather
        JOIN dataset_version AS version USING (dataset_version_id)
        JOIN dataset_source AS source USING (source_id)
        WHERE version.integration_status = 'integrated'
          AND version.publication_status = 'application_ready'
          AND weather.quality_status = 'passed'
          AND weather.air_temperature_c IS NOT NULL
          AND weather.observation_location IS NOT NULL
          AND weather.observed_at >= CURRENT_TIMESTAMP - INTERVAL '3 hours'
          AND weather.observed_at <= CURRENT_TIMESTAMP + INTERVAL '5 minutes'
        ORDER BY weather.station_code, weather.observed_at DESC,
                 version.extracted_at DESC
    ) AS observation
    ORDER BY observation.observation_location <-> candidate.address_location
    LIMIT 1
) AS weather ON TRUE;
$function$;

COMMENT ON FUNCTION get_property_air_temperature_by_address(TEXT, INTEGER) IS
    'Returns nearest recent BOM station air-temperature context for each matched Melbourne property. Values are in degrees Celsius, observations older than three hours are unavailable, and temperatures beyond 25 km are suppressed. This is not a temperature measured at the property.';

COMMIT;

BEGIN;

CREATE OR REPLACE VIEW current_environmental_classification_threshold AS
SELECT
    scheme.classification_scheme_id,
    scheme.version_label,
    scheme.analysis_area_id,
    'fixed_temperature_bands_with_canopy_terciles'::TEXT AS method,
    'fixed_temperature_display_bands_and_versioned_melbourne_canopy_thresholds'::TEXT
        AS classification_scope,
    scheme.calculated_at,
    threshold.metric_code,
    threshold.source_dataset_version_id,
    CASE WHEN threshold.metric_code = 'heat' THEN 27.0
         ELSE threshold.lower_threshold END AS lower_threshold,
    CASE WHEN threshold.metric_code = 'heat' THEN 30.0
         ELSE threshold.upper_threshold END AS upper_threshold,
    threshold.unit,
    threshold.sample_count,
    threshold.low_label,
    threshold.medium_label,
    threshold.high_label,
    threshold.missing_label,
    CASE WHEN threshold.metric_code = 'heat' THEN
        'GreenChanger display bands: Low <=27 C, Medium >27 C and <=30 C, High >30 C. Application-defined only; not a BOM heatwave, health-risk or comfort classification.'
    ELSE threshold.explanation END AS explanation
FROM environmental_classification_scheme AS scheme
JOIN environmental_classification_threshold AS threshold
  USING (classification_scheme_id)
WHERE scheme.status = 'active';

CREATE OR REPLACE FUNCTION search_melbourne_addresses(
    p_address_search TEXT,
    p_result_limit INTEGER DEFAULT 10
)
RETURNS TABLE (
    full_address TEXT, normalized_address TEXT, address_ids UUID[],
    parcel_ids UUID[], parcel_count BIGINT, longitude NUMERIC, latitude NUMERIC
)
LANGUAGE SQL
STABLE
PARALLEL SAFE
AS $function$
WITH distinct_pairs AS (
    SELECT DISTINCT ON (baseline.address_id, baseline.parcel_id)
        baseline.address_id, baseline.parcel_id, baseline.full_address,
        normalize_melbourne_address_search(baseline.full_address)
            AS normalized_address,
        baseline.longitude, baseline.latitude
    FROM get_property_baseline(
        normalize_melbourne_address_search(p_address_search), 50
    ) AS baseline
    WHERE p_address_search IS NOT NULL AND BTRIM(p_address_search) <> ''
    ORDER BY baseline.address_id, baseline.parcel_id
), grouped_addresses AS (
    SELECT MIN(full_address) AS full_address, normalized_address,
           ARRAY_AGG(DISTINCT address_id) FILTER (WHERE address_id IS NOT NULL),
           ARRAY_AGG(DISTINCT parcel_id) FILTER (WHERE parcel_id IS NOT NULL),
           COUNT(DISTINCT parcel_id), MIN(longitude), MIN(latitude)
    FROM distinct_pairs
    GROUP BY normalized_address
)
SELECT * FROM grouped_addresses
ORDER BY CASE WHEN normalized_address =
                       normalize_melbourne_address_search(p_address_search)
              THEN 0 ELSE 1 END,
         full_address
LIMIT LEAST(GREATEST(COALESCE(p_result_limit, 10), 1), 50);
$function$;

COMMENT ON FUNCTION search_melbourne_addresses(TEXT, INTEGER) IS
    'Returns one row per normalized Melbourne address, deduplicates repeated address-parcel joins, and preserves all distinct address and parcel IDs for selection.';

CREATE OR REPLACE FUNCTION get_environment_context_by_address(
    p_address_search TEXT,
    p_radius_m DOUBLE PRECISION DEFAULT 500.0,
    p_layers TEXT[] DEFAULT ARRAY['trees', 'heat']::TEXT[],
    p_result_limit INTEGER DEFAULT 1000
)
RETURNS TABLE (
    layer TEXT, feature_id TEXT, dataset_version_id UUID, distance_m NUMERIC,
    observed_on DATE, properties JSONB, geometry_geojson JSONB
)
LANGUAGE plpgsql
STABLE
PARALLEL SAFE
AS $function$
DECLARE
    v_normalized_search TEXT;
    v_matched_address TEXT;
    v_longitude DOUBLE PRECISION;
    v_latitude DOUBLE PRECISION;
    v_address_count INTEGER;
    v_exact_address_count INTEGER;
BEGIN
    IF p_address_search IS NULL OR BTRIM(p_address_search) = '' THEN
        RAISE EXCEPTION 'address search is required';
    END IF;
    v_normalized_search := normalize_melbourne_address_search(p_address_search);

    WITH matches AS MATERIALIZED (
        SELECT address_match.*,
               address_match.normalized_address = v_normalized_search AS is_exact
        FROM search_melbourne_addresses(v_normalized_search, 50) AS address_match
    ), ranked AS (
        SELECT matches.*, COUNT(*) OVER ()::INTEGER AS address_count,
               COUNT(*) FILTER (WHERE is_exact) OVER ()::INTEGER
                   AS exact_address_count,
               ROW_NUMBER() OVER (
                   ORDER BY CASE WHEN is_exact THEN 0 ELSE 1 END, full_address
               ) AS match_rank
        FROM matches
    )
    SELECT full_address, longitude::DOUBLE PRECISION, latitude::DOUBLE PRECISION,
           address_count, exact_address_count
    INTO v_matched_address, v_longitude, v_latitude,
         v_address_count, v_exact_address_count
    FROM ranked
    WHERE match_rank = 1;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'no Melbourne address matched: %', BTRIM(p_address_search);
    END IF;
    IF v_exact_address_count = 0 AND v_address_count > 1 THEN
        RAISE EXCEPTION
            'address search is ambiguous: %. Supply the complete address and postcode',
            BTRIM(p_address_search);
    END IF;
    IF v_longitude IS NULL OR v_latitude IS NULL THEN
        RAISE EXCEPTION 'matched address has no usable coordinate: %', v_matched_address;
    END IF;

    RETURN QUERY
    SELECT context.*
    FROM get_environment_context(
        v_longitude, v_latitude, p_radius_m, p_layers, p_result_limit
    ) AS context;
END;
$function$;

COMMENT ON FUNCTION get_environment_context_by_address(
    TEXT, DOUBLE PRECISION, TEXT[], INTEGER
) IS
    'Normalises abbreviations and resolves one distinct Melbourne address. Repeated joins and multiple parcels sharing that address do not create false ambiguity; genuinely different matching addresses remain ambiguous.';

COMMIT;

BEGIN;

CREATE OR REPLACE FUNCTION search_melbourne_addresses(
    p_address_search TEXT,
    p_result_limit INTEGER DEFAULT 10
)
RETURNS TABLE (
    full_address TEXT, normalized_address TEXT, address_ids UUID[],
    parcel_ids UUID[], parcel_count BIGINT, longitude NUMERIC, latitude NUMERIC
)
LANGUAGE SQL
STABLE
PARALLEL SAFE
AS $function$
WITH distinct_pairs AS (
    SELECT DISTINCT ON (baseline.address_id, baseline.parcel_id)
        baseline.address_id, baseline.parcel_id, baseline.full_address,
        normalize_melbourne_address_search(baseline.full_address)
            AS normalized_address,
        baseline.longitude, baseline.latitude
    FROM get_property_baseline(
        normalize_melbourne_address_search(p_address_search), 50
    ) AS baseline
    WHERE p_address_search IS NOT NULL AND BTRIM(p_address_search) <> ''
    ORDER BY baseline.address_id, baseline.parcel_id
), ranked_pairs AS (
    SELECT distinct_pairs.*,
           ROW_NUMBER() OVER (
               PARTITION BY distinct_pairs.normalized_address
               ORDER BY
                   CASE WHEN distinct_pairs.longitude IS NULL
                              OR distinct_pairs.latitude IS NULL THEN 1 ELSE 0 END,
                   distinct_pairs.full_address,
                   distinct_pairs.address_id,
                   distinct_pairs.parcel_id
           ) AS representative_rank
    FROM distinct_pairs
), grouped_addresses AS (
    SELECT normalized_address,
           ARRAY_AGG(DISTINCT address_id)
               FILTER (WHERE address_id IS NOT NULL) AS address_ids,
           ARRAY_AGG(DISTINCT parcel_id)
               FILTER (WHERE parcel_id IS NOT NULL) AS parcel_ids,
           COUNT(DISTINCT parcel_id) AS parcel_count
    FROM ranked_pairs
    GROUP BY normalized_address
), representative AS (
    SELECT full_address, normalized_address, longitude, latitude
    FROM ranked_pairs
    WHERE representative_rank = 1
)
SELECT representative.full_address, representative.normalized_address,
       grouped_addresses.address_ids, grouped_addresses.parcel_ids,
       grouped_addresses.parcel_count, representative.longitude,
       representative.latitude
FROM representative
JOIN grouped_addresses USING (normalized_address)
ORDER BY CASE WHEN representative.normalized_address =
                       normalize_melbourne_address_search(p_address_search)
              THEN 0 ELSE 1 END,
         representative.full_address
LIMIT LEAST(GREATEST(COALESCE(p_result_limit, 10), 1), 50);
$function$;

COMMENT ON FUNCTION search_melbourne_addresses(TEXT, INTEGER) IS
    'Returns one row per normalized Melbourne address and all distinct parcel options. Full address, longitude and latitude come from the same deterministic representative row; coordinates are never assembled from independent aggregates.';

COMMIT;

-- Fixed evidence-backed canopy classification (migration 032).
BEGIN;

-- Canopy is now classified against two published Victorian reference values,
-- rather than against distribution-dependent Melbourne terciles. Historical
-- schemes remain in the tables for auditability; this migration changes the
-- effective view and the function used to create future schemes.
ALTER TABLE environmental_classification_scheme
    DROP CONSTRAINT IF EXISTS environmental_classification_scheme_method_check;

ALTER TABLE environmental_classification_scheme
    ADD CONSTRAINT environmental_classification_scheme_method_check
    CHECK (method IN ('tercile_percentile_cont', 'fixed_evidence_bands'));

CREATE OR REPLACE VIEW current_environmental_classification_threshold AS
SELECT
    scheme.classification_scheme_id,
    scheme.version_label,
    scheme.analysis_area_id,
    'fixed_evidence_bands'::TEXT AS method,
    'fixed_temperature_display_bands_and_evidence_backed_canopy_progress_bands'::TEXT
        AS classification_scope,
    scheme.calculated_at,
    threshold.metric_code,
    threshold.source_dataset_version_id,
    CASE WHEN threshold.metric_code = 'heat' THEN 27.0
         WHEN threshold.metric_code = 'canopy' THEN 15.3
         ELSE threshold.lower_threshold END AS lower_threshold,
    CASE WHEN threshold.metric_code = 'heat' THEN 30.0
         WHEN threshold.metric_code = 'canopy' THEN 30.0
         ELSE threshold.upper_threshold END AS upper_threshold,
    threshold.unit,
    threshold.sample_count,
    threshold.low_label,
    threshold.medium_label,
    threshold.high_label,
    threshold.missing_label,
    CASE
        WHEN threshold.metric_code = 'heat' THEN
            'GreenChanger display bands: Low <=27 C, Medium >27 C and <=30 C, High >30 C. Application-defined only; not a BOM heatwave, health-risk or comfort classification.'
        WHEN threshold.metric_code = 'canopy' THEN
            'Canopy progress bands: Low <15.3%, Medium >=15.3% and <30%, High >=30%. The 15.3% value is the official metropolitan Melbourne 2018 tree-canopy baseline and 30% is the Plan for Victoria urban-area target. Progress context only; not proof of property-level compliance, and source imagery spans 2013-2020.'
        ELSE threshold.explanation
    END AS explanation
FROM environmental_classification_scheme AS scheme
JOIN environmental_classification_threshold AS threshold
  USING (classification_scheme_id)
WHERE scheme.status = 'active';

CREATE OR REPLACE FUNCTION refresh_environmental_classifications(
    p_version_label TEXT
)
RETURNS UUID
LANGUAGE plpgsql
AS $function$
DECLARE
    v_scheme_id UUID;
    v_analysis_area_id UUID;
    v_threshold_count INTEGER;
BEGIN
    IF p_version_label IS NULL OR BTRIM(p_version_label) = '' THEN
        RAISE EXCEPTION 'classification version label is required';
    END IF;
    IF EXISTS (
        SELECT 1 FROM environmental_classification_scheme
        WHERE version_label = BTRIM(p_version_label)
    ) THEN
        RAISE EXCEPTION 'classification version % already exists', BTRIM(p_version_label);
    END IF;

    SELECT analysis_area_id
    INTO STRICT v_analysis_area_id
    FROM analysis_area
    WHERE source_area_code = '2GMEL' AND source_year = 2026;

    INSERT INTO environmental_classification_scheme (
        version_label, analysis_area_id, method, classification_scope,
        status, notes
    ) VALUES (
        BTRIM(p_version_label), v_analysis_area_id,
        'fixed_evidence_bands',
        'fixed_temperature_display_bands_and_evidence_backed_canopy_progress_bands',
        'draft',
        'Canopy: Low below the official 15.3% metropolitan Melbourne baseline; Medium from 15.3% to below the 30% Plan for Victoria urban target; High at or above 30%. Temperature retains application-defined 27/30 C display bands. Missing values are Unavailable.'
    )
    RETURNING classification_scheme_id INTO v_scheme_id;

    INSERT INTO environmental_classification_threshold (
        classification_scheme_id, metric_code, source_dataset_version_id,
        lower_threshold, upper_threshold, unit, sample_count, explanation
    )
    SELECT
        v_scheme_id, 'heat', dataset_version_id, 27.0, 30.0,
        'degC_land_surface_temperature', COUNT(*),
        'GreenChanger display bands: Low <=27 C, Medium >27 C and <=30 C, High >30 C. Application-defined only; not a BOM heatwave, health-risk or comfort classification.'
    FROM latest_greater_melbourne_heat_baseline
    WHERE baseline_surface_temperature_c IS NOT NULL
    GROUP BY dataset_version_id;

    INSERT INTO environmental_classification_threshold (
        classification_scheme_id, metric_code, source_dataset_version_id,
        lower_threshold, upper_threshold, unit, sample_count, explanation
    )
    SELECT
        v_scheme_id, 'canopy', dataset_version_id, 15.3, 30.0,
        'percent_neighbourhood_canopy', COUNT(*),
        'Canopy progress bands: Low <15.3%, Medium >=15.3% and <30%, High >=30%. Based on the official metropolitan Melbourne 2018 tree-canopy baseline and Plan for Victoria urban-area target; not proof of property-level compliance.'
    FROM latest_greater_melbourne_canopy_baseline
    WHERE canopy_percentage IS NOT NULL
    GROUP BY dataset_version_id;

    SELECT COUNT(*) INTO v_threshold_count
    FROM environmental_classification_threshold
    WHERE classification_scheme_id = v_scheme_id;

    IF v_threshold_count <> 2 THEN
        RAISE EXCEPTION
            'expected heat and canopy thresholds but calculated % row(s)',
            v_threshold_count;
    END IF;

    UPDATE environmental_classification_scheme
    SET status = 'retired'
    WHERE analysis_area_id = v_analysis_area_id AND status = 'active';

    UPDATE environmental_classification_scheme
    SET status = 'active', calculated_at = CURRENT_TIMESTAMP
    WHERE classification_scheme_id = v_scheme_id;

    RETURN v_scheme_id;
END;
$function$;

COMMENT ON FUNCTION refresh_environmental_classifications(TEXT) IS
    'Creates and activates a versioned fixed-band scheme: temperature uses GreenChanger 27/30 C display bands; canopy uses the official 15.3% metropolitan baseline and 30% Plan for Victoria urban target.';

CREATE OR REPLACE FUNCTION classify_environmental_value(
    p_metric_code TEXT, p_value NUMERIC, p_version_label TEXT DEFAULT NULL
)
RETURNS TEXT
LANGUAGE SQL
STABLE
PARALLEL SAFE
RETURN CASE
    WHEN p_value IS NULL OR p_value::TEXT IN ('NaN', 'Infinity', '-Infinity')
        THEN 'Unavailable'
    WHEN p_metric_code = 'heat' THEN classify_temperature_band(p_value)
    WHEN p_metric_code = 'canopy' THEN classify_canopy_benchmark(p_value)
    ELSE 'Unavailable'
END;

COMMENT ON FUNCTION classify_environmental_value(TEXT, NUMERIC, TEXT) IS
    'Uses fixed GreenChanger 27/30 C display bands for heat and evidence-backed 15.3/30% progress bands for canopy. Missing, non-finite and unknown metrics return Unavailable.';

COMMIT;
