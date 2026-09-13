BEGIN;

INSERT INTO dataset_source (
    source_name, publisher, source_url, licence, licence_status,
    source_category, geographic_coverage, access_method, update_frequency
)
VALUES (
    'Vicmap Admin - Local Government Area Polygon Aligned to Property',
    'Department of Transport and Planning',
    'https://discover.data.vic.gov.au/dataset/vicmap-admin-local-government-area-lga-polygon-aligned-to-property',
    'Creative Commons Attribution 4.0 International', 'open_confirmed',
    'administrative_boundary', 'Victoria',
    'Official Vicmap Admin ArcGIS REST API or spatial download', 'weekly REST service'
)
ON CONFLICT (source_name, publisher) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    licence = EXCLUDED.licence,
    licence_status = EXCLUDED.licence_status,
    source_category = EXCLUDED.source_category,
    geographic_coverage = EXCLUDED.geographic_coverage,
    access_method = EXCLUDED.access_method,
    update_frequency = EXCLUDED.update_frequency;

CREATE TABLE local_government_area (
    local_government_area_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    source_feature_id TEXT NOT NULL,
    lga_code TEXT NOT NULL,
    lga_name TEXT NOT NULL,
    lga_official_name TEXT NOT NULL,
    abs_lga_code TEXT,
    gazettal_registration TEXT,
    boundary_geometry geometry(MultiPolygon, 7855) NOT NULL,
    area_m2 NUMERIC NOT NULL CHECK (area_m2 > 0),
    geometry_repaired BOOLEAN NOT NULL DEFAULT FALSE,
    quality_status TEXT NOT NULL DEFAULT 'passed' CHECK (
        quality_status IN ('passed', 'failed')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (dataset_version_id, lga_code)
);

CREATE INDEX idx_local_government_area_geometry
    ON local_government_area USING GIST(boundary_geometry);
CREATE INDEX idx_local_government_area_code_version
    ON local_government_area(lga_code, dataset_version_id);
CREATE INDEX idx_local_government_area_abs_code
    ON local_government_area(abs_lga_code) WHERE abs_lga_code IS NOT NULL;

CREATE TABLE council_species_guidance (
    council_species_guidance_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version_id UUID NOT NULL REFERENCES dataset_version(dataset_version_id),
    source_row_number BIGINT NOT NULL,
    lga_code TEXT NOT NULL,
    species_id UUID REFERENCES species_profile(species_id),
    scientific_name TEXT,
    common_name TEXT,
    mature_size_class TEXT CHECK (
        mature_size_class IS NULL OR mature_size_class IN ('small', 'medium', 'large')
    ),
    mature_height_min_m NUMERIC CHECK (
        mature_height_min_m IS NULL OR mature_height_min_m > 0
    ),
    mature_height_max_m NUMERIC CHECK (
        mature_height_max_m IS NULL OR mature_height_max_m > 0
    ),
    mature_canopy_width_min_m NUMERIC CHECK (
        mature_canopy_width_min_m IS NULL OR mature_canopy_width_min_m > 0
    ),
    mature_canopy_width_max_m NUMERIC CHECK (
        mature_canopy_width_max_m IS NULL OR mature_canopy_width_max_m > 0
    ),
    minimum_planting_area_m2 NUMERIC CHECK (
        minimum_planting_area_m2 IS NULL OR minimum_planting_area_m2 > 0
    ),
    sunlight_requirement TEXT,
    water_need_class TEXT,
    root_risk_class TEXT,
    site_requirements TEXT,
    guidance_status TEXT NOT NULL CHECK (
        guidance_status IN (
            'approved', 'recommended', 'conditional',
            'approval_required', 'not_recommended'
        )
    ),
    effective_from DATE NOT NULL,
    effective_to DATE,
    source_url TEXT NOT NULL,
    licence TEXT NOT NULL,
    limitation TEXT NOT NULL,
    quality_status TEXT NOT NULL DEFAULT 'passed' CHECK (
        quality_status IN ('passed', 'failed')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (scientific_name IS NOT NULL OR common_name IS NOT NULL),
    CHECK (effective_to IS NULL OR effective_to >= effective_from),
    CHECK (
        mature_height_min_m IS NULL OR mature_height_max_m IS NULL
        OR mature_height_min_m <= mature_height_max_m
    ),
    CHECK (
        mature_canopy_width_min_m IS NULL OR mature_canopy_width_max_m IS NULL
        OR mature_canopy_width_min_m <= mature_canopy_width_max_m
    ),
    UNIQUE (dataset_version_id, source_row_number)
);

CREATE UNIQUE INDEX uq_council_species_guidance_business_key
    ON council_species_guidance (
        dataset_version_id, lga_code, scientific_name, common_name,
        mature_size_class, effective_from
    ) NULLS NOT DISTINCT;
CREATE INDEX idx_council_species_guidance_lookup
    ON council_species_guidance(lga_code, guidance_status, mature_size_class);
CREATE INDEX idx_council_species_guidance_species
    ON council_species_guidance(species_id) WHERE species_id IS NOT NULL;

CREATE OR REPLACE VIEW latest_victorian_lga_boundary AS
WITH current_version AS (
    SELECT version.dataset_version_id
    FROM dataset_version AS version
    JOIN dataset_source AS source USING (source_id)
    WHERE source.source_name =
              'Vicmap Admin - Local Government Area Polygon Aligned to Property'
      AND source.publisher = 'Department of Transport and Planning'
      AND version.integration_status = 'integrated'
      AND version.publication_status = 'application_ready'
    ORDER BY version.extracted_at DESC, version.dataset_version_id DESC
    LIMIT 1
)
SELECT boundary.*
FROM local_government_area AS boundary
JOIN current_version USING (dataset_version_id)
WHERE boundary.quality_status = 'passed';

CREATE OR REPLACE VIEW latest_council_species_guidance AS
WITH ranked_versions AS (
    SELECT
        version.dataset_version_id,
        source.source_name,
        source.publisher,
        ROW_NUMBER() OVER (
            PARTITION BY version.source_id
            ORDER BY version.extracted_at DESC, version.dataset_version_id DESC
        ) AS version_rank
    FROM dataset_version AS version
    JOIN dataset_source AS source USING (source_id)
    WHERE source.source_category = 'council_species_guidance'
      AND version.integration_status = 'integrated'
      AND version.publication_status = 'application_ready'
)
SELECT guidance.*, version.source_name, version.publisher
FROM council_species_guidance AS guidance
JOIN ranked_versions AS version USING (dataset_version_id)
WHERE version.version_rank = 1
  AND guidance.quality_status = 'passed'
  AND guidance.effective_from <= CURRENT_DATE
  AND (guidance.effective_to IS NULL OR guidance.effective_to >= CURRENT_DATE);

CREATE OR REPLACE FUNCTION get_council_species_options_by_address(
    p_address_search TEXT,
    p_mature_size_class TEXT DEFAULT NULL,
    p_result_limit INTEGER DEFAULT 100
)
RETURNS TABLE (
    council_code TEXT,
    council_name TEXT,
    list_category TEXT,
    scientific_name TEXT,
    common_name TEXT,
    mature_size_class TEXT,
    mature_height_min_m NUMERIC,
    mature_height_max_m NUMERIC,
    mature_canopy_width_min_m NUMERIC,
    mature_canopy_width_max_m NUMERIC,
    minimum_planting_area_m2 NUMERIC,
    sunlight_requirement TEXT,
    water_need_class TEXT,
    root_risk_class TEXT,
    site_requirements TEXT,
    guidance_status TEXT,
    locally_observed_tree_count BIGINT,
    source TEXT,
    source_url TEXT,
    licence TEXT,
    limitation TEXT
)
LANGUAGE plpgsql
STABLE
AS $function$
DECLARE
    v_normalized_search TEXT;
    v_longitude DOUBLE PRECISION;
    v_latitude DOUBLE PRECISION;
    v_match_count INTEGER;
    v_exact_count INTEGER;
    v_lga latest_victorian_lga_boundary%ROWTYPE;
BEGIN
    IF p_address_search IS NULL OR BTRIM(p_address_search) = '' THEN
        RAISE EXCEPTION 'address search is required';
    END IF;
    IF p_mature_size_class IS NOT NULL
       AND LOWER(p_mature_size_class) NOT IN ('small', 'medium', 'large') THEN
        RAISE EXCEPTION 'mature_size_class must be small, medium or large';
    END IF;
    IF p_result_limit <= 0 OR p_result_limit > 500 THEN
        RAISE EXCEPTION 'result_limit must be between 1 and 500';
    END IF;

    v_normalized_search := normalize_melbourne_address_search(p_address_search);
    WITH matches AS MATERIALIZED (
        SELECT match.*,
               match.normalized_address = v_normalized_search AS is_exact
        FROM search_melbourne_addresses(v_normalized_search, 50) AS match
    ), ranked AS (
        SELECT matches.*,
               COUNT(*) OVER ()::INTEGER AS match_count,
               COUNT(*) FILTER (WHERE is_exact) OVER ()::INTEGER AS exact_count,
               ROW_NUMBER() OVER (
                   ORDER BY CASE WHEN is_exact THEN 0 ELSE 1 END, full_address
               ) AS match_rank
        FROM matches
    )
    SELECT longitude::DOUBLE PRECISION, latitude::DOUBLE PRECISION,
           match_count, exact_count
    INTO v_longitude, v_latitude, v_match_count, v_exact_count
    FROM ranked WHERE match_rank = 1;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'no Melbourne address matched: %', BTRIM(p_address_search);
    END IF;
    IF v_exact_count = 0 AND v_match_count > 1 THEN
        RAISE EXCEPTION
            'address search is ambiguous: %. Supply the complete address and postcode',
            BTRIM(p_address_search);
    END IF;

    SELECT boundary.* INTO v_lga
    FROM latest_victorian_lga_boundary AS boundary
    WHERE ST_Covers(
        boundary.boundary_geometry,
        ST_Transform(ST_SetSRID(ST_MakePoint(v_longitude, v_latitude), 4326), 7855)
    )
    ORDER BY boundary.area_m2, boundary.lga_code
    LIMIT 1;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'matched address is outside the loaded Victorian LGA boundaries';
    END IF;

    RETURN QUERY
    WITH guidance AS (
        SELECT item.*
        FROM latest_council_species_guidance AS item
        WHERE item.lga_code = v_lga.lga_code
          AND (p_mature_size_class IS NULL
               OR item.mature_size_class = LOWER(p_mature_size_class))
    ), guidance_options AS (
        SELECT
            item.scientific_name,
            item.common_name,
            item.mature_size_class,
            item.mature_height_min_m,
            item.mature_height_max_m,
            item.mature_canopy_width_min_m,
            item.mature_canopy_width_max_m,
            item.minimum_planting_area_m2,
            item.sunlight_requirement,
            item.water_need_class,
            item.root_risk_class,
            item.site_requirements,
            item.guidance_status,
            CASE WHEN item.guidance_status IN ('approved', 'recommended')
                 THEN 'available_now' ELSE 'council_approval_required' END
                AS list_category,
            observed.tree_count,
            item.source_name AS source,
            item.source_url,
            item.licence,
            item.limitation
        FROM guidance AS item
        LEFT JOIN LATERAL (
            SELECT COUNT(*)::BIGINT AS tree_count
            FROM latest_metropolitan_named_tree_inventory AS tree
            WHERE ST_Covers(v_lga.boundary_geometry, tree.tree_location)
              AND (
                  (item.scientific_name IS NOT NULL AND tree.scientific_name ILIKE item.scientific_name)
                  OR (item.scientific_name IS NULL AND item.common_name IS NOT NULL
                      AND tree.common_name ILIKE item.common_name)
              )
        ) AS observed ON TRUE
    ), observed_without_guidance AS (
        SELECT
            tree.scientific_name,
            tree.common_name,
            NULL::TEXT AS mature_size_class,
            NULL::NUMERIC AS mature_height_min_m,
            NULL::NUMERIC AS mature_height_max_m,
            NULL::NUMERIC AS mature_canopy_width_min_m,
            NULL::NUMERIC AS mature_canopy_width_max_m,
            NULL::NUMERIC AS minimum_planting_area_m2,
            NULL::TEXT AS sunlight_requirement,
            NULL::TEXT AS water_need_class,
            NULL::TEXT AS root_risk_class,
            NULL::TEXT AS site_requirements,
            'approval_required'::TEXT AS guidance_status,
            'council_approval_required'::TEXT AS list_category,
            COUNT(*)::BIGINT AS tree_count,
            MIN(tree.source_name)::TEXT AS source,
            MIN(tree.source_url)::TEXT AS source_url,
            MIN(tree.licence)::TEXT AS licence,
            'Observed in a council-maintained public-tree inventory; occurrence is not planting permission or evidence of private-site suitability.'::TEXT AS limitation
        FROM latest_metropolitan_named_tree_inventory AS tree
        WHERE ST_Covers(v_lga.boundary_geometry, tree.tree_location)
          AND NOT EXISTS (
              SELECT 1 FROM guidance AS item
              WHERE (item.scientific_name IS NOT NULL
                     AND tree.scientific_name ILIKE item.scientific_name)
                 OR (item.scientific_name IS NULL AND item.common_name IS NOT NULL
                     AND tree.common_name ILIKE item.common_name)
          )
        GROUP BY tree.scientific_name, tree.common_name
    ), options AS (
        SELECT * FROM guidance_options
        UNION ALL
        SELECT * FROM observed_without_guidance
    )
    SELECT
        v_lga.lga_code,
        v_lga.lga_official_name,
        options.list_category,
        options.scientific_name,
        options.common_name,
        options.mature_size_class,
        options.mature_height_min_m,
        options.mature_height_max_m,
        options.mature_canopy_width_min_m,
        options.mature_canopy_width_max_m,
        options.minimum_planting_area_m2,
        options.sunlight_requirement,
        options.water_need_class,
        options.root_risk_class,
        options.site_requirements,
        options.guidance_status,
        COALESCE(options.tree_count, 0),
        options.source,
        options.source_url,
        options.licence,
        options.limitation
    FROM options
    ORDER BY
        CASE options.list_category WHEN 'available_now' THEN 0 ELSE 1 END,
        COALESCE(options.tree_count, 0) DESC,
        COALESCE(options.common_name, options.scientific_name)
    LIMIT p_result_limit;
END;
$function$;

COMMENT ON TABLE local_government_area IS
    'Versioned authoritative Vicmap property-aligned Victorian LGA polygons; administrative lookup only.';
COMMENT ON TABLE council_species_guidance IS
    'Source-specific council planting guidance. Only explicit approved/recommended rows qualify for available_now; inventory occurrence never implies permission.';
COMMENT ON FUNCTION get_council_species_options_by_address(TEXT, TEXT, INTEGER) IS
    'Resolves an address to its authoritative LGA and separates verified council guidance from locally observed species requiring council approval.';

COMMIT;
