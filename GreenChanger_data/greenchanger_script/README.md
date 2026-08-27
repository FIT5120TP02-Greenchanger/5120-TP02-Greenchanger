# `greenchanger_script` commands

This folder contains command-line entry points for operating the GreenChanger
data component. Run commands from the `GreenChanger_data/` project root with the
virtual environment active.

## Initial setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python greenchanger_script/check_source_registry.py
python -m unittest discover -v
```

For the shared Aurora database, AWS credentials must be available and writes
require the explicit `--confirm-shared` flag. Secrets are never stored in this
repository.

## What is inside

| File | Use |
| --- | --- |
| `__init__.py` | Marks this directory as the command package and supports imports shared by scripts and tests. |
| `db.py` | PostgreSQL connection settings, local-password handling and shared Aurora IAM-token generation. |
| `migrate.py` | Apply, inspect or baseline numbered SQL migrations. Shared reset is prohibited. |
| `ingestion.py` | Unified source, boundary, BOM, cost, canopy, heat, address, property and mapped-tree ingestion jobs. |
| `check_source_registry.py` | Validate source configuration and print target SRID/quality threshold. |
| `extract_bom.py` | Download and normalise the BOM feed without loading the database. |
| `extract_vicmap_canopy_api.py` | Create the documented lower-resolution Vicmap canopy tile proxy. |
| `inspect_canopy.py` | Inspect raster CRS, bands, values and dimensions before ingestion. |
| `prepare_vector.py` | Repair/reproject/clip a general vector source. |
| `validate_csv.py` | Apply configured quality rules to a staging CSV and write rejected rows. |
| `calculate_measures.py` | Calculate Data Analytics & Insight Development outputs or print all formulas with sample results. |
| `validate_intervention_model.py` | Run source-linked intervention cases and update model status only after every case passes. |
| `sanity_check_melbourne.py` | Print real-address parcel, heat, canopy and mapped-tree outputs across six representative Greater Melbourne scenarios. |
| `clip_to_melbourne.py` | Create audited `2GMEL`-only Address, Property, heat and canopy dataset versions without deleting parent versions. |
| `build_heat_baseline.py` | Resolve overlapping Landsat observations into one versioned, application-ready baseline cell per location. |
| `build_canopy_baseline.py` | Publish one quality-checked, versioned 500 m canopy baseline and verify exact alignment with the heat grid. |
| `apply_database.py` | Legacy/simple schema application helper; numbered migrations are preferred. |

## Recommended run order

```bash
# 1. Check configuration and code
python greenchanger_script/check_source_registry.py
python -m unittest discover -v

# 2. Inspect and apply database migrations
python greenchanger_script/migrate.py --status
python greenchanger_script/migrate.py --confirm-shared

# 3. Synchronise source definitions
python greenchanger_script/ingestion.py sources --confirm-shared

# 4. Load the official ABS 2026 Greater Melbourne GCCSA boundary
python greenchanger_script/ingestion.py boundary --confirm-shared

# 5. Load current address and property data
python greenchanger_script/ingestion.py address --confirm-shared
python greenchanger_script/ingestion.py property --confirm-shared

# Load mapped individual-tree context from the official Tree Urban API
python greenchanger_script/ingestion.py trees --confirm-shared

# Create application-ready Greater Melbourne-only derived versions
python greenchanger_script/clip_to_melbourne.py --confirm-shared

# Deduplicate overlapping Landsat scenes into the baseline heat mosaic
python greenchanger_script/build_heat_baseline.py --confirm-shared

# Publish the matching 500 m canopy baseline
python greenchanger_script/build_canopy_baseline.py --confirm-shared

# After migration 010, test the application-ready property lookup in psql
# SELECT * FROM get_property_baseline('1 COLLINS STREET MELBOURNE', 5);

# 6. Load the remaining prepared sources as required
python greenchanger_script/ingestion.py bom --confirm-shared
python greenchanger_script/ingestion.py costs \
  --cost-file data/reference/cost_estimates.csv --confirm-shared

