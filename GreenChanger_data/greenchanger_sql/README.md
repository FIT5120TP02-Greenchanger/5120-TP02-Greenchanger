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
│   ├── 013_cost_estimate_delivery.sql
│   ├── 014_intervention_evidence.sql
│   ├── 015_intervention_model_validation.sql
│   ├── 016_multi_station_weather_context.sql
│   ├── 017_environmental_classifications.sql
│   ├── 018_environment_context_radius.sql
│   ├── 019_environment_context_by_address.sql
│   └── 020_evidence_backed_absolute_classifications.sql
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
| `migrations/025_current_dataset_sources.sql` | Registers the current multi-station Melbourne BOM source without changing the checksum of historical migration 002. |
| `migrations/010_property_baseline_lookup.sql` | Adds model validation gates and the application-facing property baseline lookup. |
| `migrations/011_tree_urban_quality_scope.sql` | Adds Tree Urban record quality status and the dataset-version index required by API ingestion. |
| `migrations/012_property_tree_limitations.sql` | Restricts property tree lookup to the current `2GMEL` version and always returns the machine-derived-data warning. |
| `migrations/013_cost_estimate_delivery.sql` | Publishes current source-backed cost contexts with greening-option labels, confidence and an indicative-estimate disclaimer. |
| `migrations/014_intervention_evidence.sql` | Stores selected primary studies, approved/prohibited uses and independent validation/output-precision gates. |
| `migrations/015_intervention_model_validation.sql` | Defines four-action parameters, the range-only model and auditable validation runs/results. |
| `migrations/016_multi_station_weather_context.sql` | Adds recent nearest-station BOM context, distance-status rules and suppression of stale or overly distant temperatures. |
| `migrations/017_environmental_classifications.sql` | Adds versioned Melbourne tercile thresholds, missing-safe classification and property-lookup labels. |
| `migrations/029_fixed_temperature_display_bands.sql` | Changes heat labels to fixed GreenChanger bands (≤27°C, >27–30°C, >30°C), preserves canopy thresholds and keeps missing/non-finite values unavailable. |
| `migrations/030_address_match_deduplication.sql` | Groups repeated address–parcel joins by normalised full address, preserves parcel options and prevents false “ambiguous/no match” results for abbreviations such as `RD`. |
| `migrations/031_address_representative_coordinate.sql` | Selects longitude and latitude together from one deterministic representative address row, preventing hybrid coordinates assembled from separate aggregates. |
| `migrations/032_fixed_canopy_benchmark_bands.sql` | Replaces canopy terciles with fixed evidence-backed progress bands using the official 15.3% metropolitan baseline and 30% Plan for Victoria urban target. |
| `migrations/018_environment_context_radius.sql` | Adds a bounded, application-facing radius query for current mapped-tree points and clipped 500 m heat cells. |
| `migrations/019_environment_context_by_address.sql` | Resolves one unambiguous Melbourne address and delegates to the bounded coordinate-radius query. |
| `migrations/020_evidence_backed_absolute_classifications.sql` | Stores threshold evidence with exact source locators and adds measurement-specific daily-mean air-temperature and canopy benchmark functions. |
| `migrations/021_historical_temperature_context.sql` | Corrects the one-day historical temperature contract: 27.2°C becomes duration-qualified context and the retired 30°C method returns structured JSON metadata rather than a current-risk label. |
| `migrations/022_address_search_and_indexes.sql` | Adds missing foreign-key/application lookup indexes and expands supported address abbreviations such as `RD` to `ROAD` before Vicmap lookup. |
| `migrations/023_property_level_canopy.sql` | Stores versioned parcel-clipped analytical canopy, publishes only >=95%-quality results and adds an address lookup with explicit `Unavailable` handling. |
| `migrations/024_property_current_air_temperature.sql` | Adds an indexed, source-labelled property address lookup for nearest BOM observations within three hours, with distance warnings and >25 km suppression. |
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
  official ASGS 2026 Melbourne GCCSA (`2GMEL`).
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

Migration 016 wraps the property lookup with nearest-station selection across
the application-ready multi-station BOM observations. Only observations no
older than three hours are eligible. Distance statuses are `good_local_context`
(at most 10 km), `regional_context_warning` (10–25 km), and
`too_distant_temperature_suppressed` (over 25 km); no eligible station is
`unavailable_no_observation_within_3_hours`. Station name, time and distance
remain traceable, while temperature is null beyond 25 km.

The function separates Landsat land-surface temperature from recent BOM station
air temperature and labels the distance to that station. It exposes the canopy
proxy only at `neighbourhood_500m` scope, keeps property canopy null, and adds
mapped Tree Urban counts when an integrated tree version exists.

Migration 018 exposes `get_environment_context(longitude, latitude, radius_m,
layers, result_limit)`. It transforms an EPSG:4326 coordinate to EPSG:7855,
requires the point to be inside the official Melbourne boundary, and uses
`ST_DWithin` with the existing GiST indexes to return only nearby records.
Supported layers are `trees` and `heat`; the radius defaults to 500 m and is
capped at 2 km, while the result limit is capped at 2,000 per layer. Tree rows
come only from the newest application-ready Melbourne Tree Urban version.
Heat rows come from the current application-ready 500 m baseline, and their
GeoJSON polygons are clipped to the requested search circle. The heat payload
continues to identify the measurement as Landsat land-surface temperature.

