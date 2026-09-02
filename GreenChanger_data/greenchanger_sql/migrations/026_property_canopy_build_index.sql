BEGIN;

-- Supports resumable property-canopy batches that filter one property dataset
-- and read parcels in stable parcel_id order without sorting all Melbourne rows.
CREATE INDEX IF NOT EXISTS idx_parcel_version_parcel_id
    ON parcel(dataset_version_id, parcel_id);

COMMIT;
