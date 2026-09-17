# GreenChanger Data Component

GreenChanger is the data component for a Melbourne-wide application that helps residents compare greening actions for their properties. This repository covers data sourcing, preparation, quality assurance, spatial integration, analytical measures and database delivery. It does not implement the frontend or the complete backend application.

## The three main folders

| Folder | Purpose | Detailed reference |
| --- | --- | --- |
| `greenchanger_data/` | Reusable extraction, normalisation, spatial processing, quality and calculation functions. These modules do not write directly to the database. | [`greenchanger_data/README.md`](greenchanger_data/README.md) |
| `greenchanger_script/` | Commands for setup, migration, API ingestion, Melbourne clipping, baseline construction, validation and calculations. | [`greenchanger_script/README.md`](greenchanger_script/README.md) |
| `greenchanger_sql/` | PostgreSQL/PostGIS schema, forward-only migrations, reference seeds and application-facing views/functions. | [`greenchanger_sql/README.md`](greenchanger_sql/README.md) |

Supporting folders are `config/` for source definitions and quality rules, `data/` for ignored raw/interim/processed artifacts, and `tests/` for automated data-component tests.

## Data workflow

```text
Official source/API
        ↓
Preserved raw extract + checksum + source metadata
        ↓
Normalisation and CRS/unit/date standardisation
        ↓
Completeness, validity, consistency and uniqueness checks
        ↓
Official ABS 2026 Melbourne (2GMEL) boundary filter
        ↓
PostgreSQL 17 + PostGIS integration
        ↓
Versioned application-ready views and property lookup
```

**Data Quality & Preparation** requires at least 95% of assessed records to pass the configured completeness, validity and consistency checks. Failed records are rejected or quarantined, and limitations are retained in the database. **Data Analytics & Insight Development** covers the analytical measures presented to users. Its calculations separate observed values from modelled scenarios and expose precise projected heat results only from validated model versions.

## Experimental mature canopy-width model

From the project root, create/activate the environment and install the model
dependency with:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Train the internal benchmark and print the train/test row counts, held-out R²,
MAE and RMSE with:

```bash
python greenchanger_script/train_tree_canopy_model.py
```

The default run uses a reproducible 80/20 split. The fitted artifact contains
only the 80% training partition; the 20% test partition remains untouched. The
model and machine-readable metrics are written to:

```text
data/processed/models/tree_canopy_width/mature_canopy_width_model.joblib
data/processed/models/tree_canopy_width/metrics.json
```

List the tree types that support automatic inputs:

```bash
python greenchanger_script/predict_tree_canopy.py --list-species
```

Choose one supported type to automatically fill representative mature height,
DBH, health, structure, useful-life class and training-area location:

```bash
python greenchanger_script/predict_tree_canopy.py \
  --species "River Red Gum"
```

When current canopy width is omitted, the command treats the selection as a new
tree with 0 m² current canopy. The JSON response lists every auto-filled input
and the assumption. User-supplied measurements always override the profile.

For example, run the model with explicit measurements and property location:

```bash
python greenchanger_script/predict_tree_canopy.py \
  --species "River Red Gum" \
  --height-m 8 \
  --dbh-cm 30 \
  --current-canopy-width-m 3 \
  --health "Good" \
  --structure "Good" \
  --useful-life "20-30 years" \
  --longitude 144.66 \
  --latitude -37.90
```

The command prints JSON containing `predicted_mature_canopy_width_m`,
`current_canopy_area_m2`, `predicted_mature_canopy_area_m2`,
`predicted_added_canopy_m2`, `model_held_out_test_r2` and
`model_unseen_species_r2`, plus the model timestamp and limitation. R² is a
model-level evaluation metric, not confidence for the individual prediction.
Height or DBH is required; supply both when available. Longitude and latitude
are optional but must be provided together.

The equivalent Python API is:

```bash
python - <<'PY'
import joblib

from greenchanger_data.tree_canopy_model import predict_canopy

artifact = joblib.load(
    "data/processed/models/tree_canopy_width/"
    "mature_canopy_width_model.joblib"
)

result = predict_canopy(
    artifact["model"],
    species_name="River Red Gum",
    height_m=8,
    diameter_breast_height_cm=30,
    current_canopy_width_m=3,
    health_status="Good",
    structure_status="Good",
    useful_life_expectancy="20-30 years",
    longitude=144.66,
    latitude=-37.90,
)

for name, value in result.items():
    print(f"{name}: {value:.2f}")
PY
```

Use exact Wyndham inventory species/common-name labels where possible. An
unknown species can be scored because the model handles it explicitly, but that
estimate relies more heavily on the other measurements and should be treated
with greater caution.

The trainer uses the open Wyndham inventory records explicitly labelled
`Mature` or `Over mature`. It predicts observed mature crown width with
categorical boosting from species, height, DBH, health, structure, remaining
useful-life category and location. It also reports a stricter complete-species
holdout diagnostic. The saved artifact is fitted only on the training partition;
the test partition remains untouched. Mature crown area is derived as
`π × (width / 2)²`, and added canopy is mature area minus current area, floored
at zero. This is a cross-sectional benchmark, not longitudinal growth evidence or a production
forecast; the existing validation gate remains in force.

## Initial setup

Run commands from the `GreenChanger_data/` project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python greenchanger_script/check_source_registry.py
python -m unittest discover -v
```

The shared Aurora database uses AWS IAM authentication. Sign in before database commands:

```bash
aws login
aws sts get-caller-identity
```

Do not store AWS keys, database passwords or `.env` secrets in the repository.

## Complete run order

The following sequence builds the data component from an empty database. Shared-database writes deliberately require `--confirm-shared`.

```bash
# 1. Apply and inspect the PostgreSQL/PostGIS schema
python greenchanger_script/migrate.py --status
python greenchanger_script/migrate.py --confirm-shared

# 2. Register sources and load the official Melbourne boundary
python greenchanger_script/ingestion.py sources --confirm-shared
python greenchanger_script/ingestion.py boundary --confirm-shared

# 3. Load current Vicmap Address, Property and authoritative LGA boundaries
python greenchanger_script/ingestion.py address --confirm-shared
python greenchanger_script/ingestion.py property --confirm-shared
python greenchanger_script/ingestion.py lga-boundaries --confirm-shared

# Load one source-controlled council planting guide at a time. Start from
# data/reference/council_species_guidance_template.csv and retain its source,
# licence, effective dates and limitation text.
python greenchanger_script/ingestion.py council-guidance \
  --council-guidance-file /path/to/official_council_guidance.csv \
  --confirm-shared

