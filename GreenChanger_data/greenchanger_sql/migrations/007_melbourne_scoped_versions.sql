BEGIN;

ALTER TABLE dataset_version
    ADD COLUMN IF NOT EXISTS parent_version_id UUID REFERENCES dataset_version(dataset_version_id),
    ADD COLUMN IF NOT EXISTS analysis_area_id UUID REFERENCES analysis_area(analysis_area_id),
    ADD COLUMN IF NOT EXISTS derivation_method TEXT;

CREATE INDEX IF NOT EXISTS idx_dataset_version_parent
    ON dataset_version(parent_version_id);

CREATE INDEX IF NOT EXISTS idx_dataset_version_analysis_area
    ON dataset_version(analysis_area_id);

CREATE TABLE IF NOT EXISTS analysis_area_tile (
    analysis_area_tile_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    analysis_area_id UUID NOT NULL REFERENCES analysis_area(analysis_area_id) ON DELETE CASCADE,
    tile_geometry geometry(Geometry, 7855) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_analysis_area_tile_area
    ON analysis_area_tile(analysis_area_id);

CREATE INDEX IF NOT EXISTS idx_analysis_area_tile_geometry
    ON analysis_area_tile USING GIST(tile_geometry);

INSERT INTO analysis_area_tile (analysis_area_id, tile_geometry)
SELECT aa.analysis_area_id, pieces.geom
FROM analysis_area AS aa
CROSS JOIN LATERAL ST_Subdivide(aa.boundary_geometry, 256) AS pieces(geom)
WHERE aa.source_area_code = '2GMEL'
  AND aa.source_year = 2026
  AND NOT EXISTS (
      SELECT 1 FROM analysis_area_tile AS existing
      WHERE existing.analysis_area_id = aa.analysis_area_id
  );

COMMIT;