# 7. Verify migration state and rerun tests
python greenchanger_script/migrate.py --status
python -m unittest discover -v
```

Use a previously completed Vicmap raw extract without downloading again:

```bash
python greenchanger_script/ingestion.py address \
  --address-file data/raw/vicmap/address_TIMESTAMP.jsonl.gz \
  --confirm-shared

python greenchanger_script/ingestion.py property \
  --property-file data/raw/vicmap/property_TIMESTAMP.jsonl.gz \
  --confirm-shared

python greenchanger_script/ingestion.py trees \
  --urban-tree-file data/raw/vicmap/urban_tree_TIMESTAMP.jsonl.gz \
  --confirm-shared
```

Override the project bbox only when the team has approved a different extent:

```bash
python greenchanger_script/ingestion.py address \
  --vicmap-bbox WEST SOUTH EAST NORTH --confirm-shared
```

## What `ingestion.py` does

For each dataset it registers/fetches the source, preserves raw data, computes a
checksum, creates a `dataset_version`, applies the configured quality rules,
records rule-level outcomes, rejects failed rows, inserts accepted rows in
bounded batches, transforms spatial data into EPSG:7855 and marks only a
successful version as `application_ready`.

## Greater Melbourne boundary filtering

`clip_to_melbourne.py` uses the official ABS ASGS 2026 GCCSA `2GMEL` stored in
`analysis_area`. Migration 007 subdivides the complex boundary into indexed
pieces for efficient multi-million-row spatial filtering. Address points must
be inside the boundary, property polygons may intersect it, and the centroids
of heat/canopy grid cells must be inside it. Each output is a new
`dataset_version` linked to its parent and transformation audit record. Running
the command again is idempotent and reports the completed outputs.

`build_heat_baseline.py` averages only same-day scene overlaps, then selects
the latest valid date for each grid cell. It does not average temperatures from
different acquisition dates. The resulting view is
`latest_greater_melbourne_heat_baseline`.

`build_canopy_baseline.py` retains zero-canopy cells, verifies percentages,
geometry, uniqueness, Greater Melbourne coverage and exact matching of every
current heat-baseline cell. Its `coverage_confidence_pct` means complete raster
coverage only; it is not classification or positional accuracy. The current
official rendered-tile proxy is labelled `api_tile_proxy` and is appropriate
for 500 m summaries, not property-level tree-crown decisions. Replace it with
the original analytical GeoTIFF when obtained through the DataVic order flow.

Migration 010 provides `get_property_baseline(text, integer)` for the prototype.
It performs a prefix address search, joins Vicmap Address to Vicmap Property by
the source property identifier, and attaches current heat and canopy baselines
spatially. Blank searches return no rows and the result limit is constrained to
1–50. Missing property or environmental matches are returned with an explicit
partial quality status instead of being silently dropped.

The default BOM job downloads the ten official station feeds in
`config/bom_stations.json`, rejects identity mismatches, preserves one combined
raw document, applies the 95% record-quality gate and publishes one dataset
version. The registry covers central, western, northern, eastern,
southeastern, bayside and Frankston/Mornington Melbourne. `--bom-url` remains a
single-feed diagnostic override; its dataset version is kept `internal` and
cannot replace the application-ready multi-station context.

Migration 016 makes the property lookup eligible for only observations no older
than three hours. At most 10 km is `good_local_context`; 10–25 km is
`regional_context_warning`; beyond 25 km temperature is suppressed; and no
eligible observation is explicitly unavailable. Station name, time and distance
remain traceable. The lookup returns Landsat land-surface temperature and BOM
station air temperature as separate fields. Canopy from the proxy is labelled
`neighbourhood_500m`; property canopy percentage is null. The `trees` job uses
the official Tree Urban Feature Service to add mapped tree counts and dimensions
without claiming that they are a current field survey.

The `trees` job uses adaptive API tiles, preserves a reusable gzip JSON Lines
extract, applies the record-quality gate, bulk-stages accepted records with
PostgreSQL `COPY`, and publishes only points covered by the official ABS 2026
`2GMEL` boundary. Optional canopy radius is limited to 0.25–50 m and height to
0.5–100 m; outlying measurements become null while the mapped point is retained.

Application code must read analytical outputs through
`application_ready_measure_result`. That view excludes draft, prototype-only
and in-validation models. For temperature measures it also checks the separate
precision gate, preventing a model validated only for ranges from exposing a
precise after-temperature.

Inspect the selected research and its usage restrictions after migration 014:

```sql
SELECT citation_key, intervention_types, outcome_types, transferability,
       approved_use, prohibited_use