# 4. Load weather, Landsat surface heat and Vicmap canopy
python greenchanger_script/ingestion.py bom --confirm-shared
python greenchanger_script/ingestion.py heat --confirm-shared
python greenchanger_script/aggregate_vicmap_tree_extent.py --workers 2
python greenchanger_script/ingestion.py canopy \
  --canopy-file data/raw/vicmap/tree_extent_analytical/melbourne_tree_extent_20cm.vrt \
  --canopy-aggregate-file data/processed/vicmap/melbourne_tree_extent_500m.jsonl.gz \
  --canopy-analytical \
  --canopy-observed-from 2013-12-07 \
  --canopy-observed-on 2020-11-02 \
  --tree-value 1 --confirm-shared

# 5. Load official Vicmap Tree Urban points through the Feature Service API
python greenchanger_script/ingestion.py trees --confirm-shared

# Load source-labelled named council-tree records. Names are not inferred for
# nearby Vicmap points or for private/backyard trees absent from inventories.
python greenchanger_script/ingestion.py named-trees --confirm-shared

# Load openly licensed research inputs for future species-aware modelling.
# These remain internal evidence and do not publish canopy predictions.
python greenchanger_script/ingestion.py austraits --confirm-shared
python greenchanger_script/ingestion.py urban-growth --confirm-shared

# Add historical modelling covariates. DEA streams the public annual COG;
# ERA5-Land requires accepted CDS terms and a configured ~/.cdsapirc token.
python greenchanger_script/ingestion.py dea-land-cover \
  --dea-year 2025 --dea-grid-size-m 500 --confirm-shared
python greenchanger_script/ingestion.py era5-land \
  --era5-start 2014-01-01 --era5-end 2018-12-31 --confirm-shared
python greenchanger_script/ingestion.py brimbank-trees yarra-trees casey-trees \
  hobsons-bay-trees wyndham-trees port-phillip-trees manningham-trees \
  glen-eira-trees \
  --confirm-shared

# Reuse a completed API extract without redownloading it
python greenchanger_script/ingestion.py trees \
  --urban-tree-file data/raw/vicmap/urban_tree_TIMESTAMP.jsonl.gz \
  --confirm-shared

# 6. Publish Melbourne-only and deduplicated baselines
python greenchanger_script/clip_to_melbourne.py --confirm-shared
python greenchanger_script/build_heat_baseline.py --confirm-shared
python greenchanger_script/build_canopy_baseline.py --confirm-shared
python greenchanger_script/build_environmental_classifications.py \
  --version-label melbourne-fixed-canopy-v1 \
  --require-analytical-canopy --confirm-shared

# Parcel processing is resumable and remains internal until its quality gate passes.
python greenchanger_script/optimise_vicmap_tree_extent_tiles.py
python greenchanger_script/build_property_canopy.py \
  --canopy-file data/interim/vicmap/tree_extent_tiled/melbourne_tree_extent_20cm_tiled.vrt \
  --tree-value 1 --batch-size 1000 --max-parcels 100000 \
  --workers 2 --confirm-shared

# Repeat the command until application_ready is true. Completed batches resume
# without duplication. Extreme non-residential/corridor geometries are marked
# Unavailable rather than allowing a single 0.2 m raster window to exhaust RAM.

# 7. Validate and load reviewed cost references
python greenchanger_script/validate_csv.py cost_estimate \
  data/reference/cost_estimates.csv
python greenchanger_script/ingestion.py costs \
  --cost-file data/reference/cost_estimates.csv --confirm-shared

# 8. Verify code and schema
python greenchanger_script/migrate.py --status
python -m unittest discover -v
```

Query a property result with:

```sql
SELECT * FROM get_property_canopy_by_address(
    '1 COLLINS STREET MELBOURNE', 5
);
```

Query the normalized property/place category with:

```sql
SELECT * FROM get_property_category(
    '1 COLLINS STREET MELBOURNE', 5
);
```

The controlled list includes `house`, `townhouse`, `apartment`, `station`,
`road`, `school`, `hospital`, `commercial`, `industrial`, `park`, `utility`,
`other` and `unclassified`. An assignment must retain its source, method and
optional dataset version. Existing Vicmap `O`/`G` property-type and `S`/`M`
address-class codes are decoded separately; they do not establish that a
property is a house, station, road or another use, so unverified rows remain
explicitly unclassified.

Current air-temperature context for each matched property is available through:

```sql
SELECT * FROM get_property_air_temperature_by_address(
    '1 COLLINS STREET MELBOURNE 3000', 5
);
```

It selects the nearest application-ready BOM station observation no older than
three hours. Results include `degC`, station, timestamp, age, distance, status,
dataset version, source and the database limitation. Temperatures are suppressed
beyond 25 km because this is station context, not a property measurement.

This returns canopy area, parcel canopy percentage, raster coverage, source
resolution and observation date. No approved result returns `Unavailable`,
never an assumed 0% canopy.

The same approved value also fills `property_canopy_percentage` in
`get_property_baseline()`. Its separate `neighbourhood_canopy_percentage` and
neighbourhood-relative classification remain unchanged.

To inspect every **Data Analytics & Insight Development** formula and sample output:

```bash
python greenchanger_script/calculate_measures.py --sample
```

Validate the source-bounded intervention ranges without changing the database:

```bash
python greenchanger_script/validate_intervention_model.py
python greenchanger_script/validate_residential_greening_inputs.py
```

After reviewing a passing report, record the test results and allow the script
to promote only the range model on shared Aurora:

```bash
python greenchanger_script/validate_intervention_model.py \
  --update-status --confirm-shared
