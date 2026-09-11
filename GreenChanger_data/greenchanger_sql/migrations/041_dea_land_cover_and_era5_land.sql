BEGIN;

CREATE TABLE dea_land_cover_observation (
    dea_land_cover_observation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    cell_key TEXT NOT NULL,
    observed_year SMALLINT NOT NULL CHECK (observed_year BETWEEN 1988 AND 2100),
    observed_on DATE NOT NULL,
    observation_geometry geometry(Polygon, 7855) NOT NULL,
    dominant_level3_code SMALLINT NOT NULL CHECK (
        dominant_level3_code IN (111, 112, 124, 215, 216, 220)
    ),
    dominant_level3_name TEXT NOT NULL,
    cultivated_vegetation_pct NUMERIC(7, 4) NOT NULL CHECK (
        cultivated_vegetation_pct BETWEEN 0 AND 100
    ),
    natural_terrestrial_vegetation_pct NUMERIC(7, 4) NOT NULL CHECK (
        natural_terrestrial_vegetation_pct BETWEEN 0 AND 100
    ),
    natural_aquatic_vegetation_pct NUMERIC(7, 4) NOT NULL CHECK (
        natural_aquatic_vegetation_pct BETWEEN 0 AND 100
    ),
    artificial_surface_pct NUMERIC(7, 4) NOT NULL CHECK (
        artificial_surface_pct BETWEEN 0 AND 100
    ),
    natural_bare_surface_pct NUMERIC(7, 4) NOT NULL CHECK (
        natural_bare_surface_pct BETWEEN 0 AND 100
    ),
    water_pct NUMERIC(7, 4) NOT NULL CHECK (water_pct BETWEEN 0 AND 100),
    valid_data_pct NUMERIC(7, 4) NOT NULL CHECK (valid_data_pct > 0 AND valid_data_pct <= 100),
    source_resolution_m NUMERIC NOT NULL DEFAULT 30 CHECK (source_resolution_m > 0),
    aggregation_grid_m NUMERIC NOT NULL DEFAULT 500 CHECK (aggregation_grid_m > 0),
    calculation_method TEXT NOT NULL DEFAULT 'binary_class_fraction_average_v1',
    quality_status TEXT NOT NULL DEFAULT 'passed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (dataset_version_id, cell_key)
);

CREATE INDEX idx_dea_land_cover_version_year
    ON dea_land_cover_observation(dataset_version_id, observed_year);
CREATE INDEX idx_dea_land_cover_dominant_class
    ON dea_land_cover_observation(dominant_level3_code, observed_year);
CREATE INDEX idx_dea_land_cover_geometry
    ON dea_land_cover_observation USING GIST(observation_geometry);

CREATE TABLE era5_land_daily_observation (
    era5_land_daily_observation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    cell_key TEXT NOT NULL,
    observed_on DATE NOT NULL,
    observation_location geometry(Point, 7855) NOT NULL,
    air_temperature_mean_c NUMERIC,
    air_temperature_min_c NUMERIC,
    air_temperature_max_c NUMERIC,
    precipitation_total_mm NUMERIC CHECK (
        precipitation_total_mm IS NULL OR precipitation_total_mm >= 0
    ),
    soil_water_layer_1_mean_m3_m3 NUMERIC CHECK (
        soil_water_layer_1_mean_m3_m3 IS NULL
        OR soil_water_layer_1_mean_m3_m3 BETWEEN 0 AND 1
    ),
    surface_solar_radiation_total_mj_m2 NUMERIC CHECK (
        surface_solar_radiation_total_mj_m2 IS NULL
        OR surface_solar_radiation_total_mj_m2 >= 0
    ),
    wind_speed_mean_ms NUMERIC CHECK (
        wind_speed_mean_ms IS NULL OR wind_speed_mean_ms >= 0
    ),
    hour_count SMALLINT NOT NULL CHECK (hour_count BETWEEN 1 AND 24),
    source_spatial_resolution_m NUMERIC NOT NULL DEFAULT 9000 CHECK (
        source_spatial_resolution_m > 0
    ),
    temporal_aggregation TEXT NOT NULL DEFAULT 'daily',
    quality_status TEXT NOT NULL DEFAULT 'passed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        air_temperature_min_c IS NULL OR air_temperature_max_c IS NULL
        OR air_temperature_min_c <= air_temperature_max_c
    ),
    UNIQUE (dataset_version_id, cell_key, observed_on)
);

CREATE INDEX idx_era5_land_version_date
    ON era5_land_daily_observation(dataset_version_id, observed_on);
CREATE INDEX idx_era5_land_cell_date
    ON era5_land_daily_observation(cell_key, observed_on DESC);
CREATE INDEX idx_era5_land_location
    ON era5_land_daily_observation USING GIST(observation_location);

CREATE OR REPLACE VIEW latest_dea_land_cover AS
WITH current_version AS (
    SELECT version.dataset_version_id
    FROM dataset_version AS version
    JOIN dataset_source AS source USING (source_id)
    WHERE source.source_name = 'DEA Land Cover (Landsat)'
      AND source.publisher = 'Geoscience Australia'
      AND version.integration_status = 'integrated'
      AND version.quality_status IN ('passed', 'passed_with_limitations')
    ORDER BY version.source_observed_to DESC NULLS LAST,
             version.extracted_at DESC, version.dataset_version_id DESC
    LIMIT 1
)
SELECT observation.*
FROM dea_land_cover_observation AS observation
JOIN current_version USING (dataset_version_id)
WHERE observation.quality_status = 'passed';

CREATE OR REPLACE VIEW latest_era5_land_daily AS
WITH current_version AS (
    SELECT version.dataset_version_id
    FROM dataset_version AS version
    JOIN dataset_source AS source USING (source_id)
    WHERE source.source_name = 'ERA5-Land hourly data from 1950 to present'
      AND source.publisher = 'Copernicus Climate Change Service / ECMWF'
      AND version.integration_status = 'integrated'
      AND version.quality_status IN ('passed', 'passed_with_limitations')
    ORDER BY version.source_observed_to DESC NULLS LAST,
             version.extracted_at DESC, version.dataset_version_id DESC
    LIMIT 1
)
SELECT observation.*
FROM era5_land_daily_observation AS observation
JOIN current_version USING (dataset_version_id)
WHERE observation.quality_status = 'passed';

COMMENT ON TABLE dea_land_cover_observation IS
    'Annual 30 m DEA Level-3 land-cover classes aggregated to 500 m Melbourne modelling cells; not property-scale canopy.';
COMMENT ON TABLE era5_land_daily_observation IS
    'Daily summaries of hourly approximately 9 km ERA5-Land reanalysis grid points; modelled weather controls, not BOM station observations.';

COMMIT;
