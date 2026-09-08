BEGIN;

ALTER TABLE dataset_source
    ADD COLUMN licence_status TEXT NOT NULL DEFAULT 'review_required' CHECK (
        licence_status IN ('open_confirmed', 'public_domain', 'review_required', 'restricted')
    );

UPDATE dataset_source
SET licence = 'Creative Commons Attribution 4.0 International',
    licence_status = 'open_confirmed'
WHERE source_name = 'Vicmap Property'
  AND publisher = 'Victorian Government';

UPDATE dataset_source
SET licence = 'Creative Commons Attribution',
    licence_status = 'open_confirmed'
WHERE source_name = 'Tree Canopies 2021 (Urban Forest)'
  AND publisher = 'City of Melbourne';

UPDATE dataset_source
SET licence = 'United States public domain',
    licence_status = 'public_domain'
WHERE source_name = 'USGS Landsat Collection 2 Surface Temperature'
  AND publisher = 'United States Geological Survey';

INSERT INTO dataset_source (
    source_name, publisher, source_url, licence, licence_status,
    source_category, geographic_coverage, access_method, update_frequency
)
VALUES
    (
        'Trees, with species and dimensions (Urban Forest)',
        'City of Melbourne',
        'https://data.melbourne.vic.gov.au/explore/dataset/trees-with-species-and-dimensions-urban-forest/',
        'Creative Commons Attribution', 'open_confirmed', 'tree_inventory',
        'City of Melbourne municipality', 'Open Data Portal API and download',
        'portal update'
    ),
    (
        'Change in Vegetation Cover in Metropolitan Melbourne between 2014 and 2018',
        'Victorian Government Department of Transport and Planning',
        'https://discover.data.vic.gov.au/dataset/change-in-vegetation-cover-in-metropolitan-melbourne-between-2014-and-2018',
        'Creative Commons Attribution 4.0 International', 'open_confirmed',
        'vegetation_change', 'Metropolitan Melbourne comparison extent',
        'SHP, GDB, TAB, MIF, DWG and DXF download',
        'source metadata states annual; observed product is 2014-2018'
    ),
    (
        'DEA Land Cover (Landsat)', 'Geoscience Australia',
        'https://knowledge.dea.ga.gov.au/data/product/dea-land-cover-landsat/',
        'Creative Commons Attribution 4.0 International', 'open_confirmed',
        'land_cover', 'Australia', 'AWS, NCI, OGC web services and download',
        'annual'
    ),
    (
        'ERA5-Land hourly data from 1950 to present',
        'Copernicus Climate Change Service / ECMWF',
        'https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land',
        'Creative Commons Attribution 4.0 International', 'open_confirmed',
        'weather_control', 'Global; subset to Melbourne',
        'Copernicus Climate Data Store API, STAC and download', 'daily'
    ),
    (
        'Identifying the mechanisms by which irrigation can cool urban green spaces in summer',
        'Zenodo research record by Cheung et al.',
        'https://zenodo.org/records/10972539',
        'Record-level licence not displayed in the current Rights field',
        'review_required', 'experimental_garden_cooling', 'Burnley, Melbourne',
        'Zenodo CSV download', 'static research deposit'
    )
ON CONFLICT (source_name, publisher) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    licence = EXCLUDED.licence,
    licence_status = EXCLUDED.licence_status,
    source_category = EXCLUDED.source_category,
    geographic_coverage = EXCLUDED.geographic_coverage,
    access_method = EXCLUDED.access_method,
    update_frequency = EXCLUDED.update_frequency;