```

Print real property-baseline outputs for six representative Melbourne scenarios:

```bash
python greenchanger_script/sanity_check_melbourne.py
```

Run the four greening actions against one real small, medium and large Melbourne
property and print area gain, indicative heat ranges, cost ranges and output
checks:

```bash
python greenchanger_script/run_residential_greening_scenarios.py
python greenchanger_script/run_residential_greening_scenarios.py --json
```

The versioned scenario addresses and expected zones/lot categories are stored in
`config/melbourne_sanity_scenarios.json`. The output prints the parcel area,
official `2GMEL` boundary result, Landsat land-surface temperature and date,
500 m proxy canopy percentage, mapped Tree Urban count and nearest BOM station
distance. It fails missing/ambiguous joins and invalid ranges, while unusual but
possible values—such as 0%/90%+ proxy canopy, zero mapped trees or a distant
weather station—are printed as warnings for imagery or field sanity checking.

The command cannot set `validation_status='validated'` when any evidence case
fails. It never validates the precise arithmetic prototype.

To test the application-facing property lookup:

```sql
SELECT *
FROM get_property_baseline('1 COLLINS STREET', 5);
```

To return only application-ready mapped trees and heat cells within a radius of
a searched Melbourne address, apply migrations 018 and 019 and call:

```sql
SELECT layer, feature_id, distance_m, observed_on, properties, geometry_geojson
FROM get_environment_context_by_address(
    '1 COLLINS STREET MELBOURNE 3000',
    500,
    ARRAY['trees', 'heat'],
    1000
);
```

The wrapper accepts one unique prefix result or one exact full-address match.
Migration 022 normalises case and repeated whitespace and expands supported
street types before lookup; for example, `10 Smith Rd` is searched as
`10 SMITH ROAD`. `ST` is intentionally not expanded because it may mean Saint.
It rejects missing, unmatched and ambiguous searches instead of silently using
the wrong property. Migration 030 groups repeated joins by normalised full
address, so multiple parcels attached to the same official address no longer
become a false “no match”. Consumers can inspect the retained parcel options:

```sql
SELECT full_address, parcel_count, parcel_ids
FROM search_melbourne_addresses('251A BELMORE RD', 10);
```

Genuinely different matching addresses remain ambiguous. After resolving the
address coordinate, the wrapper delegates to the coordinate-based function:

```sql
SELECT layer, feature_id, distance_m, observed_on, properties, geometry_geojson
FROM get_environment_context(
    144.9631,
    -37.8136,
    500,
    ARRAY['trees', 'heat'],
    1000
);
```

The resolved coordinate is EPSG:4326 longitude/latitude and is transformed to
EPSG:7855 for metre-based filtering. The database rejects coordinates outside
the official Melbourne boundary, radii over 2 km, unsupported layers and more
than 2,000 results per layer. `ST_DWithin` uses the existing tree and heat GiST
indexes. Returned heat polygons are clipped to the search circle before GeoJSON
conversion; their 500 m source resolution is unchanged.

## Current shared-database results

| Output | Current result | Quality/status |
| --- | ---: | --- |
| Repository migrations | 001–043 | Migration 043 adds authoritative Victorian LGA lookup and versioned council species guidance |
| Automated tests | Fast unit suite + opt-in PostGIS integration suite | Use the validation commands below and in `PR_DATA_CONTRACT.md` |
| Melbourne Address records | 3,007,474 | 100% boundary membership |
| Melbourne Property records | 3,001,053 | 100% boundary membership |
| Address–Property source-key matches | 3,007,470 of 3,007,474 | 99.999867% |
| Application-ready Landsat baseline | 35,218 unique 500 m cells | All baseline checks passed |
| Application-ready canopy baseline | 37,146 unique 500 m cells | All baseline checks passed |
| BOM weather observations | 1,557 from 10 stations | 100% source quality pass rate; version `greater-melbourne-bom-stations-v1` |
| Vicmap Tree Urban | 10,473,773 Melbourne points | 100% record-quality and boundary-membership pass rates |
| Source-labelled council trees | 629,322 current rows across nine councils | Every latest eligible-record version passes the ≥95% gate; coverage and fields vary by council |
| Property-level analytical canopy | 3,001,053 parcels assessed; 2,984,934 available | 99.46% available; 16,119 safely return `Unavailable` rather than an assumed 0% |
| Cost estimates | 8 in AWS | 100% quality pass; 0 rejected, 0 missing source URLs and 0 expired |
| Representative residential simulations | 3 properties × 4 actions | 12/12 output checks passed; overall WARN from retained baseline caveats |
| Validated scenario measure results | 0 | Prototype model is deliberately blocked from application output |

### Named council-tree inventory results

Migration 037 and `council_tree_inventories.py` support eight additional council inventories without
pretending they describe the same physical objects as Vicmap Tree Urban. Raw
placeholders become null, removed Brimbank records are excluded, coordinates
are transformed to EPSG:7855 and clipped to `2GMEL`, Wyndham Z coordinates are
reduced to the database's 2D point contract, and accepted rows retain their
municipality, source, licence and available dimensions.

| Source | Raw rows | Current rows in AWS | Eligible quality | Usable-name coverage | Height available | Canopy width available |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Brimbank Street Trees | 133,373 | 85,900 | 98.42% | 85.50% of 102,082 active rows | 76,638 | 84,225 |
| City of Yarra | 20,782 | 20,782 | 100% | 100% | 20,782 | Not supplied |
| City of Casey | 205,614 | 151,204 | 100% | 73.54% | 141,640 | 1,952 non-zero values |
| Hobsons Bay | 82,100 | 72,409 | 99.96% | 88.23% | Not supplied | Not supplied |
| Wyndham | 44,859 | 44,841 | 99.99% | 99.97% | 34,257 | 34,260 |
| City of Port Phillip | 46,000 | 45,989 | 100% | 100% | 42,501 | 43,490 |
| Manningham City Council | 66,904 | 66,904 | 100% | 100% | 66,904 ranges | Not supplied |
| Glen Eira Park and Street Trees | 59,259 | 59,229 | 99.99% | 99.96% | 59,071 | 56,365 |

The quality percentage is calculated only over active records with a usable
name; the separate name-coverage percentage prevents that gate from hiding
source incompleteness. Brimbank's 1,378 rejected eligible rows failed only the
identifier-uniqueness rule. Glen Eira's six rejected rows are the members of
three duplicated source identifiers. A missing council record never means that a private
or backyard tree does not exist.

`data/reference/council_tree_inventory_coverage.csv` records the review of all
31 metropolitan councils. Nine councils currently have an integrated source.
The remaining 22 are deliberately not added where no official openly licensed
row-level download was verified, the only source was a partial significant-tree
register, or reuse restrictions were incompatible with the open-data contract.
"Not added" means no suitable source was verified during the recorded review;
it does not claim that the council has no internal inventory.

Application lookup:

```sql
SELECT *
FROM get_metropolitan_named_tree_context(144.998, -37.805, 500, 100);
```

Council-specific planting options are resolved from an address. Only explicit
`approved` or `recommended` guidance appears as `available_now`; conditional,
unlisted and locally observed species appear as `council_approval_required`:

```sql
SELECT *
FROM get_council_species_options_by_address(
    '251A BELMORE ROAD BALWYN NORTH 3104', NULL, 100
);
```

Rank the most commonly recorded public-tree species inside the address council:

```sql
SELECT popularity_rank, display_name, recorded_tree_count,
       recorded_tree_percentage, list_category, guidance_status, limitation
