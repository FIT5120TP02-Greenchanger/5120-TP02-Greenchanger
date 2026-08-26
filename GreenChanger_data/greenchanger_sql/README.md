# `greenchanger_sql` database definition

This folder defines the GreenChanger PostgreSQL 17/PostGIS database. Use
`greenchanger_script/migrate.py` to apply it; do not manually paste individual
migrations into the shared database.

## Folder contents

```text
greenchanger_sql/
├── schema.sql                  # Complete current schema for reference/local setup
├── migrations/
│   ├── 001_schema.sql         # Core tables, constraints, indexes and base views
│   ├── 002_reference_data.sql # Includes the reference seed file
│   ├── 003_analytics_views.sql# Includes application-facing analytical views
│   ├── 004_spatial_assets.sql # Raster/vector asset provenance
│   ├── 005_vicmap_address_property.sql
│   ├── 006_greater_melbourne_boundary.sql
│   ├── 007_melbourne_scoped_versions.sql
│   ├── 008_heat_baseline_mosaic.sql
│   ├── 009_canopy_baseline.sql
│   ├── 010_property_baseline_lookup.sql
│   ├── 011_tree_urban_quality_scope.sql
│   ├── 012_property_tree_limitations.sql
│   └── 013_cost_estimate_delivery.sql
├── seeds/001_reference_data.sql
└── analytics/001_views.sql
```

## File reference

| File | Responsibility |
| --- | --- |
| `schema.sql` | Complete current PostgreSQL/PostGIS schema for local setup and structural reference. |
| `migrations/001_schema.sql` | Creates the original entities, constraints, spatial indexes and base views. |
| `migrations/002_reference_data.sql` | Loads the version-controlled reference seed through an include directive. |
| `migrations/003_analytics_views.sql` | Loads the original analytical/application views through an include directive. |
| `migrations/004_spatial_assets.sql` | Adds source-raster and vector-asset provenance used by canopy and Landsat processing. |
| `migrations/005_vicmap_address_property.sql` | Adds Vicmap Address and Property attributes, source join keys and supporting indexes. |
| `migrations/006_greater_melbourne_boundary.sql` | Adds official ABS boundary metadata and the `2GMEL` source identity. |
| `migrations/007_melbourne_scoped_versions.sql` | Adds boundary tiles and provenance for Melbourne-only derived dataset versions. |
| `migrations/008_heat_baseline_mosaic.sql` | Creates the deduplicated 500 m Landsat heat baseline structure and current view. |
| `migrations/009_canopy_baseline.sql` | Creates the aligned 500 m canopy baseline structure and current view. |
| `migrations/010_property_baseline_lookup.sql` | Adds model validation gates and the application-facing property baseline lookup. |
| `migrations/011_tree_urban_quality_scope.sql` | Adds Tree Urban record quality status and the dataset-version index required by API ingestion. |
| `migrations/012_property_tree_limitations.sql` | Restricts property tree lookup to the current `2GMEL` version and always returns the machine-derived-data warning. |
| `migrations/013_cost_estimate_delivery.sql` | Publishes current source-backed cost contexts with greening-option labels, confidence and an indicative-estimate disclaimer. |
| `seeds/001_reference_data.sql` | Defines sources, greening options, analytical measures, model metadata and sample test cases. |
| `analytics/001_views.sql` | Defines reusable analytical views for dataset quality, site baselines and scenario comparison. |

`schema.sql` must describe the same current structure as the cumulative
migrations. Existing databases advance through migrations; new schema changes
must be added as the next numbered migration.

## Main entity groups

### Provenance and quality

- `dataset_source`: publisher, catalogue URL, licence, coverage and access.
- `dataset_version`: one reproducible extraction with dates, checksum, counts,
  quality state and publication state. Derived versions also store their parent,
  analysis area and derivation method.
- `spatial_asset`: source/raw asset path, API URL, CRS, checksum and metadata.
- `data_quality_rule`, `data_quality_run`, `data_quality_result`: Data Quality & Preparation evidence.
- `transformation_run`, `integration_run`: cleaning and load audit history.
- `data_limitation`: known currency, coverage, join and interpretation issues.

### Spatial foundation

- `analysis_area`: versioned supported spatial boundary. Migration 006 adds
  ABS area code/year, source metadata and dataset-version provenance for the
  official ASGS 2026 Greater Melbourne GCCSA (`2GMEL`).
- `analysis_area_tile`: indexed subdivisions of a complex boundary used for
  scalable point/polygon membership checks. Migration 007 creates these tiles.
- `address`: Vicmap Address point and source identifiers.
- `parcel`: the project property/parcel polygon entity. Current Vicmap Property
  `prop_pfi` is stored in `source_parcel_id`.
- `site`: application site linked to an analysis area and optional address and
  property/parcel record.

Vicmap Address `property_pfi` is stored in `address.source_property_id` and
matches `parcel.source_parcel_id`. Migration 005 adds this join key plus useful
address/property attributes and indexes.