Migration 019 exposes `get_environment_context_by_address(address, radius_m,
layers, result_limit)`. It uses the existing property-baseline address search to
resolve coordinates, accepts a unique result or one exact full-address match,
and rejects missing, unmatched or ambiguous searches. It then delegates radius,
layer, boundary and result-limit enforcement to migration 018 rather than
duplicating spatial-query logic.

Migration 022 adds case/whitespace normalisation and expands unambiguous
Australian street types including `RD`, `AVE`, `BLVD`, `CRES`, `CT`, `DR`,
`HWY`, `LN`, `PDE`, `PL` and `TCE`. `ST` is deliberately not expanded because
it can mean Saint, as in St Kilda. The migration also adds missing foreign-key,
status/version, time-series and address-prefix indexes. Existing primary-key,
unique and spatial GiST indexes are not duplicated. Because address, parcel and
tree tables are large, schedule the shared migration during a low-write period.

Migration 017 adds `environmental_classification_scheme` and
`environmental_classification_threshold`. The active
`current_environmental_classification_threshold` view exposes source-version
IDs, effective cutoffs, sample counts, scope and explanations. Migration 029
overrides the effective heat cutoffs with fixed 27°C/30°C display bands.
Migration 032 replaces canopy terciles with the official 15.3% metropolitan
baseline and 30% Plan for Victoria urban target. The SQL classifier returns
`Unavailable` for missing or non-finite values. Property lookup keeps the
measurement source and type alongside its labels.

Migration 020 records each absolute reference's URL and exact page/section
locator. Migration 021 corrects its temperature contract in a forward-only
change: the 27.2°C research percentile is marked as context requiring at least
two consecutive days, and the one-pair function compares only with the retired
30°C Victorian Central District threshold. It returns JSONB containing the
calculated mean, historical-context status, method, limitation and source—never
a bare current-risk label. It remains prohibited for a current observation,
apparent temperature or Landsat LST. The separate canopy helper uses the
official 15.3% metropolitan baseline and current 30% Plan for Victoria
urban-area target. It is prohibited for the rendered canopy proxy and does not
establish property-level planning compliance.

The fixed classification contract is:

| Metric | Low | Medium | High | Low / Medium / High count |
| --- | --- | --- | --- | --- |
| Temperature display band | ≤27°C | >27°C and ≤30°C | >30°C | Counts depend on the source values |
| 500 m neighbourhood canopy progress | <15.3% | ≥15.3% and <30% | ≥30% | Counts depend on source values |

The temperature bands are application-defined and are not regulatory, health,
comfort or BOM heatwave standards. Canopy labels describe progress against the
published baseline and target; they are not property compliance findings. Its
threshold rows remain tied to specific source dataset-version IDs. Rebuilt canopy
baselines must produce a new reviewed scheme version rather than changing
historical values.

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
- `model_version.output_precision`: independent precision gate. Validation can
  authorise an indicative interval without authorising a precise
  after-temperature.
- `intervention_evidence`: reviewed primary research with outcome, scale,
  reported effects, transferability and explicit approved/prohibited uses.
- `model_evidence`: records how a model version uses each selected study.
- `selected_intervention_evidence`: application/documentation-facing evidence
  register without implying that reported maxima are model coefficients.
- `intervention_model_parameter`: versioned required inputs, guardrails and
  source-linked evidence bounds for trees, pots, garden beds and green walls.
- `intervention_model_validation_run` and
  `intervention_model_validation_result`: expected/actual evidence-case audit.
- `current_intervention_model_parameter`: source-traceable parameter view.
- Scenario, intervention, result and community entities store model inputs and
  outputs; they do not convert estimates into observed facts.

The versioned Residential Greening Scenario Simulation input contract currently lives in
`config/residential_greening_simulation_inputs.json` and is validated before these scenario
entities are written. This keeps input/UI assumptions separate from the
database's literature evidence bounds. No database migration is required for
the contract itself; persisted scenario rows must retain its
`residential-greening-simulation-inputs-v1` version in their assumptions/provenance metadata.

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

The next migration number is `025`. Never modify `001`–`024` after they have
been applied. Their checksums are part of the migration audit trail.

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

-- Bounded map context around a selected Melbourne coordinate
SELECT layer, feature_id, distance_m, observed_on, properties, geometry_geojson
FROM get_environment_context(
    144.9631,
    -37.8136,
    500,
    ARRAY['trees', 'heat'],
    1000
);

-- The same bounded context starting from an unambiguous address
SELECT layer, feature_id, distance_m, observed_on, properties, geometry_geojson
FROM get_environment_context_by_address(
    '1 COLLINS STREET MELBOURNE 3000',
    500,
    ARRAY['trees', 'heat'],
    1000
);
```