FROM get_council_tree_species_popularity_by_address(
    '251A BELMORE ROAD BALWYN NORTH 3104', 20
);
```

This ranking combines the authoritative LGA lookup with only the latest
application-ready named council inventories and requires the record's source
municipality to match the address LGA. Historical versions are not
double-counted and unnamed Vicmap Tree Urban points are excluded. It may join
loaded council guidance for recommendation status, but frequency is labelled as
an observed public-tree inventory statistic—not resident preference, planting
approval, nursery availability or property suitability. Councils without an
integrated inventory receive a clearly labelled warning plus at most the ten
most frequently recorded species across all integrated Melbourne council
inventories. This fallback is not council-specific evidence, planting approval,
nursery availability or property-suitability advice.

Return the complete Iteration 2 planting catalogue for an address, including
the council guidance status, current supply-only and installed AUD ranges, and
a licensed reference image with attribution:

```sql
SELECT tree_type, scientific_name, list_category, guidance_status,
       supply_min_cost_aud, supply_max_cost_aud,
       installed_min_cost_aud, installed_max_cost_aud,
       image_url, image_alt_text, image_attribution, guidance_limitation
FROM get_tree_planting_catalog_by_address(
    '251A BELMORE ROAD BALWYN NORTH 3104', 20
);
```

The function always includes exact-priced catalogue stock, then adds the most
frequently recorded species for the address council (or the documented
metropolitan fallback). `available_now` means the loaded council source
explicitly uses `approved` or `recommended`; every other row is labelled
`council_approval_required`. Missing species prices use the explicitly labelled
generic catalogue range, and missing verified images remain unavailable.
Images are illustrative reference photographs, not the exact nursery stock;
the returned attribution and limitation must be retained with every image.

The complete named-species catalogue is exposed through
`complete_tree_species_catalog`. Every distinct scientific name is retained.
Species-specific prices use `species_specific_current_source_range`; all other
rows use `generic_current_catalogue_range_not_species_quote`. GBIF enrichment
publishes only exact Plantae matches with confidence at least 95 and individual
media-level CC0 or CC BY 4.0 terms. The licence must be present on the selected media object;
an occurrence-search licence filter is not sufficient. Missing licences, All Rights
Reserved, CC BY-NC, CC BY-ND and custom terms are rejected. For names still
missing images, the optional Wikimedia
Commons fallback is limited to rows with an exact GBIF taxon ID and requires an
exact Wikidata P225 match for that name or its GBIF canonical taxon. This permits
an explicitly labelled base-taxon reference for a cultivar while rejecting fuzzy
or higher-rank substitutions. Only public-domain, GFDL 1.2, CC0, CC BY or CC BY-SA files
with their record-level licence, creator, source page and attribution are accepted.
The separately invoked broader pass can also accept exact Wikidata catalogue-name
or English label/alias matches on taxon items, verified parent species for cultivars,
same-genus GBIF spelling corrections with confidence at least 93 and similarity at
least 0.93, and genus representatives only for names explicitly labelled `sp.`. Each
broader relationship is disclosed in the image alt text or limitation. A final
Wikipedia-title check can correct a uniquely close binomial only when its Wikidata
P225 claim exactly verifies the corrected taxon; user-confirmed corrections take
priority over conflicting GBIF fuzzy suggestions. Ambiguous names remain explicitly
unavailable.

```bash
python greenchanger_script/enrich_tree_catalog.py \
  --workers 12 \
  --confirm-shared

python greenchanger_script/enrich_tree_catalog.py \
  --commons-fallback \
  --workers 4 \
  --confirm-shared

python greenchanger_script/enrich_tree_catalog.py \
  --commons-broader-fallback \
  --workers 4 \
  --confirm-shared

# Replace selected existing images with the exact taxon's Wikipedia lead image
# when its Commons file has an approved licence. Other Commons candidates are
# ranked to prefer mature whole-tree views; the existing image remains fallback.
python greenchanger_script/enrich_tree_catalog.py \
  --prefer-full-tree \
  --species 'Eucalyptus camaldulensis' \
  --species 'Eucalyptus leucoxylon' \
  --workers 1 \
  --confirm-shared

# Revalidate every existing GBIF image against its current media-level licence,
# then load the replaced or quarantined results into the database.
python greenchanger_script/enrich_tree_catalog.py \
  --revalidate-gbif-licences \
  --fetch-only \
  --workers 12
python greenchanger_script/migrate.py --confirm-shared
python greenchanger_script/enrich_tree_catalog.py \
  --load-only \
  --confirm-shared
