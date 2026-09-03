# `greenchanger_data` package

This package contains reusable extraction, cleaning, validation and calculation
logic for the GreenChanger data component. Code here does not connect to the
database directly; commands in `greenchanger_script/` orchestrate these
functions and perform database writes.

## What is inside

| File | Responsibility |
| --- | --- |
| `__init__.py` | Marks this directory as the reusable `greenchanger_data` Python package. |
| `boundary.py` | Download, preserve and normalise the official ABS ASGS 2026 Melbourne GCCSA boundary. |
| `bom.py` | Validate the Melbourne station registry, independently download official BOM feeds, preserve per-station failures, verify feed identity, flatten and normalise observations. |
| `canopy.py` | Inspect and aggregate a binary tree-extent raster into Melbourne grid summaries. |
| `canopy_baseline.py` | Define versioned baseline and source-provenance rules, including analytical-versus-proxy classification. |
| `classification.py` | Apply fixed 27°C/30°C temperature display bands, versioned Melbourne-relative canopy thresholds and separate historical/evidence helpers, with explicit missing-data handling. |
| `landsat.py` | Search Landsat Collection 2, sign/download assets, mask unusable pixels and calculate land-surface temperature. |
| `heat_baseline.py` | Define and reference-test the latest-date/same-day-overlap baseline mosaic rule. |
| `intervention_model.py` | Load source-backed action parameters, calculate non-guaranteed impact ranges and evaluate published-evidence cases. |
| `measures.py` | Evidence-gated calculations and sample outputs for canopy, future shade proxy, greenery, surface heat and cost measures. |
| `melbourne_sanity.py` | Validate real-address parcel, Melbourne boundary, heat, analytical property canopy, 500 m neighbourhood canopy, mapped-tree and weather-context outputs without requiring a database in unit tests. |
| `property_baseline.py` | Reference-test the project-defined small, medium and large lot-size categories used by Priority 4. |
| `property_canopy.py` | Validate fine-resolution analytical canopy and calculate parcel-clipped canopy area, percentage and raster coverage without treating nodata as zero. |
| `quality.py` | Record-level completeness, uniqueness, validity and consistency rules, including memory-safe stream validation. |
| `residential_scenarios.py` | Join real property baselines to four-action calculations and reviewed cost evidence while preserving measurement scope and warnings. |
| `scenario_inputs.py` | Validate the versioned Residential Greening Scenario Simulation quantity, area, maturity, survival and suitability contract and translate it into evidence-bounded model inputs. |
| `sources.py` | Load the source registry and calculate reproducibility checksums. |
| `spatial.py` | Read, repair, reproject, clip and write general vector datasets. |
| `vicmap_features.py` | Extract, clean and normalise current Vicmap Address, Property and Tree Urban features from official ArcGIS APIs. |
| `vicmap_tiles.py` | Build a georeferenced Vicmap Tree Extent proxy from official cached map tiles. |

## Standard preparation flow

1. Extract from the official source and preserve the unmodified response or a
   lossless normalised raw file.
2. Record source URL, source edit/observation date, extraction timestamp,
   bounding box, CRS, row count and SHA-256 checksum.
3. Standardise names, numeric values, dates, units and missing values.
4. Check required fields, business-key uniqueness, ranges and geometry.
5. Quarantine failed records before integration.
6. Transform accepted geometry into EPSG:7855 during the database load.
7. Save the quality run, rule results and known limitations.

## Canopy baseline preparation

The Melbourne-clipped Tree Extent observations are published as a separate,
immutable 500 m baseline version. Zero-canopy cells are retained. Required
values, 0–100 percentages, EPSG:7855 polygon validity, cell uniqueness and
official `2GMEL` centroid membership are checked before publication. A final
consistency rule requires every current heat-baseline geometry to have an exact
canopy match.

The current asset role `canopy_api_tile_mosaic` maps to `api_tile_proxy`; it is
never labelled as an analytical GeoTIFF. `coverage_confidence_pct` describes
complete source-raster coverage, not classification accuracy. The source's
multi-year imagery period and proxy resolution are recorded as limitations.

Property canopy is a separate evidence scope. It accepts only a registered
`canopy_analytical_geotiff` with one band, projected coordinates and pixels no
larger than 2 m. Each Vicmap parcel is the clip mask; tree-class pixel area is
divided by parcel area and raster coverage is reported separately. Rows below
95% raster coverage return `Unavailable`, not 0%. The current 19.109 m rendered
API mosaic cannot satisfy this contract.

When available, the parcel result populates `property_canopy_percentage` and
uses scope `property_raster_clip`; it does not replace or reclassify the 500 m
neighbourhood canopy baseline.

## Environmental classification logic

