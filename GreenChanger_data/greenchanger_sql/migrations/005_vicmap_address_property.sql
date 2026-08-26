ALTER TABLE address
    ADD COLUMN IF NOT EXISTS source_property_id TEXT,
    ADD COLUMN IF NOT EXISTS lga_code TEXT,
    ADD COLUMN IF NOT EXISTS is_primary TEXT,
    ADD COLUMN IF NOT EXISTS address_class TEXT;

ALTER TABLE parcel
    ADD COLUMN IF NOT EXISTS property_number TEXT,
    ADD COLUMN IF NOT EXISTS property_type TEXT,
    ADD COLUMN IF NOT EXISTS property_status TEXT,
    ADD COLUMN IF NOT EXISTS lga_code TEXT;

CREATE INDEX IF NOT EXISTS idx_address_source_property
    ON address(source_property_id);

CREATE INDEX IF NOT EXISTS idx_parcel_source_id
    ON parcel(source_parcel_id);
