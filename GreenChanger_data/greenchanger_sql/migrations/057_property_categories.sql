BEGIN;

CREATE TABLE property_category (
    category_code TEXT PRIMARY KEY,
    category_name TEXT NOT NULL,
    category_group TEXT NOT NULL,
    description TEXT NOT NULL,
    display_order SMALLINT NOT NULL CHECK (display_order > 0),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (category_name)
);

COMMENT ON TABLE property_category IS
    'Controlled application categories for a property or place, such as house, station and road. These categories are not inferred from Vicmap Property O/G or Vicmap Address S/M codes.';

INSERT INTO property_category (
    category_code, category_name, category_group, description, display_order
)
VALUES
    ('house', 'House', 'residential',
     'A detached or semi-detached residential house supported by a building or land-use source.', 10),
    ('townhouse', 'Townhouse', 'residential',
     'A townhouse or attached dwelling supported by a building or land-use source.', 20),
    ('apartment', 'Apartment', 'residential',
     'An apartment or multi-unit residential building supported by a building or land-use source.', 30),
    ('station', 'Station', 'transport',
     'A railway, tram, bus or other transport station supported by an authoritative transport source.', 40),
    ('road', 'Road', 'transport',
     'A road or road-reserve property supported by an authoritative transport or cadastral source.', 50),
    ('school', 'School', 'community',
     'A school or education facility supported by a feature-of-interest or land-use source.', 60),
    ('hospital', 'Hospital', 'community',
     'A hospital or health facility supported by a feature-of-interest or land-use source.', 70),
    ('commercial', 'Commercial', 'business',
     'A commercial property supported by an authoritative building or land-use source.', 80),
    ('industrial', 'Industrial', 'business',
     'An industrial property supported by an authoritative building or land-use source.', 90),
    ('park', 'Park or reserve', 'open_space',
     'A park, reserve or public open-space property supported by an authoritative source.', 100),
    ('utility', 'Utility', 'infrastructure',
     'A utility or infrastructure property supported by an authoritative source.', 110),
    ('other', 'Other', 'other',
     'A source-classified category outside the current controlled list.', 120),
    ('unclassified', 'Unclassified', 'unclassified',
     'No supported property/place category has been loaded.', 999)
ON CONFLICT (category_code) DO UPDATE SET
    category_name = EXCLUDED.category_name,
    category_group = EXCLUDED.category_group,
    description = EXCLUDED.description,
    display_order = EXCLUDED.display_order,
    active = TRUE;

CREATE TABLE property_category_assignment (
    property_category_assignment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parcel_id UUID NOT NULL REFERENCES parcel(parcel_id) ON DELETE CASCADE,
    category_code TEXT NOT NULL REFERENCES property_category(category_code),
    category_detail TEXT,
    source_dataset_version_id UUID REFERENCES dataset_version(dataset_version_id),
    classification_source TEXT NOT NULL,
    source_feature_id TEXT,
    source_url TEXT CHECK (source_url IS NULL OR source_url ~ '^https://'),
    classification_method TEXT NOT NULL,
    confidence NUMERIC CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    is_primary BOOLEAN NOT NULL DEFAULT TRUE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    valid_from DATE,
    valid_to DATE,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from),
    CHECK (BTRIM(classification_source) <> ''),
    CHECK (BTRIM(classification_method) <> '')
);

COMMENT ON TABLE property_category_assignment IS
    'Source-backed category assignments for versioned parcel records. Do not classify a parcel as house, station, road or another use from Vicmap Property type O/G or Address class S/M alone.';

CREATE UNIQUE INDEX uq_property_category_assignment_source
    ON property_category_assignment (
        parcel_id, category_code, classification_source,
        COALESCE(source_feature_id, '')
    );

CREATE UNIQUE INDEX uq_property_category_assignment_primary
    ON property_category_assignment(parcel_id)
    WHERE is_primary AND active;

CREATE INDEX idx_property_category_assignment_category
    ON property_category_assignment(category_code, parcel_id)
    WHERE active;

CREATE INDEX idx_property_category_assignment_dataset_version
    ON property_category_assignment(source_dataset_version_id)
    WHERE source_dataset_version_id IS NOT NULL;

CREATE OR REPLACE FUNCTION vicmap_property_type_label(p_property_type TEXT)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
RETURN CASE UPPER(BTRIM(p_property_type))
    WHEN 'O' THEN 'Occupancy'
    WHEN 'G' THEN 'Graphic entity'
    ELSE NULL
END;

