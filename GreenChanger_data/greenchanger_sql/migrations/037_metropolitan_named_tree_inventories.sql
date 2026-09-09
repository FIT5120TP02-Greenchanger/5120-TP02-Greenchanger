BEGIN;

ALTER TABLE named_tree_inventory
    ADD COLUMN IF NOT EXISTS inventory_source_key TEXT,
    ADD COLUMN IF NOT EXISTS municipality TEXT,
    ADD COLUMN IF NOT EXISTS taxonomic_precision TEXT,
    ADD COLUMN IF NOT EXISTS height_m NUMERIC,
    ADD COLUMN IF NOT EXISTS height_min_m NUMERIC,
    ADD COLUMN IF NOT EXISTS height_max_m NUMERIC,
    ADD COLUMN IF NOT EXISTS canopy_width_m NUMERIC,
    ADD COLUMN IF NOT EXISTS canopy_width_min_m NUMERIC,
    ADD COLUMN IF NOT EXISTS canopy_width_max_m NUMERIC,
    ADD COLUMN IF NOT EXISTS canopy_width_ew_m NUMERIC,
    ADD COLUMN IF NOT EXISTS canopy_width_ns_m NUMERIC,
    ADD COLUMN IF NOT EXISTS dbh_min_cm NUMERIC,
    ADD COLUMN IF NOT EXISTS dbh_max_cm NUMERIC,
    ADD COLUMN IF NOT EXISTS health_status TEXT,
    ADD COLUMN IF NOT EXISTS structure_status TEXT,
    ADD COLUMN IF NOT EXISTS address TEXT,
    ADD COLUMN IF NOT EXISTS source_observed_on DATE;

UPDATE named_tree_inventory
SET inventory_source_key = 'city_melbourne',
    municipality = 'City of Melbourne',
    taxonomic_precision = CASE
        WHEN scientific_name IS NOT NULL THEN 'species'
        WHEN common_name IS NOT NULL THEN 'common_name'
        ELSE NULL
    END
WHERE inventory_source_key IS NULL;

ALTER TABLE named_tree_inventory
    ALTER COLUMN inventory_source_key SET NOT NULL,
    ALTER COLUMN municipality SET NOT NULL,
    ADD CONSTRAINT named_tree_height_positive CHECK (
        height_m IS NULL OR height_m > 0
    ),
    ADD CONSTRAINT named_tree_height_range_valid CHECK (
        (height_min_m IS NULL OR height_min_m > 0)
        AND (height_max_m IS NULL OR height_max_m > 0)
        AND (height_min_m IS NULL OR height_max_m IS NULL OR height_min_m <= height_max_m)
    ),
    ADD CONSTRAINT named_tree_canopy_width_positive CHECK (
        (canopy_width_m IS NULL OR canopy_width_m > 0)
        AND (canopy_width_ew_m IS NULL OR canopy_width_ew_m > 0)
        AND (canopy_width_ns_m IS NULL OR canopy_width_ns_m > 0)
    ),
    ADD CONSTRAINT named_tree_canopy_range_valid CHECK (
        (canopy_width_min_m IS NULL OR canopy_width_min_m > 0)
        AND (canopy_width_max_m IS NULL OR canopy_width_max_m > 0)
        AND (canopy_width_min_m IS NULL OR canopy_width_max_m IS NULL
             OR canopy_width_min_m <= canopy_width_max_m)
    ),
    ADD CONSTRAINT named_tree_dbh_range_valid CHECK (
        (dbh_min_cm IS NULL OR dbh_min_cm > 0)
        AND (dbh_max_cm IS NULL OR dbh_max_cm > 0)
        AND (dbh_min_cm IS NULL OR dbh_max_cm IS NULL OR dbh_min_cm <= dbh_max_cm)
    );

CREATE INDEX idx_named_tree_inventory_municipality
    ON named_tree_inventory (municipality, dataset_version_id, quality_status);
