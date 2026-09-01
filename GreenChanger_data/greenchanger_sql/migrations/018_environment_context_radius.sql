BEGIN;

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

COMMIT;
