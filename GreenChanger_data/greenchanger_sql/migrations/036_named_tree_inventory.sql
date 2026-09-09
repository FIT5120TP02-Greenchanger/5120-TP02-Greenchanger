BEGIN;

ALTER TABLE species_profile
    ADD COLUMN IF NOT EXISTS genus TEXT,
    ADD COLUMN IF NOT EXISTS family TEXT;

CREATE TABLE named_tree_inventory (
    named_tree_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    source_tree_id TEXT NOT NULL,
    species_id UUID REFERENCES species_profile(species_id),
    common_name TEXT,
    scientific_name TEXT,
    display_name TEXT NOT NULL,
    genus TEXT,
    family TEXT,
    diameter_breast_height_cm NUMERIC CHECK (
        diameter_breast_height_cm IS NULL OR diameter_breast_height_cm > 0
    ),
    year_planted INTEGER CHECK (
        year_planted IS NULL OR year_planted BETWEEN 1700 AND 2200
    ),
    date_planted DATE,
    age_description TEXT,
    useful_life_expectancy TEXT,
    useful_life_expectancy_years INTEGER CHECK (
        useful_life_expectancy_years IS NULL OR useful_life_expectancy_years >= 0
    ),
    precinct TEXT,
    located_in TEXT,
    tree_location geometry(Point, 7855) NOT NULL,
    quality_status TEXT NOT NULL CHECK (quality_status IN ('passed', 'failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (dataset_version_id, source_tree_id),
    CHECK (common_name IS NOT NULL OR scientific_name IS NOT NULL)
);

CREATE INDEX idx_named_tree_inventory_location
    ON named_tree_inventory USING GIST (tree_location);
CREATE INDEX idx_named_tree_inventory_version_quality
    ON named_tree_inventory (dataset_version_id, quality_status);
CREATE INDEX idx_named_tree_inventory_species
    ON named_tree_inventory (species_id);
CREATE INDEX idx_named_tree_inventory_display_name
    ON named_tree_inventory (UPPER(display_name) text_pattern_ops);

CREATE OR REPLACE VIEW latest_city_melbourne_named_tree_inventory AS
WITH latest_version AS (
    SELECT version.dataset_version_id
    FROM dataset_version AS version
    JOIN dataset_source AS source USING (source_id)
    WHERE source.source_name = 'Trees, with species and dimensions (Urban Forest)'
      AND source.publisher = 'City of Melbourne'
      AND version.integration_status = 'integrated'
      AND version.publication_status = 'application_ready'
    ORDER BY version.extracted_at DESC, version.dataset_version_id DESC
    LIMIT 1
)
SELECT
    tree.*,
    'City of Melbourne municipality only'::TEXT AS geographic_scope,
    'Council inventory name; not inferred from Vicmap Tree Urban'::TEXT AS name_status,
    'CC BY 4.0'::TEXT AS licence
FROM named_tree_inventory AS tree
JOIN latest_version USING (dataset_version_id)
WHERE tree.quality_status = 'passed';

CREATE OR REPLACE FUNCTION get_named_tree_context(
    p_longitude DOUBLE PRECISION,
    p_latitude DOUBLE PRECISION,
    p_radius_m DOUBLE PRECISION DEFAULT 100.0,
    p_result_limit INTEGER DEFAULT 100
)
RETURNS TABLE (
    named_tree_id UUID,
    source_tree_id TEXT,
    common_name TEXT,
    scientific_name TEXT,
    display_name TEXT,
    distance_m NUMERIC,
    diameter_breast_height_cm NUMERIC,
    year_planted INTEGER,
    precinct TEXT,
    geometry_geojson JSONB,
    source TEXT,
    status TEXT,
    limitation TEXT
)
LANGUAGE plpgsql
STABLE
AS $function$
DECLARE
    v_point geometry(Point, 7855);
BEGIN
    IF p_radius_m <= 0 OR p_radius_m > 2000 THEN
        RAISE EXCEPTION 'radius_m must be greater than 0 and no more than 2000';
    END IF;
    IF p_result_limit <= 0 OR p_result_limit > 2000 THEN
        RAISE EXCEPTION 'result_limit must be between 1 and 2000';
    END IF;
    v_point := ST_Transform(ST_SetSRID(ST_MakePoint(p_longitude, p_latitude), 4326), 7855);

    RETURN QUERY
    SELECT
        tree.named_tree_id,
        tree.source_tree_id,
        tree.common_name,
        tree.scientific_name,
        tree.display_name,
        ROUND(ST_Distance(tree.tree_location, v_point)::NUMERIC, 2),
        tree.diameter_breast_height_cm,
        tree.year_planted,
        tree.precinct,
        ST_AsGeoJSON(ST_Transform(tree.tree_location, 4326), 6)::JSONB,
        'City of Melbourne Trees, with species and dimensions (Urban Forest)'::TEXT,
        'observed_council_inventory_name'::TEXT,
        'Coverage is limited to the City of Melbourne municipality. This record is not joined to a Vicmap Tree Urban point.'::TEXT
    FROM latest_city_melbourne_named_tree_inventory AS tree
    WHERE ST_DWithin(tree.tree_location, v_point, p_radius_m)
    ORDER BY tree.tree_location <-> v_point, tree.named_tree_id
    LIMIT p_result_limit;
END;
$function$;

COMMENT ON TABLE named_tree_inventory IS
    'Source-specific City of Melbourne named-tree observations kept separate from machine-derived Vicmap Tree Urban points.';
COMMENT ON VIEW latest_city_melbourne_named_tree_inventory IS
    'Latest application-ready City of Melbourne named-tree inventory. It must not be used to infer names for nearby Vicmap points.';

COMMIT;