Migration 010 exposes `latest_greater_melbourne_address_property` and the
selective `get_property_baseline(address, limit)` function. It attaches current
heat and canopy cells at the parcel point-on-surface without materialising
millions of repeated environmental values.

The function separates Landsat land-surface temperature from recent BOM station
air temperature and labels the distance to that station. It exposes the canopy
proxy only at `neighbourhood_500m` scope, keeps property canopy null, and adds
mapped Tree Urban counts when an integrated tree version exists.

### Environmental and analytical data

- `weather_observation`: BOM station air observations.
- `heat_observation`: spatial land-surface temperature/heat values.
- `heat_baseline_cell`: one deduplicated baseline temperature per 500 m cell,
  with acquisition date, source scenes and overlap spread. The
  `latest_greater_melbourne_heat_baseline` view exposes the current version.
- `canopy_baseline_cell`: one versioned canopy percentage per 500 m cell, with
  source type, native source-pixel size and an explicit proxy flag. The
  `latest_greater_melbourne_canopy_baseline` view exposes the current version.
- `vegetation_observation`, `canopy_patch`, `urban_tree`: canopy and greenery.
- `species_profile`, `greening_option`: available intervention definitions.
- `cost_estimate`: dated, source-backed indicative cost ranges.
- `application_ready_cost_estimate`: current cost contexts joined to greening-option labels with confidence, inclusions and the mandatory not-a-quote disclaimer.
- `model_version.validation_status`: explicit model gate. Only `validated`
  models can appear in `application_ready_measure_result`.
- Scenario, intervention, result and community entities store model inputs and
  outputs; they do not convert estimates into observed facts.

## Migration workflow

```bash
python greenchanger_script/migrate.py --status
python greenchanger_script/migrate.py --confirm-shared
python greenchanger_script/migrate.py --status
```

The runner creates `schema_version`, expands `-- include:` directives, records a
SHA-256 checksum for every migration and refuses to continue if an already
applied file has changed or disappeared.

To add a schema change:

1. Create the next numbered migration in `migrations/`.
2. Use forward-only, recoverable SQL such as `ADD COLUMN IF NOT EXISTS` and
   `CREATE INDEX IF NOT EXISTS` where appropriate.
3. Update `schema.sql` to match the cumulative structure.
4. Update the expected migration list in `tests/test_migrate.py`.
5. Run `python -m unittest discover -v`.
6. Check status before applying to shared Aurora.

Never modify `001`–`012` after they have been applied. Their checksums are part
of the migration audit trail.

## Data preparation and database integration

The database accepts only rows that have passed the Python quality gate.
Spatial source geometries arrive in their documented CRS and are transformed to
GDA2020 / MGA zone 55 (`EPSG:7855`) in the insert statement. Geometry columns
have fixed types and spatial indexes where needed. Source business keys are
unique within a `dataset_version`, allowing new source versions to coexist with
older reproducible versions.

For address/property ingestion:

1. Create the two `dataset_version` rows with checksums and observed dates.
2. Register the gzip JSON Lines extracts in `spatial_asset`.
3. Store the completeness, uniqueness and positive-area results.
4. Insert accepted address points and property polygons only.
5. Set successful versions to `integration_status='integrated'` and
   `publication_status='application_ready'`.
6. Record bbox, rejected-record and unmatched-join limitations.

## Failure handling

- A failed ingestion transaction is rolled back.
- A dataset below 95% quality is not integrated.
- Foreign keys prevent orphaned versions, sites and analytical results.
- Check constraints reject negative areas, invalid percentages and unsupported
  status values.
- Unique constraints prevent duplicate source keys within one version.
- Applied-migration checksum mismatches stop deployment rather than silently
  changing history.
- Shared destructive reset is blocked in `migrate.py`; use a local sandbox for
  rebuild testing.

## Verification queries

```sql
-- Latest source versions and quality status
SELECT * FROM latest_dataset_version;

-- Rule-level failures
SELECT q.dataset_version_id, r.rule_code, x.failed_count, x.pass_rate
FROM data_quality_run q
JOIN data_quality_result x USING (quality_run_id)
JOIN data_quality_rule r USING (quality_rule_id)
ORDER BY q.completed_at DESC, r.rule_code;

-- Address/property source-key coverage for selected versions
SELECT COUNT(*) FILTER (WHERE p.parcel_id IS NOT NULL) AS matched,
       COUNT(*) AS address_total
FROM address a
LEFT JOIN parcel p
  ON p.source_parcel_id = a.source_property_id
 AND p.dataset_version_id = :property_version
WHERE a.dataset_version_id = :address_version;

-- Geometry checks
SELECT COUNT(*) FILTER (WHERE NOT ST_IsValid(parcel_geometry)) AS invalid,
       COUNT(*) FILTER (WHERE ST_SRID(parcel_geometry) <> 7855) AS wrong_srid
FROM parcel
WHERE dataset_version_id = :property_version;

-- Prototype-ready property baseline lookup
SELECT *
FROM get_property_baseline('1 COLLINS STREET MELBOURNE', 5);
```