FROM selected_intervention_evidence
ORDER BY publication_year;
```

Print the shade-proxy example and the deliberately suppressed temperature
example:

```bash
python greenchanger_script/calculate_measures.py --sample
```

Validate the four intervention types without database writes:

```bash
python greenchanger_script/validate_intervention_model.py
```

Persist the complete case report and promote the range model only after all
tests pass:

```bash
python greenchanger_script/validate_intervention_model.py \
  --update-status --confirm-shared
```

Print the six real Melbourne geographic sanity checks:

```bash
python greenchanger_script/sanity_check_melbourne.py
```

The default scenarios cover the CBD, inner suburbs, western and northern growth
areas, eastern suburbs, southeastern suburbs, and the project-defined small,
medium and large lot categories. `WARN` is an inspectable caveat rather than a
failed join; `FAIL` means a required match, range, boundary or measurement label
did not pass. Use `--json` for a machine-readable report or `--scenario
EAST_LARGE` for one case. Add `--fail-on-warning` only when warnings should fail
an automated pipeline.

Migration 015 must be applied first. A failing case exits non-zero, records the
failure when `--update-status` is used, and keeps the model at
`validation_in_progress`.

The shared database write is one transaction per named job. If a command raises
an exception, it rolls back its database work. Large API extracts are reusable
files, so an insertion retry can use `--address-file` or `--property-file`.

The cost file is reviewed evidence rather than scraped application state. Run
`validate_csv.py cost_estimate data/reference/cost_estimates.csv` before its
ingestion job. Each record has a three-month validity window, source reference,
inclusion flags and confidence label. Blank delivery, setup, GST or maintenance
fields mean the source did not publish a reliable value; they must not be
interpreted as zero.

## Failure guide

| Symptom | Cause and response |
| --- | --- |
| `PENDING 005_vicmap_address_property.sql` | Apply migrations before address/property ingestion. |
| Missing AWS dependency | Activate `.venv` and run `python -m pip install -r requirements.txt`; `botocore[crt]` is required for AWS login credentials. |
| Refusal to write shared DB | Review the target, then add `--confirm-shared`. Do not bypass this protection in code. |
| Vicmap timeout | The extractor retries automatically. Do not stop it merely because one polygon tile is slow. |
| `.partial` Vicmap file | Extraction did not complete. Do not pass it to `--address-file`/`--property-file`. |
| Quality gate failed | Inspect `data_quality_run`, `data_quality_result` and the configured rules; correct or quarantine source rows before retrying. |
| BOM `IndeterminateDatatype` | Geometry placeholders must keep explicit PostgreSQL casts (`%s::text`, `%s::integer`). This is fixed in the current loader. |
| Multi-station BOM quality below 95% | Inspect failures by station. A wind-only or partially populated feed must not be treated as an air-temperature station; replace it with the correct official temperature feed rather than weakening `WEATHER_REQUIRED`. |
| Landsat TIFF is HTML/unsupported | Do not reuse it. Current code signs Planetary Computer URLs and validates downloaded raster content. |
| Canopy source value is ambiguous | Run `inspect_canopy.py`; never infer the tree class from display colours. |

## Safety

- `migrate.py --reset` works only against a local host.
- Never commit `.env`, AWS credentials or raw source data.
- Do not edit an applied migration; create the next numbered migration.
- Do not label Landsat land-surface temperature as BOM air temperature.
- Do not present modelled heat reduction or cost ranges as guarantees.