`classification.py` supports fixed temperature display bands and versioned
Melbourne canopy tercile schemes. The deployed canopy proxy baseline remains
`melbourne-terciles-v1`; after the analytical tile-wise
baseline passes its quality gate, it must be published separately as
`melbourne-terciles-v2`. Canopy uses the 33.33rd and 66.67th percentiles of the
application-ready Melbourne cells. Temperature uses fixed product display
bands:

| Metric | Low | Medium | High | Distribution |
| --- | --- | --- | --- | --- |
| Temperature display band | ≤27°C | >27°C and ≤30°C | >30°C | Counts depend on the source values |
| Canopy | ≤28.8% | >28.8% and ≤73.533333% | >73.533333% | 12,384 / 12,380 / 12,382 |

Inclusive boundary handling is intentional: 27°C belongs to `Low`, and 30°C
belongs to `Medium`. Null or non-finite temperature measurements return
`Unavailable`. Absent canopy cells and missing active canopy thresholds also
return `Unavailable`; they are never treated as environmental `Low`. A
replacement canopy baseline requires a new scheme version and review rather
than mutation of v1.

The separate historical/evidence helpers do not redefine the product bands.
`classify_melbourne_daily_mean_air_temperature()` uses a forecast maximum and
the following overnight minimum and returns a structured historical-context
object, not `Low/Medium/High` or a current warning. The 27.2°C research value
requires two consecutive days and is metadata only. It never categorises a
single current BOM observation or Landsat surface temperature.
`classify_canopy_benchmark()` uses
the official 15.3% metropolitan baseline and 30% urban-area target but is
prohibited for the current rendered canopy proxy. Exact sources and document locations are recorded in
`config/environmental_classification_evidence.json` and migrations 020–021.

## Property baseline integration

Priority 4 uses the source-defined Address–Property relationship first, then
spatially matches the selected parcel point-on-surface to current 500 m heat
and canopy cells. The database lookup returns WGS84 coordinates and GeoJSON for
the parcel and environmental cells, observation dates, source types, a combined
quality status and explicit limitations.

Lot-size categories are project interface assumptions: small is below 400 m²,
medium is 400–800 m² inclusive, and large is above 800 m². They are not
statutory planning classifications.

The same lookup keeps three different evidence scopes separate:

- Tree Extent proxy: neighbourhood canopy percentage at 500 m only.
- Tree Urban points: mapped individual-tree context after the `trees` ingestion
  job; still machine-derived rather than a field inventory.
- Temperature: Landsat land-surface temperature and BOM station air temperature
  are separate named fields with their own time and spatial metadata.

The BOM registry is `config/bom_stations.json`. It contains ten station codes,
official source URLs and coverage roles. Feed station identity must match the
registry before rows are combined. Air-temperature records require station
name, timestamp, temperature and coordinates; a wind-only feed cannot pass the
weather quality gate.

A failure from one official station endpoint no longer discards valid data from
all other stations. The raw extraction records successful and failed feeds,
station coverage is stored on `dataset_version`, and partial availability is
recorded in `data_limitation`. At least 80% of configured stations must load
before a multi-station version can become application-ready; record-level
completeness and validity must still satisfy the separate 95% quality gate.

Tree Urban cleaning retains points with valid identifiers and locations while
suppressing optional machine-derived canopy radii outside 0.25–50 m and heights
outside 0.5–100 m. The current API version suppressed 172,179 height outliers;
no canopy-radius outliers were found. This transformation is recorded in
`transformation_run`, and the original compressed API extract remains available
for audit.

Unvalidated heat arithmetic is retained only for internal test cases. The
display-safe calculation separates `validation_status` from `output_precision`.
A validated indicative-range model still returns no precise after-temperature;
an exact value requires explicit `precise_point_estimate` approval.

`projected_canopy_proxy_shade_m2` discounts a supplied future crown area by
survival probability, site suitability and canopy overlap. The output includes
a maturity horizon and is deliberately labelled as a canopy proxy rather than
a sun-angle shadow measurement. No generic literature maximum is used as a
temperature coefficient.

The versioned four-action registry is
`config/intervention_model_parameters.json`. Trees, garden beds and green walls
retain distinct outcome scopes. Potted plants deliberately return no
temperature output. `evaluate_validation_cases` compares only expected subsets,
so audit fields and disclaimers may be added without weakening the scientific
checks.

The separate `config/residential_greening_simulation_inputs.json` file defines the scenario
input contract. `scenario_inputs.py` requires positive whole-number quantities
and maturity horizons, ordered probability/suitability ranges between zero and
one, and action-specific area fields. It locks the Iteration 1 tree quantity to
one, aggregates per-unit areas, applies survival and site-suitability uncertainty
before calling the evidence-bounded impact model, and retains the contract
version in every output. Missing required inputs raise a validation error so the
application can display `Unavailable` instead of inventing a result.

