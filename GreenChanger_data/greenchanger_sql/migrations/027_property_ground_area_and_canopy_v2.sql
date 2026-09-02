BEGIN;

-- ArcGIS Shape__Area was calculated in Web Mercator and is inflated at
-- Melbourne's latitude. Store ground area from the prepared EPSG:7855
-- geometry so parcel coverage, lot size and canopy percentages use m2.
UPDATE parcel AS p
SET parcel_area_m2 = ST_Area(p.parcel_geometry)
FROM dataset_version AS dv
JOIN dataset_source AS ds USING (source_id)
JOIN analysis_area AS aa USING (analysis_area_id)
WHERE p.dataset_version_id = dv.dataset_version_id
  AND ds.source_name = 'Vicmap Property'
  AND aa.source_area_code = '2GMEL'
  AND p.parcel_geometry IS NOT NULL
  AND (
      p.parcel_area_m2 IS NULL
      OR ABS(p.parcel_area_m2 - ST_Area(p.parcel_geometry))
         > GREATEST(1, ST_Area(p.parcel_geometry) * 0.01)
  );

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
      AND dv.derivation_method = 'property_canopy_raster_clip_v2'
    ORDER BY dv.extracted_at DESC
    LIMIT 1
)
SELECT summary.*
FROM property_canopy_summary AS summary
JOIN latest_version USING (dataset_version_id)
WHERE summary.quality_status = 'passed';

COMMENT ON VIEW latest_melbourne_property_canopy IS
    'Application-ready parcel canopy calculated from <=2 m analytical Tree Extent pixels and EPSG:7855 ground parcel area. Incomplete or failed versions are excluded.';

COMMIT;
