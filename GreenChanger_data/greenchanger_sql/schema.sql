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
    scheme.method,
    scheme.classification_scope,
    scheme.calculated_at,
    threshold.metric_code,
    threshold.source_dataset_version_id,
    threshold.lower_threshold,
    threshold.upper_threshold,
    threshold.unit,
    threshold.sample_count,
    threshold.low_label,
    threshold.medium_label,
    threshold.high_label,
    threshold.missing_label,
    threshold.explanation
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

CREATE OR REPLACE FUNCTION classify_environmental_value(
    p_metric_code TEXT, p_value NUMERIC, p_version_label TEXT DEFAULT NULL
)
RETURNS TEXT
LANGUAGE SQL
STABLE
PARALLEL SAFE
RETURN CASE
    WHEN p_value IS NULL THEN 'Unavailable'
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

COMMIT;