Only the tree example has a published prototype size range: 6.6–43.7 m² crown
area at 10 years across Melbourne species/rainfall cases
([Torquato et al. 2024](https://doi.org/10.1016/j.ufug.2024.128268)). Other
example dimensions are calculation fixtures rather than recommended defaults.

`residential_scenarios.py` uses real parcel area as the denominator for tree and
garden-bed land-unit heat ranges. It never adds an action's m² output to the
500 m neighbourhood canopy percentage. Costs are scaled using their source
basis (`per_tree`, `per_pot` or `per_m2`) and retain source, confidence and
validity metadata. Output checks cover ordered ranges, supported temperature
scope, potted-plant suppression, the exact-temperature prohibition and cost
arithmetic. Passing these checks does not establish a causal cooling effect.

## Vicmap Address and Property processing

The project boundary is the official ABS ASGS 2026 Melbourne GCCSA,
code `2GMEL`. Boundary ingestion checks its code, name, year, positive area and
polygon geometry, and preserves the raw ABS GeoJSON for reproducibility.

The default project extent is `144.4,-38.5,146.0,-37.4` in EPSG:4326. It is a
project bounding box, not an official Melbourne administrative polygon.

### Extraction and cleaning

- Query the official Vicmap ArcGIS Feature Service using spatial tiles.
- Recursively subdivide any response that reaches the 2,000-feature API cap.
- Use ordered `OBJECTID` pagination when many unit addresses share the same
  location and spatial subdivision cannot reduce the response.
- Deduplicate features by source `OBJECTID`, because polygons can intersect
  more than one tile.
- Write to `.partial` first and atomically promote the gzip JSON Lines file only
  after the whole extent completes.
- Preserve `pfi`, `property_pfi`, address text, locality, postcode and address
  attributes for Vicmap Address.
- Preserve `prop_pfi`, council property number, property type/status, LGA code,
  reported area and complete geometry for Vicmap Property.
- Repair invalid polygon geometry with Shapely `make_valid` and standardise all
  accepted polygons to `MultiPolygon`.

### Quality rules

Address records must contain `source_address_id`, `full_address` and geometry,
and `source_address_id` must be unique. Property records must contain
`source_parcel_id` and geometry, `source_parcel_id` must be unique, and a
reported area—when present—must be greater than zero.

The validator reads compressed records as a stream, retaining only uniqueness
keys and failed indices. This prevents millions of polygon WKT strings from
being held in memory. The quality gate uses the unrounded percentage; displayed
and database percentages are rounded to two decimal places.

### Address–property join

`address.source_property_id` is Vicmap Address `property_pfi`.
`parcel.source_parcel_id` is Vicmap Property `prop_pfi`.
These fields form the source-defined relationship. Do not join an address
property PFI to a Vicmap Parcel PFI, because they are different identifier
domains.

## Failures handled

| Failure | Handling/fix |
| --- | --- |
| ArcGIS response reaches 2,000 records | Discard the capped response and subdivide the tile. |
| More than 2,000 colocated unit addresses | Use stable `OBJECTID` pagination at the minimum tile size. |
| Transient API timeout | Retry with bounded exponential backoff; never skip the tile. |
| Process/API failure during extraction | Keep only a `.partial` file; do not register or integrate it. |
| Polygon crosses several tiles | Deduplicate by `OBJECTID`. |
| Invalid polygon/ring | Run `make_valid`, retain polygonal parts and convert to `MultiPolygon`. |
| Missing required value or duplicate business key | Mark the record failed and exclude it from insertion. |
| Zero/negative reported property area | Reject through `PARCEL_AREA_POSITIVE`. |
| Address has no matching accepted property | Retain the address, exclude unavailable property analytics and document the limitation. |
| Tree Extent source is only a rendered proxy | Publish neighbourhood canopy only and suppress property canopy percentage. |
| Whole analytical VRT aggregation is interrupted | Resume from the atomic per-tile checkpoint; never restart completed tiles. |
| Property-canopy batch is interrupted | Resume the same internal output version; application views ignore it until all parcels and the 95% gate pass. |
| Tree Urban API times out during a large extract | Retry/subdivide tiles, preserve `.partial`, and resume using a completed raw extract only. |
| Heat model has not passed validation | Suppress precise projected temperature and reduction in application output. |
| Study measures air, wall or globe temperature rather than Landsat LST | Retain the evidence for its named outcome only; prohibit cross-metric coefficient reuse. |
| Study reports a maximum cooling effect | Store it as a reported effect and plausibility bound, never as the default prediction. |

## Tests

Run all package and pipeline tests from the project root:

```bash
python -m unittest discover -v
```

The tests cover normalisation, cross-record uniqueness, the unrounded quality
gate, geometry conversion, BOM extraction, raster checks, migration history,
classification boundaries/missing/non-finite values, scenario-input constraints,
real-property scenario output checks and analytical calculations. The current
suite contains 98 tests.