COMMENT ON FUNCTION vicmap_property_type_label(TEXT) IS
    'Decodes Vicmap Property O as Occupancy and G as Graphic entity. Neither value is a building-use category and O must not be presented as House.';

CREATE OR REPLACE FUNCTION vicmap_address_class_label(p_address_class TEXT)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
RETURN CASE UPPER(BTRIM(p_address_class))
    WHEN 'S' THEN 'Standard'
    WHEN 'M' THEN 'Miscellaneous'
    ELSE NULL
END;

COMMENT ON FUNCTION vicmap_address_class_label(TEXT) IS
    'Decodes Vicmap Address S as Standard and M as Miscellaneous. Address class is not residential or property-use classification.';

CREATE OR REPLACE VIEW application_ready_property_category AS
WITH primary_assignment AS (
    SELECT DISTINCT ON (assignment.parcel_id)
           assignment.parcel_id,
           assignment.category_code,
           assignment.category_detail,
           assignment.source_dataset_version_id,
           assignment.classification_source,
           assignment.source_feature_id,
           assignment.source_url,
           assignment.classification_method,
           assignment.confidence,
           assignment.valid_from,
           assignment.valid_to
    FROM property_category_assignment AS assignment
    JOIN property_category AS category
      ON category.category_code = assignment.category_code
     AND category.active
    WHERE assignment.active
      AND assignment.is_primary
      AND (assignment.valid_from IS NULL OR assignment.valid_from <= CURRENT_DATE)
      AND (assignment.valid_to IS NULL OR assignment.valid_to >= CURRENT_DATE)
    ORDER BY assignment.parcel_id,
             assignment.confidence DESC NULLS LAST,
             assignment.updated_at DESC,
             assignment.property_category_assignment_id
)
SELECT
    property.address_id,
    property.parcel_id,
    property.full_address,
    property.locality_name,
    property.postcode,
    property.source_property_id,
    property.source_parcel_id,
    property.property_type AS vicmap_property_type,
    vicmap_property_type_label(property.property_type) AS vicmap_property_type_label,
    property.address_class AS vicmap_address_class,
    vicmap_address_class_label(property.address_class) AS vicmap_address_class_label,
    COALESCE(assignment.category_code, 'unclassified') AS property_category_code,
    category.category_name AS property_category_name,
    category.category_group AS property_category_group,
    assignment.category_detail,
    CASE WHEN assignment.parcel_id IS NULL
         THEN 'unclassified_source_not_loaded'
         ELSE 'source_backed_category'
    END AS property_category_status,
    assignment.classification_source,
    assignment.source_dataset_version_id,
    assignment.source_feature_id,
    assignment.source_url,
    assignment.classification_method,
    assignment.confidence,
    CASE WHEN assignment.parcel_id IS NULL
         THEN 'Vicmap Property O/G and Address S/M do not identify house, station, road or land use; load a supported building, transport, feature-of-interest or land-use classification.'
         ELSE 'Category is limited to the cited classification source, method and validity period.'
    END AS property_category_limitation
FROM latest_greater_melbourne_address_property AS property
LEFT JOIN primary_assignment AS assignment USING (parcel_id)
JOIN property_category AS category
  ON category.category_code = COALESCE(assignment.category_code, 'unclassified');

COMMENT ON VIEW application_ready_property_category IS
    'Application property/address rows with a controlled primary category and provenance. Unassigned rows remain explicitly unclassified; Vicmap raw code labels are exposed separately.';

CREATE OR REPLACE FUNCTION get_property_category(
    p_address_search TEXT,
    p_result_limit INTEGER DEFAULT 10
)
RETURNS SETOF application_ready_property_category
LANGUAGE SQL
STABLE
PARALLEL SAFE
AS $function$
    SELECT category.*
    FROM application_ready_property_category AS category
    WHERE p_address_search IS NOT NULL
      AND BTRIM(p_address_search) <> ''
      AND UPPER(category.full_address) LIKE
          normalize_melbourne_address_search(p_address_search) || '%'
    ORDER BY
        CASE WHEN UPPER(category.full_address) =
                  normalize_melbourne_address_search(p_address_search)
             THEN 0 ELSE 1 END,
        category.full_address,
        category.address_id
    LIMIT LEAST(GREATEST(COALESCE(p_result_limit, 10), 1), 50);
$function$;

COMMENT ON FUNCTION get_property_category(TEXT, INTEGER) IS
    'Returns source-backed property/place categories for a Melbourne address search. Until a category source is loaded, the result is Unclassified rather than an inferred House, Station or Road.';

COMMIT;
