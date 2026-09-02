# GreenChanger Data Contract and Deployment Notes

## Review scope

This change covers the data component only: source ingestion, validation,
PostgreSQL/PostGIS migrations, application-ready spatial lookup functions and
evidence-bounded analytical outputs. Frontend rendering and backend HTTP route
handling remain separate team components.

## Application-facing database functions

| Function | Purpose | Contract and scope |
| --- | --- | --- |
| `get_environment_context(longitude, latitude, radius_m, layers, result_limit)` | Returns nearby mapped-tree points and clipped Landsat heat cells. | EPSG:4326 input is transformed to EPSG:7855; Melbourne boundary required; radius `(0, 2000]` m; layers are `trees` and/or `heat`; limit `1–2000` applies independently per layer. |
| `get_environment_context_by_address(address, radius_m, layers, result_limit)` | Normalises supported street abbreviations, resolves one Vicmap address and delegates to the coordinate function. | `RD` is expanded to `ROAD`; missing, unmatched and ambiguous searches are rejected. An exact full-address match is preferred. |
| `get_property_baseline(address, result_limit)` | Joins application-ready address, parcel, Landsat, canopy, tree and recent BOM context. | Returns source/version details and limitations; BOM air temperature remains separate from Landsat land-surface temperature. |
| `classify_environmental_value(metric, value, version)` | Applies an active, versioned Melbourne-relative tercile scheme to comparable baseline cells. | `Low/Medium/High` are relative rank groups, not health or safety categories. Missing data returns `Unavailable`. |
| `classify_melbourne_daily_mean_air_temperature(maximum, following_minimum)` | Returns structured context for the retired Victorian Central District 30°C daily-mean threshold. | Returns JSON metadata with `status: historical_context`; it is never a current BOM warning. The 27.2°C research percentile is metadata only because it requires at least two consecutive days. |
| `classify_canopy_benchmark(canopy_percentage)` | Compares a validated analytical canopy percentage with the official 15.3% metropolitan baseline and 30% urban target. | Progress context only; prohibited for the rendered canopy proxy and not property-level compliance. |

## Classification scope

Three distinct measures must never be mixed:

1. Landsat land-surface temperature is classified only by versioned Melbourne
   terciles calculated from comparable application-ready cells.
2. BOM observations are air temperature from a named station, timestamped and
   distance-labelled. They are not property temperature or Landsat LST.
3. The retired Victorian 30°C daily-mean method is historical context. It does
   not produce `Low`, `Medium` or `High`, and is not a current warning.

The 27.2°C value from Tong et al. is a Melbourne 95th-percentile research
threshold defined for at least two consecutive summer days. Because the helper
accepts one maximum/following-minimum pair, migration 021 explicitly prevents
27.2°C from being used as a one-day category boundary.

## Migration and deployment order

Never edit a migration already recorded in `schema_version`. Apply the numbered
files in order:

- 001–017: core schema, sources, spatial assets, baselines, scenario evidence,
  multi-station weather and Melbourne-relative classifications.
- 018: bounded coordinate/radius context function.
- 019: address-resolving context wrapper.
- 020: sourced absolute reference records and original helpers.
- 021: forward-only correction that converts historical temperature output to
  structured JSON and records the 27.2°C duration requirement.
- 022: missing query/foreign-key indexes and supported Australian street-type
  abbreviation expansion for address lookup.

Check and deploy to the shared database:

```bash
python greenchanger_script/migrate.py --status
python greenchanger_script/migrate.py --confirm-shared
python greenchanger_script/migrate.py --status
```

Migration 021 changes the SQL helper return type from `TEXT` to `JSONB`. Backend
consumers must read `classification`, `daily_mean_c`, `method`, `status`,
`limitation`, `source` and `historical_percentile_context` from the returned
object. Deploy the database migration before deploying a consumer expecting the
new contract.

## Data versions and provenance

- `dataset_source` stores publisher, source URL, licence and access method.
- `dataset_version` stores extraction/observation dates, checksum, quality,
  integration/publication status, Melbourne scope and derivation method.
- `schema_version` stores migration filename and SHA-256 checksum.
- `environmental_classification_scheme` and
  `environmental_classification_threshold` bind terciles to exact heat/canopy
  dataset-version IDs. The current documented label is
  `melbourne-terciles-v1`; a changed baseline requires a new label rather than
  overwriting v1.
- `environmental_classification_reference` stores threshold evidence, source
  locator, limitation, role, duration requirement and historical status.
- `config/environmental_classification_evidence.json` is versioned as
  `historical-context-and-canopy-benchmarks-v2`, superseding the unsafe v1
  one-day interpretation.

Do not assume a migration or data version is deployed from repository contents.
Confirm it with `migrate.py --status` and the database queries in the README.

## Validation commands

Run fast tests:

```bash
python -m unittest discover -s tests -v
python greenchanger_script/sanity_check_melbourne.py
python greenchanger_script/run_residential_greening_scenarios.py
```

Run real PostgreSQL/PostGIS contract tests:

```bash
docker compose -f docker-compose.integration.yml up -d --wait
export GREENCHANGER_TEST_DATABASE_URL='postgresql://greenchanger_test:greenchanger_test@127.0.0.1:55432/greenchanger_test'
python -m unittest tests.test_postgis_integration -v
docker compose -f docker-compose.integration.yml down -v
```

The integration suite applies every migration to an isolated schema and
executes both context functions. It checks an exact and ambiguous address,
inside/outside-boundary coordinates, invalid radius, unsupported layers and the
per-layer limit. It also executes the structured historical-temperature helper.

The same suite is required by the GitHub Actions
`GreenChanger PostGIS / Apply migrations and execute PostGIS contracts` job in
`.github/workflows/greenchanger-postgis.yml`. It runs for pull requests that
change `GreenChanger_data`, relevant pushes to `main` or `greenchanger-ds`, and
manual workflow dispatches.

## Known limitations

- The current canopy baseline is a rendered API proxy at approximately 19.1 m
  source resolution, aggregated to 500 m neighbourhood cells. It is unsuitable
  for individual-tree or property canopy measurement and cannot be passed to
  the absolute canopy helper.
- Landsat measures land-surface temperature, not the air temperature a resident
  experiences. Scene date, cloud filtering and seasonal comparability matter.
- BOM is recent station context only. Values over 25 km away are suppressed;
  observations older than three hours are unavailable.
- Vicmap Tree Urban is machine-derived 2019–2020 mapping, not a current field
  survey. Zero mapped points never proves that no tree exists.
- Address prefix searches may be ambiguous. The database rejects ambiguity
  instead of silently selecting a property.
- Intervention temperature outputs are evidence-bounded indicative ranges, not
  guaranteed before/after temperatures or a trained machine-learning model.
- Cost figures are source-dated estimates and must be shown as ranges, not
  quotations.

## Deployment checklist

- Review `git diff` and confirm no raw data or credentials are staged.
- Run all fast tests and the PostGIS integration suite.
- Confirm active source and baseline version IDs in the target database.
- Apply migrations in order; never use `--baseline` for an unverified database.
- Verify migration 021 returns JSONB and 27.2°C is not a one-day category.
- Coordinate backend consumers with the return-type change.
- Retain the resident-facing measurement labels, sources and limitations.
- Schedule migration 022 during a low-write period because building indexes on
  multi-million-row address, parcel and tree tables can temporarily increase
  database load and lock writes.
