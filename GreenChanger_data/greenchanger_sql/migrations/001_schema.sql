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
    CHECK (
        source_observed_to IS NULL
        OR source_observed_from IS NULL
        OR source_observed_to >= source_observed_from
    )
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
    area_name TEXT NOT NULL,
    area_type TEXT NOT NULL,
    boundary_geometry geometry(MultiPolygon, 7855) NOT NULL,
    area_m2 NUMERIC CHECK (area_m2 IS NULL OR area_m2 > 0),
    support_status TEXT NOT NULL DEFAULT 'supported',
    supported_from DATE,
    supported_to DATE,
    UNIQUE (area_name, area_type)
);

CREATE TABLE IF NOT EXISTS address (
    address_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    source_address_id TEXT,
    full_address TEXT NOT NULL,
    locality_name TEXT,
    postcode TEXT,
    address_location geometry(Point, 7855) NOT NULL,
    UNIQUE (dataset_version_id, source_address_id)
);

CREATE TABLE IF NOT EXISTS parcel (
    parcel_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    source_parcel_id TEXT NOT NULL,
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
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    retired_at TIMESTAMPTZ,
    UNIQUE (model_name, version_label)
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
    result_value NUMERIC NOT NULL,
    output_unit TEXT NOT NULL,
    confidence_level TEXT CHECK (confidence_level IN ('low', 'medium', 'high')),
    calculation_details JSONB,
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
CREATE INDEX IF NOT EXISTS idx_vegetation_geometry
    ON vegetation_observation USING GIST(observation_geometry);
CREATE INDEX IF NOT EXISTS idx_canopy_geometry
    ON canopy_patch USING GIST(canopy_geometry);
CREATE INDEX IF NOT EXISTS idx_tree_location
    ON urban_tree USING GIST(tree_location);

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

COMMIT;