CREATE TABLE predictive_model_specification (
    model_code TEXT PRIMARY KEY,
    model_version_id UUID NOT NULL UNIQUE REFERENCES model_version(model_version_id),
    target_metric TEXT NOT NULL,
    output_metric TEXT NOT NULL,
    training_grain TEXT NOT NULL,
    model_status TEXT NOT NULL CHECK (
        model_status IN (
            'blocked_licence_review', 'training_data_not_prepared',
            'training_data_prepared', 'validation_in_progress', 'validated', 'retired'
        )
    ),
    feature_contract JSONB NOT NULL,
    validation_plan TEXT NOT NULL,
    limitations TEXT NOT NULL,
    precise_after_temperature_allowed BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE predictive_model_source (
    model_code TEXT NOT NULL REFERENCES predictive_model_specification(model_code),
    source_id UUID NOT NULL REFERENCES dataset_source(source_id),
    source_role TEXT NOT NULL,
    required_for_training BOOLEAN NOT NULL,
    training_use_allowed BOOLEAN NOT NULL,
    licence_decision TEXT NOT NULL,
    PRIMARY KEY (model_code, source_id)
);

WITH models (
    model_code, model_name, target_metric, output_metric, training_grain,
    model_status, features, validation_plan, limitations, temperature_metric
) AS (
    VALUES
        (
            'tree_canopy_growth', 'Tree canopy growth model',
            'future_canopy_area_m2', 'expected_canopy_range_m2',
            'individual tree at an explicit future horizon',
            'training_data_not_prepared',
            '["tree_age_years","species","current_canopy_area_m2","height_m","diameter_cm","site_context","maturity_horizon_years"]'::jsonb,
            'Group spatial hold-out by precinct and temporal hold-out by observation year; report MAE and empirical interval coverage by species.',
            'City of Melbourne training coverage is not representative of all residential Melbourne. Do not extrapolate unsupported species or horizons.',
            NULL
        ),
        (
            'melbourne_canopy_change', 'Melbourne-wide canopy change model',
            'vegetation_cover_change_percentage_points_2014_2018',
            'expected_canopy_change_range_percentage_points',
            'ABS 2016 Mesh Block or consistently aligned analysis cell',
            'training_data_not_prepared',
            '["baseline_tree_cover_pct","land_use_class","parcel_area_summary","impervious_cover_pct","weather_summary","location"]'::jsonb,
            'Spatial block cross-validation with complete suburbs or LGAs held out; report MAE and interval coverage, including growth-area error slices.',
            'The target records net vegetation change, not the causal effect of a particular planting action.',
            NULL
        ),
        (
            'cooling_association', 'Vegetation and surface-cooling association model',
            'landsat_land_surface_temperature_c',
            'conditional_land_surface_temperature_range_c',
            'spatial cell and Landsat acquisition time',
            'training_data_not_prepared',
            '["tree_cover_pct","vegetation_cover_change_pct","land_cover_class","air_temperature_control_c","rainfall_control_mm","solar_radiation_control","cloud_quality","acquisition_time"]'::jsonb,
            'Hold out complete spatial blocks and acquisition dates; compare against a weather-only baseline and report MAE, bias and interval coverage.',
            'Association only: not causal intervention cooling and not resident-level air temperature.',
            'land_surface_temperature'
        ),
        (
            'garden_cooling', 'Irrigated garden cooling model',
            'irrigated_minus_unirrigated_surface_energy_and_microclimate_response',
            'experimental_garden_cooling_range',
            'Burnley experimental plot and hour',
            'blocked_licence_review',
            '["irrigation_mm_per_day","soil_moisture","background_air_temperature_c","solar_radiation","wind","hour"]'::jsonb,
            'Train on the 2021 experiment and hold out the 2022 experiment; report treatment-effect range and uncertainty by weather condition.',
            'Burnley irrigated-turf experiment only. Do not use until the record-level licence is confirmed.',
            NULL
        )
), inserted_versions AS (
    INSERT INTO model_version (
        model_name, version_label, method_description, validation_status,
        validation_summary, output_precision, temperature_metric, spatial_scope,
        uncertainty_method, evidence_reviewed_at
    )
    SELECT
        model_name, 'separate-environmental-models-v1',
        'Independent model contract for ' || model_code || '; no estimator is fitted by this migration.',
        'draft', 'Training data preparation and held-out validation are incomplete.',
        'suppressed', temperature_metric, training_grain,
        'Prediction intervals must be measured on held-out spatial and temporal data.',
        DATE '2026-09-05'
    FROM models
    ON CONFLICT (model_name, version_label) DO UPDATE SET
        method_description = EXCLUDED.method_description,
        validation_status = EXCLUDED.validation_status,
        validation_summary = EXCLUDED.validation_summary,
        output_precision = EXCLUDED.output_precision,
        temperature_metric = EXCLUDED.temperature_metric,
        spatial_scope = EXCLUDED.spatial_scope,
        uncertainty_method = EXCLUDED.uncertainty_method,
        evidence_reviewed_at = EXCLUDED.evidence_reviewed_at
    RETURNING model_version_id, model_name
)
INSERT INTO predictive_model_specification (
    model_code, model_version_id, target_metric, output_metric, training_grain,
    model_status, feature_contract, validation_plan, limitations
)
SELECT
    models.model_code, versions.model_version_id, models.target_metric,
    models.output_metric, models.training_grain, models.model_status,
    models.features, models.validation_plan, models.limitations
FROM models
JOIN inserted_versions AS versions USING (model_name)
ON CONFLICT (model_code) DO UPDATE SET
    model_version_id = EXCLUDED.model_version_id,
    target_metric = EXCLUDED.target_metric,
    output_metric = EXCLUDED.output_metric,
    training_grain = EXCLUDED.training_grain,
    model_status = EXCLUDED.model_status,
    feature_contract = EXCLUDED.feature_contract,
    validation_plan = EXCLUDED.validation_plan,
    limitations = EXCLUDED.limitations,
    precise_after_temperature_allowed = FALSE,
    updated_at = CURRENT_TIMESTAMP;

WITH source_roles (model_code, source_name, publisher, source_role, required) AS (
    VALUES
        ('tree_canopy_growth', 'Trees, with species and dimensions (Urban Forest)', 'City of Melbourne', 'tree attributes and planting year', TRUE),
        ('tree_canopy_growth', 'Tree Canopies 2021 (Urban Forest)', 'City of Melbourne', 'observed canopy target', TRUE),
        ('tree_canopy_growth', 'Vicmap Property', 'Victorian Government', 'parcel and site context', FALSE),
        ('melbourne_canopy_change', 'Change in Vegetation Cover in Metropolitan Melbourne between 2014 and 2018', 'Victorian Government Department of Transport and Planning', 'Melbourne-wide change target', TRUE),
        ('melbourne_canopy_change', 'Vicmap Property', 'Victorian Government', 'parcel characteristics', TRUE),
        ('melbourne_canopy_change', 'DEA Land Cover (Landsat)', 'Geoscience Australia', 'land-cover covariates and longer-term context', FALSE),
        ('melbourne_canopy_change', 'ERA5-Land hourly data from 1950 to present', 'Copernicus Climate Change Service / ECMWF', 'openly licensed historical weather controls', TRUE),
        ('cooling_association', 'USGS Landsat Collection 2 Surface Temperature', 'United States Geological Survey', 'land-surface-temperature target', TRUE),
        ('cooling_association', 'Change in Vegetation Cover in Metropolitan Melbourne between 2014 and 2018', 'Victorian Government Department of Transport and Planning', 'vegetation predictors', TRUE),
        ('cooling_association', 'ERA5-Land hourly data from 1950 to present', 'Copernicus Climate Change Service / ECMWF', 'openly licensed historical weather controls', TRUE),
        ('cooling_association', 'BOM Melbourne station observations', 'Bureau of Meteorology', 'optional observation cross-check subject to feed-specific licence', FALSE),
        ('garden_cooling', 'Identifying the mechanisms by which irrigation can cool urban green spaces in summer', 'Zenodo research record by Cheung et al.', 'paired irrigated and unirrigated experimental observations', TRUE)
)
INSERT INTO predictive_model_source (
    model_code, source_id, source_role, required_for_training,
    training_use_allowed, licence_decision
)
SELECT
    roles.model_code, source.source_id, roles.source_role, roles.required,
    source.licence_status IN ('open_confirmed', 'public_domain'),
    CASE
        WHEN source.licence_status IN ('open_confirmed', 'public_domain')
            THEN source.licence
        ELSE 'Blocked until a source-specific open reuse licence is documented.'
    END
FROM source_roles AS roles
JOIN dataset_source AS source
  ON source.source_name = roles.source_name
 AND source.publisher = roles.publisher
ON CONFLICT (model_code, source_id) DO UPDATE SET
    source_role = EXCLUDED.source_role,
    required_for_training = EXCLUDED.required_for_training,
    training_use_allowed = EXCLUDED.training_use_allowed,
    licence_decision = EXCLUDED.licence_decision;

CREATE VIEW current_predictive_model_contract AS
SELECT
    specification.model_code,
    model.model_name,
    model.version_label,
    specification.target_metric,
    specification.output_metric,
    specification.training_grain,
    specification.model_status,
    model.validation_status,
    model.output_precision,
    specification.precise_after_temperature_allowed,
    specification.feature_contract,
    specification.validation_plan,
    specification.limitations,
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'source_name', source.source_name,
                'source_role', link.source_role,
                'required', link.required_for_training,
                'licence', source.licence,
                'licence_status', source.licence_status,
                'training_use_allowed', link.training_use_allowed
            ) ORDER BY source.source_name
        ) FILTER (WHERE source.source_id IS NOT NULL),
        '[]'::jsonb
    ) AS source_contract
FROM predictive_model_specification AS specification
JOIN model_version AS model USING (model_version_id)
LEFT JOIN predictive_model_source AS link USING (model_code)
LEFT JOIN dataset_source AS source USING (source_id)
GROUP BY specification.model_code, model.model_name, model.version_label,
         specification.target_metric, specification.output_metric,
         specification.training_grain, specification.model_status,
         model.validation_status, model.output_precision,
         specification.precise_after_temperature_allowed,
         specification.feature_contract, specification.validation_plan,
         specification.limitations;

COMMENT ON VIEW current_predictive_model_contract IS
    'Four separate, suppressed model contracts. This view does not represent fitted or validated predictions.';

COMMIT;
