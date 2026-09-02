BEGIN;

UPDATE dataset_version
SET quality_status = 'failed',
    integration_status = 'failed',
    publication_status = 'internal'
WHERE derivation_method = 'property_canopy_raster_clip_v1'
  AND publication_status = 'internal';

UPDATE transformation_run AS run
SET completed_at = COALESCE(run.completed_at, CURRENT_TIMESTAMP),
    run_status = 'failed',
    notes = CONCAT_WS(
        E'\n', NULLIF(run.notes, ''),
        'Retired: v1 divided ground raster coverage by ArcGIS Web Mercator Shape__Area. Use property_canopy_raster_clip_v2.'
    )
FROM dataset_version AS output
WHERE run.output_version_id = output.dataset_version_id
  AND output.derivation_method = 'property_canopy_raster_clip_v1';

COMMIT;