```

The commands are resumable through
`data/interim/tree_catalog/gbif_species_images.jsonl`. The Commons pass revisits
only rows without a verified image that have an exact GBIF taxon ID. The broader
pass revisits every remaining unavailable row using the disclosed rules above.
Both Commons modes throttle Wikimedia requests; the primary pass skips names
already present unless `--refresh` is supplied.
The `--prefer-full-tree` pass revisits verified exact-taxon rows and prioritises
the exact Wikidata-P225-verified Wikipedia lead file before ranking Commons
metadata for mature whole-tree views. Requests are batched for catalogue-wide
refreshes. Filenames explicitly describing flowers, leaves, fruit, bark, branches,
seedlings, specimens, maps, ranges or close-ups are rejected unless they also
explicitly describe a mature or whole-tree view. The existing approved image is
retained and marked reviewed when no approved representative replacement is
available. Repeat `--species` to limit either fetching or loading to named rows.

The lookup uses the latest application-ready version per source, an indexed
metre-based radius and a bounded result limit. It returns source and licence
metadata plus the public-tree/private-tree limitation with every row.

### Active environmental classifications

Migrations 029 and 032 apply fixed GreenChanger bands to temperature and
canopy values. Temperature bands are product-defined labels, not BOM
heatwave, health-risk or comfort classifications, and every response must retain
whether the source value is Landsat land-surface temperature or BOM air
temperature.

| Metric | Low | Medium | High | Cells assessed |
| --- | --- | --- | --- | ---: |
| Temperature display band | ≤27°C | >27°C and ≤30°C | >30°C | Source-dependent |
| 500 m neighbourhood canopy progress | <15.3% | ≥15.3% and <30% | ≥30% | Source-dependent |

Neither metric is expected to contain equal class counts because both use fixed
boundaries. Exact 15.3% canopy is Medium and exact 30% canopy is High. Exact
27°C temperature is Low and exact 30°C temperature is Medium.
A missing or non-finite value returns `Unavailable`, never `Low`. Inspect the
active metadata:

```bash
python greenchanger_script/build_environmental_classifications.py --status
```

The canopy scheme is tied to the exact baseline dataset version assessed with
the fixed references. A replacement canopy baseline requires a new reviewed version
instead of overwriting history. Temperature uses fixed display bands, but its
source, measurement type, date and limitations remain mandatory. Neither set
of labels means safe/unsafe temperature or statutory canopy adequacy.

### Evidence-backed absolute benchmark helpers

Migration 020 adds two deliberately separate absolute helpers. Their source
URLs, page/section locators, evidence scope, limitations and review date are
stored in `environmental_classification_reference` and mirrored in
`config/environmental_classification_evidence.json`.

For a Melbourne **daily-mean air temperature**, calculate:

```text
(forecast daily maximum + following overnight minimum) / 2
```

The helper compares the calculated daily mean only with the retired 30°C
Victorian Central District threshold and returns structured historical context,
never a current risk class. The 27.2°C value is the published Melbourne summer
95th-percentile daily mean in Table 2 of Tong et al., whose heatwave definition
requires two or more consecutive days. It is therefore retained as evidence
metadata but not used to classify a one-day input. The historical 30°C method
appears on the Victorian Department of Health page under **Weather forecast
districts and corresponding heat health temperature thresholds**,
**Calculating the average temperature**, and Figure 1.

```sql
SELECT jsonb_pretty(classify_melbourne_daily_mean_air_temperature(38, 25));
-- classification: At or above historical 30 C threshold
-- status: historical_context; daily_mean_c: 31.5
```

This function requires a forecast maximum and the following overnight minimum
and returns structured metadata rather than a bare risk label. The historical
30°C method ended in 2021–22 and is not a current BOM warning. The 27.2°C
research percentile requires at least two consecutive days, so it is included
only in `historical_percentile_context` and is never used to categorise this
one-day pair. The helper is not applied to a current instantaneous BOM station
value, apparent temperature or Landsat land-surface temperature.

The canopy helper returns Low below the official 2018 metropolitan baseline of
15.3%, Medium from 15.3% to below 30%, and High from the current Plan for
Victoria urban-area target of 30%. These categories mean below baseline,
between baseline and target, and meeting/exceeding target. They do not prove
property-level planning compliance. The helper must not be used with the
current rendered Vicmap canopy proxy; it is reserved for a validated analytical
canopy percentage at a compatible spatial scope.

```sql
SELECT classify_canopy_benchmark(24.5);
-- Medium
```

References:

- [Victorian Department of Health—Planning for extreme heat and heatwaves](https://www.health.vic.gov.au/environmental-health/planning-for-extreme-heat-and-heatwaves), sections and figure identified above.
- [Tong et al.—The impact of heatwaves on mortality in Australia](https://pmc.ncbi.nlm.nih.gov/articles/PMC3931989/), Table 2.
- [Loughnan et al.—Mapping Heat Health Risks in Urban Areas](https://doi.org/10.1155/2012/518687), Sections 2 and 3.

- [Victorian Government—Melbourne vegetation, heat and land-use data](https://www.planning.vic.gov.au/guides-and-resources/Data-spatial-and-insights/melbournes-vegetation-heat-and-land-use-data), **2018 tree cover**.
- [Plan for Victoria—Action 12: Protect and enhance our canopy trees](https://www.planning.vic.gov.au/planforvictoria/measuring-success/actions-and-outcomes/action-12-protect-and-enhance-our-canopy-trees), **What we'll do**.
- [CDC—Bivariate choropleth map FAQ](https://usdss.cdc.gov/diabetes/data/tutorials/analysis/faq_bvc.html), **What are tertiles?** and **How are the values associated with tertiles found?**

- [Esri—How Calculate Composite Index works](https://pro.arcgis.com/en/pro-app/3.5/tool-reference/spatial-statistics/how-calculate-composite-index-works.htm), **Classify the index** and **Interpret results**.

The complete application-facing function contract, migration order, PostGIS
integration-test command, data-version rules and deployment limitations are in
[`PR_DATA_CONTRACT.md`](PR_DATA_CONTRACT.md).

GitHub Actions also runs the real PostGIS integration suite through
`.github/workflows/greenchanger-postgis.yml` whenever a pull request changes
this data component.

Seven peer-reviewed primary studies are versioned in the intervention evidence
register added by migration 014. This is a completed evidence-selection step,
not a claim that a local intervention coefficient has passed validation.

### Separate predictive-model roadmap

Migration 034 and `config/predictive_model_registry.json` replace the idea of
one general environmental model with four independent contracts:

| Model | Target | Required core sources | Current status |
| --- | --- | --- | --- |
| Tree canopy growth | Future canopy-area range for an individual tree at a stated horizon | City of Melbourne tree inventory and 2021 canopy | Training data not prepared |
| Melbourne canopy change | Historical canopy/change at a consistently aligned spatial grain | City of Melbourne 2008/2015/2016/2021 canopy snapshots, Victorian metropolitan vegetation change, Vicmap Property, DEA Land Cover and ERA5-Land | DEA/ERA5 ingestion implemented; shared versions and aligned labels still need to be built |
| Cooling association | Landsat land-surface-temperature range conditional on vegetation and weather | Landsat surface temperature, vegetation change and ERA5-Land | Training data not prepared |
| Garden cooling | Paired irrigated/unirrigated experimental response | Burnley 2021–2022 irrigation experiment | Blocked pending record-level licence confirmation |

#### Historical canopy and vegetation-change inputs

The longitudinal preparation stage supports City of Melbourne canopy polygons
for 2008, 2015, 2016 and 2021. Migration 039 adds the earlier years without
rewriting migration 038 and creates a separate contract for the statewide
department's 2014–2018 metropolitan percentage-point change layer:

```bash
python greenchanger_script/migrate.py --confirm-shared
python greenchanger_script/ingestion.py sources --confirm-shared
python greenchanger_script/ingestion.py city-canopy \
  --city-canopy-year 2008 --confirm-shared
python greenchanger_script/ingestion.py city-canopy \
  --city-canopy-year 2015 --confirm-shared
python greenchanger_script/ingestion.py city-canopy \
  --city-canopy-year 2016 --confirm-shared
python greenchanger_script/ingestion.py city-canopy \
  --city-canopy-year 2021 --confirm-shared
python greenchanger_script/ingestion.py vegetation-change \
  --vegetation-change-file /path/to/VEGETATION_COVER_2014_18_CHG.shp \
  --confirm-shared