CREATE INDEX idx_named_tree_inventory_source
    ON named_tree_inventory (inventory_source_key, dataset_version_id);

CREATE OR REPLACE VIEW latest_metropolitan_named_tree_inventory AS
WITH ranked_versions AS (
    SELECT
        version.dataset_version_id,
        source.source_name,
        source.publisher,
        source.source_url,
        source.licence,
        ROW_NUMBER() OVER (
            PARTITION BY version.source_id
            ORDER BY version.extracted_at DESC, version.dataset_version_id DESC
        ) AS version_rank
    FROM dataset_version AS version
    JOIN dataset_source AS source USING (source_id)
    WHERE source.source_category = 'tree_inventory'
      AND version.integration_status = 'integrated'
      AND version.publication_status = 'application_ready'
)
SELECT
    tree.*,
    version.source_name,
    version.publisher,
    version.source_url,
    version.licence,
    'Council-maintained public tree inventory; not inferred from Vicmap Tree Urban'::TEXT
        AS name_status
FROM named_tree_inventory AS tree
JOIN ranked_versions AS version USING (dataset_version_id)
WHERE version.version_rank = 1
  AND tree.quality_status = 'passed';

CREATE OR REPLACE FUNCTION get_metropolitan_named_tree_context(
    p_longitude DOUBLE PRECISION,
    p_latitude DOUBLE PRECISION,
    p_radius_m DOUBLE PRECISION DEFAULT 100.0,
    p_result_limit INTEGER DEFAULT 100
)
RETURNS TABLE (
    named_tree_id UUID,
    source_tree_id TEXT,
    municipality TEXT,
    common_name TEXT,
    scientific_name TEXT,
    display_name TEXT,
    taxonomic_precision TEXT,
    distance_m NUMERIC,
    diameter_breast_height_cm NUMERIC,
    height_m NUMERIC,
    height_min_m NUMERIC,
    height_max_m NUMERIC,
    canopy_width_m NUMERIC,
    canopy_width_min_m NUMERIC,
    canopy_width_max_m NUMERIC,
    health_status TEXT,
    source_observed_on DATE,
    geometry_geojson JSONB,
    source TEXT,
    licence TEXT,
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
    v_point := ST_Transform(
        ST_SetSRID(ST_MakePoint(p_longitude, p_latitude), 4326), 7855
    );

    RETURN QUERY
    SELECT
        tree.named_tree_id,
        tree.source_tree_id,
        tree.municipality,
        tree.common_name,
        tree.scientific_name,
        tree.display_name,
        tree.taxonomic_precision,
        ROUND(ST_Distance(tree.tree_location, v_point)::NUMERIC, 2),
        tree.diameter_breast_height_cm,
        tree.height_m,
        tree.height_min_m,
        tree.height_max_m,
        tree.canopy_width_m,
        tree.canopy_width_min_m,
        tree.canopy_width_max_m,
        tree.health_status,
        tree.source_observed_on,
        ST_AsGeoJSON(ST_Transform(tree.tree_location, 4326), 6)::JSONB,
        tree.source_name,
        tree.licence,
        'observed_council_inventory'::TEXT,
        'Council inventories cover maintained public trees, not every private tree. Fields and survey dates differ by council; names are not inferred for Vicmap points.'::TEXT
    FROM latest_metropolitan_named_tree_inventory AS tree
    WHERE ST_DWithin(tree.tree_location, v_point, p_radius_m)
    ORDER BY tree.tree_location <-> v_point, tree.named_tree_id
    LIMIT p_result_limit;
END;
$function$;

COMMENT ON VIEW latest_metropolitan_named_tree_inventory IS
    'Latest application-ready version of each source-labelled metropolitan council tree inventory.';
COMMENT ON FUNCTION get_metropolitan_named_tree_context(
    DOUBLE PRECISION, DOUBLE PRECISION, DOUBLE PRECISION, INTEGER
) IS
    'Returns bounded nearby named council trees while preserving source, licence, observation date, dimensions and limitations.';

COMMIT;
