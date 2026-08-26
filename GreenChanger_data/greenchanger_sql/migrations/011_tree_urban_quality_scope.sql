BEGIN;

ALTER TABLE urban_tree
    ADD COLUMN IF NOT EXISTS quality_status TEXT NOT NULL DEFAULT 'unreviewed';

ALTER TABLE urban_tree
    DROP CONSTRAINT IF EXISTS ck_urban_tree_quality_status;

ALTER TABLE urban_tree
    ADD CONSTRAINT ck_urban_tree_quality_status CHECK (
        quality_status IN ('unreviewed', 'passed', 'failed')
    );

CREATE INDEX IF NOT EXISTS idx_tree_dataset_version
    ON urban_tree(dataset_version_id);

COMMENT ON COLUMN urban_tree.quality_status IS
    'Record-level status assigned by the configured Tree Urban quality gate.';

COMMIT;