```

The City API extracts are checksummed, geometry-repaired where
possible, normalised to multipolygons in EPSG:7855 and subjected to required,
unique, year and positive-area checks. Passing snapshots remain `internal`.
The metropolitan product must first be ordered/downloaded in SHP or GDB format
from DataShare because its catalogue page is not a direct data API. Its raw
attributes are preserved in JSONB while recognised tree, shrub, grass and total
change fields (`PP_ANYTREE`, `PP_SHRUB`, `PP_GRASS` and `PP_ANYVEG`) are
normalised to percentage points. The large source is read in bounded 5,000-row
batches. Its business key combines `MMB_CODE` and `UNIQUEID`, because one
modified Mesh Block can contain multiple land-type polygons. It remains
separate because its polygons are based on 2016 ABS Mesh Blocks, not canopy
patches.

These inputs do not become ML labels or resident-facing results until all
selected years have been aligned to a common grid and capture/classification
method differences have been assessed. The canopy sources supply year-level rather than exact
acquisition dates, so `observed_on` stores 31 December only as a period-end
convention; modelling must use `observed_year`.

These are model specifications, not trained estimators. All corresponding
`model_version` rows have `output_precision='suppressed'`; therefore no model
may produce a resident-facing prediction yet. Production requires aligned
training data, a confirmed open licence for every required source, spatial and
temporal held-out validation, uncertainty coverage checks and an explicit new
status migration. The existing literature-bounded scenario calculator remains
separate and unchanged.

The historical modelling weather control is ERA5-Land (CC BY 4.0). Migration
041 stores daily summaries of its approximately 9 km reanalysis grid in a
separate table, with temperature (°C), precipitation (mm), layer-1 soil water
(m³/m³), surface solar radiation (MJ/m²) and wind speed (m/s). DEA Land Cover
(CC BY 4.0) is separately stored as annual fractions of its six Level-3 classes
on aligned 500 m Melbourne modelling cells. Neither dataset is published as a
property observation. Current BOM
station observations remain useful application context, but the anonymous
feed is optional for model training because its feed-specific open-reuse terms
have not been confirmed. The Burnley files are also blocked until the Rights
field for that exact Zenodo record states an acceptable reuse licence.

Print the current readiness evidence without fitting or publishing anything:

```bash
python greenchanger_script/assess_predictive_models.py
```

Passing `--available-dataset KEY` means that an aligned training table exists;
it does not bypass licence or validation gates.

### Residential Greening Scenario Simulation input contract

`config/residential_greening_simulation_inputs.json` defines the versioned
`residential-greening-simulation-inputs-v1` contract for trees, potted plants, garden beds and
green walls. Every scenario requires a positive quantity and maturity horizon,
plus explicit survival and site-suitability uncertainty ranges. Action-specific
area and establishment inputs are converted into the existing
`literature-bounded-indicative-v1` model format by
`greenchanger_data/scenario_inputs.py`.

Iteration 1 permits one active simulated tree. Its published 10-year crown-area
preview is 6.6–43.7 m² across 20 common Melbourne street-tree species and
rainfall zones, from [Torquato et al. 2024](https://doi.org/10.1016/j.ufug.2024.128268).
This is a deliberately broad indicative range, not a species selection or
guaranteed mature canopy. The example survival/suitability ranges are transparent
prototype sensitivity assumptions. Examples for pots, beds and walls test the
calculations only and are not application defaults; their dimensions must come
from a user's selection, measurement or supplier specification.

The versioned real-property run uses Richmond (299.96 m², small), Werribee
(600.06 m², medium) and Box Hill (999.34 m², large). Real parcel area scales the
tree and garden-bed land-surface-temperature ranges; it does not change the
green-wall wall-surface metric. All 12 action outputs pass range, unit,
outcome-scope and cost checks. The report remains `WARN` because the proxy
canopy is 0% for Werribee and 93.43% for Box Hill, some mapped-tree results are
zero, and no integrated BOM observation is recent enough. These retained
warnings are not calculation failures.

The Tree Urban raw extract was obtained from the official Vicmap ArcGIS Feature Service, contains 10,580,207 bbox records, is approximately 435 MB compressed, and records a source edit timestamp of 4 June 2025. The application-ready version `558e07b7-f2d3-47b4-ade4-7f9c53ad02a6` contains 10,473,773 points inside the official ABS `2GMEL` boundary; 106,434 outside-boundary points were excluded and no record failed the configured quality gate.

## Main application-ready datasets

| Dataset | Role |
| --- | --- |
| ABS ASGS Edition 4 GCCSA 2026 | Official Melbourne `2GMEL` project boundary |
| Vicmap Address | Address search, coordinates and Property join key |
| Vicmap Property | Property polygons, identifiers and area |
| Vicmap Vegetation – Tree Urban Point | Mapped individual-tree context, radius and height |
| Nine supported source-labelled council tree inventories | Public-tree names and available measured height, crown spread, DBH, maturity, health and planting dates; fields differ by council and each source is loaded separately |
| ERA5-Land daily controls | Historical temperature, rainfall, soil-water, solar-radiation and wind covariates for modelling; approximately 9 km and not property observations |
| DEA Land Cover | Annual 30 m categorical land cover aggregated to aligned 500 m modelling cells; not parcel canopy |
| Vicmap Vegetation – Tree Extent | Melbourne neighbourhood canopy baseline |
| USGS Landsat Collection 2 Surface Temperature | Spatial land-surface-temperature baseline |
| [BOM Melbourne observations](https://www.bom.gov.au/vic/observations/melbourne.shtml) | Recent multi-station air-temperature context; exact official feeds are versioned in `config/bom_stations.json` |
| Reviewed Melbourne-accessible supplier prices | Indicative residential and community greening cost ranges exposed through `application_ready_cost_estimate` |

All source versions retain extraction time, observation period, checksum, source URL, row counts, quality state and publication state.

## Limitations and display rules

### Canopy

- The official analytical source has now been obtained as four DataShare map-sheet packages and prepared as a 57-tile, 0.20 m EPSG:7899 VRT catalogue covering the Melbourne boundary. Its checksummed manifest is stored with the Git-ignored raw data.
- `aggregate_vicmap_tree_extent.py` replaces the failed whole-mosaic approach with atomic tile checkpoints and a compact 500 m valid-area-weighted extract. Rerunning it skips completed tiles.
- Publish `melbourne-fixed-canopy-v1` after migration 032 so the application reports the official 15.3% baseline and 30% urban target instead of retired terciles.
- Property canopy is calculated separately by clipping the unchanged 0.20 m VRT to each parcel. Raster coverage below 95% returns `Unavailable`, never 0%.
- Property batches are resumable and remain internal until all parcels are assessed and the dataset-level 95% quality gate passes.

### Tree Urban points

- Points are machine-derived from aerial imagery and a LiDAR-derived canopy-height model, not a current field inventory.
- The source is described as machine-derived 2019–2020 mapping. Per-feature source metadata in the current extract ranges from 23 October 2019 to 27 January 2021, which may include processing/update timing rather than field observation.
- The dimension audit suppressed 172,179 optional height values outside the conservative 0.5–100 m plausibility range. Tree locations and counts were retained; missing height must not be inferred.
- A point does not prove current tree presence, ownership, health or exact crown extent.
- Results must be labelled “mapped tree points” and should not replace a site inspection.

### Named council trees

- Council inventories describe managed street/park trees, not all vegetation or private/backyard trees.
- They are independent source records and are not assigned to nearby Vicmap Tree Urban points by proximity.
- Brimbank and Hobsons Bay source files date from 2019; they are not current field surveys even where catalogue metadata was refreshed later.
- Wyndham provides common names but not botanical names. Hobsons Bay supplies DBH ranges but no height or crown width; Yarra supplies height but no crown width. Casey crown-width fields are mostly zero and are treated as missing, not measured zero.
- Port Phillip supplies species, planting date, DBH, height and crown-width fields for public street trees. It excludes private trees and source update dates vary by record.
- Manningham supplies street-tree species, height and DBH ranges, address and survey date. The published extract has no crown-width or planting-year field.
- Glen Eira supplies botanical and common names, DBH, height, crown spread and location type. The source has no observation or planting date, so it supports cross-sectional dimension modelling but not age-based growth by itself.
- A missing name or dimension returns `Unavailable`; it is never inferred from another council or from a nearby mapped point.
- “Most common” is calculated only from the latest application-ready public-tree
  inventory records spatially inside the selected LGA. It must not be presented
  as “best to plant”; council guidance and property-specific conditions remain
  separate decisions.

### Heat and weather

- Landsat values are land-surface temperature, not the air temperature experienced by a resident.
- BOM values are observations from the nearest of ten configured official Melbourne stations, not property-level measurements. Scoresby is currently in a BOM-planned outage due to site relocation; its official feed remains configured and failed refreshes are retained as a limitation while other stations continue independently.
- Only observations no older than three hours are eligible. Stations within 10 km are labelled `good_local_context`; 10–25 km is `regional_context_warning`; beyond 25 km the air and apparent temperatures are suppressed; no eligible observation is `unavailable_no_observation_within_3_hours`.
- Station name, observation time and distance remain visible whenever a recent station exists. BOM air temperature is never substituted for Landsat land-surface temperature.
- The heat mosaic uses the newest usable cell and same-day overlap averaging; cells can come from different acquisition dates.
- The original arithmetic model remains suppressed. Migration 015 creates a
  separate `literature-bounded-indicative-v1` model as
  `validation_in_progress` with `indicative_range` precision.
- Validation status and output precision are separate. A future validated model
  can be restricted to `indicative_range`; only a separately approved
  `precise_point_estimate` model may expose an exact after-temperature.
- Literature maxima are never default coefficients. A Melbourne/comparable
  study may constrain a plausible range, but a resident-facing range still
  requires local calibration against the project's aligned Landsat and canopy
  cells plus held-out validation.

### Intervention evidence and output policy

Migration 014 creates `intervention_evidence`, `model_evidence` and the
`selected_intervention_evidence` view. Each record stores the study design,
location, outcome type, spatial scale, reported effects, transferability,
approved use, prohibited use and limitations.

| Action/output | Selected evidence | Permitted model use |
| --- | --- | --- |
| Tree shade and comfort | [Coutts et al. 2016, Melbourne](https://doi.org/10.1007/s00704-015-1409-y) | Validate direction and local shade/comfort benefit; not a Landsat coefficient. |
| Residential vegetation and LST | [Ossola et al. 2021, Adelaide](https://doi.org/10.1016/j.landurbplan.2021.104046) | Constrain daytime surface-cooling plausibility; observational maximum is not causal lift. |
| Tree shade and grass surface cooling | [Armson et al. 2012](https://doi.org/10.1016/j.ufug.2012.05.002) | Mechanism and upper-envelope reasonableness check only. |
| Melbourne future crown area | [Torquato et al. 2025](https://doi.org/10.1016/j.landurbplan.2024.105287) and [Cybula et al. 2026](https://doi.org/10.3390/f17010111) | Species/time-horizon canopy estimates and local growth plausibility. |
| Green-wall surface effect | [Hoelscher et al. 2016](https://doi.org/10.1016/j.enbuild.2015.06.047) | Separately labelled wall-surface benefit only. |
| Melbourne scenario cross-check | [Balany et al. 2022](https://doi.org/10.3390/su14159057) | Contextual ranking and mechanism; not a residential property coefficient. |

The shade output is explicitly named `canopy_area_proxy_for_shade`. It applies
survival, site-suitability and overlap discounts to a supplied future crown
area and always includes a maturity horizon. It is not a sun-angle-specific
shadow measurement. Potted plants receive greenery and directly supported
shade-area outputs only; no temperature coefficient is assigned without
fit-for-purpose outdoor evidence.

#### Action parameters and uncertainty ranges

The complete machine-readable registry is
`config/intervention_model_parameters.json`. Migration 015 mirrors it into
`intervention_model_parameter`, while
`current_intervention_model_parameter` exposes each source and limitation.

| Action | Required scenario parameters | Range output | Evidence boundary |
| --- | --- | --- | --- |
| Trees | Projected crown-area range—or starting crown plus source-supported growth range—survival range, site-suitability range, overlap range, site area and maturity horizon | Canopy-area proxy for shade; indicative daytime land-unit LST range | 0–6°C upper envelope from [Ossola et al.](https://doi.org/10.1016/j.landurbplan.2021.104046); 2.3 m²/year reported young-tree mean is only a plausibility check from [Cybula et al.](https://doi.org/10.3390/f17010111). |
| Potted plants | Quantity and measured/supplier-supported foliage-area range per pot | Projected foliage-area range | No temperature range is emitted because no fit-for-purpose outdoor evidence was selected. |
| Garden beds | Installed-area range, established-cover range and site area | Established vegetation-area range; conservative daytime land-unit LST range | Capped at the 0–6°C combined-vegetation envelope from [Ossola et al.](https://doi.org/10.1016/j.landurbplan.2021.104046). The 24°C direct-plot maximum from [Armson et al.](https://doi.org/10.1016/j.ufug.2012.05.002) is explicitly excluded from parcel output. |
| Green walls | Installed wall-area range, established-cover range and target wall area | Established wall-cover range; exterior wall-surface-temperature range | 0–15.5°C exterior-wall envelope from [Hoelscher et al.](https://doi.org/10.1016/j.enbuild.2015.06.047); never labelled as air temperature or neighbourhood LST. |

The lower cooling bound is zero because a cooling outcome is not guaranteed.
For trees, garden beds and green walls, the evidence upper bound is scaled by
the maximum intervention coverage and capped at the published maximum. Linear
coverage scaling is a transparent project assumption, not a causal research
finding.

#### Published-evidence test cases

`tests/fixtures/intervention_evidence_cases.json` contains four auditable cases:

1. Melbourne young-tree crown growth and the Adelaide land-unit LST bound.
2. Potted plants returning foliage area but no temperature claim.
3. Garden-bed output remaining inside the conservative vegetation bound.
4. Green-wall output retaining the wall-surface metric and 15.5°C ceiling.

`validate_intervention_model.py` records the expected and actual JSON for every
case. Only an all-pass run changes the range model to `validated`; a failed run
keeps it at `validation_in_progress`. Here, “validated” means the calculations
respect their selected literature bounds and output guardrails. It does not
mean local causal validation or permission to display a precise after-temperature.

### Cost

- No suitable government dataset provides current Melbourne residential greening prices.
- The version-controlled file `data/reference/cost_estimates.csv` uses current advertised supplier prices and clearly labelled composite scenarios.
- Exact advertised retail prices are high confidence; transparent multi-source calculations are medium confidence; broad installed-market guidance is low confidence.
- The current coverage includes DIY and installed backyard trees by named type, potted plants, an installed garden bed, DIY and installed green walls, and an installed advanced/community tree context. The earlier container-tree estimate is retained only as expired history.
- Named residential tree costs now match the Iteration 2 planting flow: Water Gum, Lemon-scented Gum and Crepe Myrtle. Earlier Ficus, citrus, elm and pistache estimates remain in the CSV as expired history and are excluded from current application results. `tree_type` and `botanical_name` are retained in the CSV, database and application-ready view.
- Green-roof and unsupported annual-maintenance values remain absent rather than being invented.
- Every record includes its source, assumptions, validity window, verification timestamp, inclusions and confidence level.
- Outputs are indicative estimates, not quotations, and should be rechecked approximately every three months.
- Applications should query `application_ready_cost_estimate` and display its disclaimer.

#### Cost sources and assumptions

The tree prices below were verified on 15 September 2026 and have a review date
of 14 December 2026. Other greening options retain their own row-level validity
windows. Full component fields and source notes are stored in
`data/reference/cost_estimates.csv`.

| Greening option | Indicative range | Source-backed assumption | Confidence |
| --- | ---: | --- | --- |
| Water Gum | $24.95–$99.95 supply only; $108.95–$183.95 with one planting hour | [Diaco's Garden Nursery](https://diacos.com.au/product/water-gum/) lists variant-dependent Water Gum stock; installed cost adds one published $84 Melbourne landscaping hour. | High supply / medium installed |
| Lemon-scented Gum | $15.95–$259.95 supply only; $99.95–$343.95 with one planting hour | [Plant Nest](https://www.plantnest.com.au/products/lemon-scented-gum-corymbia-citriodora-scentuous) lists an exact-species starting price and a 30 cm `Scentuous` cultivar; variants must be confirmed before purchase. | Medium |
| Crepe Myrtle | $35–$179.95 supply only; $119–$263.95 with one planting hour | [Diaco's Garden Nursery](https://diacos.com.au/product/crape-mrytle/) lists colour- and pot-size-dependent Crepe Myrtle stock; installed cost adds one published $84 Melbourne landscaping hour. | High supply / medium installed |
| Potted plants | $49–$175 per pot | Melbourne-accessible plants with decorative pots or multi-planters from [The Indoor Plant Co](https://www.theindoorplantco.com.au/collections/all-plants); delivery and ongoing care are excluded. | High |
| Installed garden bed | $105–$190 per m² | Published Melbourne installed garden-construction range from [Landscaping for Melbourne](https://landscapingformelbourne.com/pricing/); the final price depends on site conditions and inclusions. | Medium |
| DIY living green-wall kit | $94.95 per m² | [Vertical Gardens Direct](https://www.verticalgardensdirect.com.au/products/wallgarden-original-vertical-garden-wall-planter-kit-5-pots-1-square-meter) five-pot kit covering 1 m²; plants, growing media, irrigation, fixings and shipping are excluded. | High |
| Professionally installed green wall | $400–$700 per m² | [Green Wall Australia](https://greenwallaustralia.com.au/) Australian outdoor modular-system guide; this is market guidance rather than a Melbourne supplier quotation. | Low |
| Installed advanced/community tree | $425–$600 per tree | Featured starting prices from [Nursery Direct](https://nurserydirect.com.au/), including tree, delivery and standard installation; Melbourne availability and group pricing require confirmation. | Medium |

Blank GST, delivery, setup or annual-maintenance fields mean that the source did
not publish a reliable value. They must not be interpreted as zero.

The professional planting figures are arithmetic scenarios, not supplier quotes:
one published retail tree price plus one $84 landscaping hour. Actual labour can
require more than one hour, and delivery, access, excavation, soil improvement,
staking, irrigation, permits and aftercare remain excluded unless explicitly stated.

### Property and boundary

- Small/medium/large lot categories are project assumptions, not statutory planning classifications.
- API extraction uses a reproducible bounding box, while application-ready spatial data are filtered to the official ABS 2026 `2GMEL` boundary.
- Address–Property joins use Vicmap Address `property_pfi` to Vicmap Property `prop_pfi`; unmatched records remain documented rather than silently removed.

## Pre-deployment readiness and next data work

The data component can support Local Heat & Greenery Understanding and the baseline parts of
Residential Greening Scenario Simulation: address/parcel context, Melbourne boundary membership, fixed heat and
canopy classifications, mapped-tree context, recent weather when available and
source-backed indicative cost ranges. The environmental and weather values are
application-ready only with the limitations and labels documented above.

The next data-science work, in recommended order, is:

1. Review `residential-greening-simulation-inputs-v1` with the team/mentor, then connect the
   approved contract to scenario persistence and the application data handoff.
2. Review the 16,119 parcel-canopy records that safely return `Unavailable` due
   to insufficient raster coverage or processing eligibility; do not convert
   them to zero canopy.
3. Reconcile historical canopy, vegetation-change, DEA and ERA5-Land data onto
   explicit training grains before fitting any predictive model. Keep every
   model output suppressed until spatial/temporal held-out validation passes.
4. Request full inventories and compatible reuse permission from additional
   councils. The 31-council audit currently has nine integrated sources; a
   partial register or unlicensed download must not be treated as complete.
5. Add 10 m and 25 m buffered mapped-tree counts so property context does not
   rely only on parcel intersection.
6. Refresh BOM observations before demonstrations, rerun the six Melbourne
   sanity scenarios, investigate every warning, and retain the generated
   quality/validation evidence.

An exact resident-facing “after temperature” remains out of scope until a
locally calibrated intervention model passes held-out validation and receives
separate `precise_point_estimate` approval. Until then, expose only clearly
labelled indicative ranges where the selected evidence supports them.

## Safety and reproducibility

- Never edit migrations already applied to the shared database; add the next numbered migration.
- `migrate.py --reset` is restricted to a local database.
- Large raw files and credentials are ignored by Git.
- Raw API extracts can be reused after a failed database transaction.
- Only `application_ready` dataset versions and validated analytical models should feed the application.
