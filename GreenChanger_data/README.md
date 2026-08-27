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
Official ABS 2026 Greater Melbourne (2GMEL) boundary filter
        ↓
PostgreSQL 17 + PostGIS integration
        ↓
Versioned application-ready views and property lookup
```

**Data Quality & Preparation** requires at least 95% of assessed records to pass the configured completeness, validity and consistency checks. Failed records are rejected or quarantined, and limitations are retained in the database. **Data Analytics & Insight Development** covers the analytical measures presented to users. Its calculations separate observed values from modelled scenarios and expose precise projected heat results only from validated model versions.

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

# 2. Register sources and load the official Greater Melbourne boundary
python greenchanger_script/ingestion.py sources --confirm-shared
python greenchanger_script/ingestion.py boundary --confirm-shared

# 3. Load current Vicmap Address and Property data
python greenchanger_script/ingestion.py address --confirm-shared
python greenchanger_script/ingestion.py property --confirm-shared

# 4. Load weather, Landsat surface heat and Vicmap canopy
python greenchanger_script/ingestion.py bom --confirm-shared
python greenchanger_script/ingestion.py heat --confirm-shared
python greenchanger_script/ingestion.py canopy \
  --canopy-file data/raw/vicmap/tree_extent_api_z13.tif \
  --canopy-observed-from 2013-12-07 \
  --canopy-observed-on 2020-11-02 \
  --tree-value 255 --confirm-shared

# 5. Load official Vicmap Tree Urban points through the Feature Service API
python greenchanger_script/ingestion.py trees --confirm-shared

# Reuse a completed API extract without redownloading it
python greenchanger_script/ingestion.py trees \
  --urban-tree-file data/raw/vicmap/urban_tree_TIMESTAMP.jsonl.gz \
  --confirm-shared

# 6. Publish Melbourne-only and deduplicated baselines
python greenchanger_script/clip_to_melbourne.py --confirm-shared
python greenchanger_script/build_heat_baseline.py --confirm-shared
python greenchanger_script/build_canopy_baseline.py --confirm-shared
python greenchanger_script/build_environmental_classifications.py \
  --version-label melbourne-terciles-v1 --confirm-shared

# 7. Validate and load reviewed cost references
python greenchanger_script/validate_csv.py cost_estimate \
  data/reference/cost_estimates.csv
python greenchanger_script/ingestion.py costs \
  --cost-file data/reference/cost_estimates.csv --confirm-shared

# 8. Verify code and schema
python greenchanger_script/migrate.py --status
python -m unittest discover -v
```

To inspect every **Data Analytics & Insight Development** formula and sample output:

```bash
python greenchanger_script/calculate_measures.py --sample
```

Validate the source-bounded intervention ranges without changing the database:

```bash
python greenchanger_script/validate_intervention_model.py
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

## Current shared-database results

| Output | Current result | Quality/status |
| --- | ---: | --- |
| Applied migrations | 001–017 | Applied to shared Aurora |
| Automated tests | 86/86 | Passed locally after classification implementation |
| Greater Melbourne Address records | 3,007,474 | 100% boundary membership |
| Greater Melbourne Property records | 3,001,053 | 100% boundary membership |
| Address–Property source-key matches | 3,007,470 of 3,007,474 | 99.999867% |
| Application-ready Landsat baseline | 35,218 unique 500 m cells | All baseline checks passed |
| Application-ready canopy baseline | 37,146 unique 500 m cells | All baseline checks passed |
| BOM weather observations | 1,557 from 10 stations | 100% source quality pass rate; version `greater-melbourne-bom-stations-v1` |
| Vicmap Tree Urban | 10,473,773 Greater Melbourne points | 100% record-quality and boundary-membership pass rates |
| Cost estimates | 8 in AWS | 100% quality pass; 0 rejected, 0 missing source URLs and 0 expired |
| Validated scenario measure results | 0 | Prototype model is deliberately blocked from application output |

### Active environmental classifications

Migration 017 and `build_environmental_classifications.py` created the active
`melbourne-terciles-v1` scheme from the current application-ready cells. These
are relative Melbourne indicators, not health, planning or comfort standards.

| Metric | Low | Medium | High | Cells assessed |
| --- | --- | --- | --- | ---: |
| Landsat land-surface temperature | ≤9.508°C | >9.508°C and ≤13.147°C | >13.147°C | 35,218 |
| 500 m neighbourhood canopy proxy | ≤28.8% | >28.8% and ≤73.533333% | >73.533333% | 37,146 |

The distributions are 11,741/11,742/11,735 heat cells and
12,384/12,380/12,382 canopy cells for Low/Medium/High respectively. Exact
boundary values remain in the lower class. A missing source value or missing
active threshold returns `Unavailable`, never `Low`. Inspect the active scheme:

```bash
python greenchanger_script/build_environmental_classifications.py --status
```

Seven peer-reviewed primary studies are versioned in the intervention evidence
register added by migration 014. This is a completed evidence-selection step,
not a claim that a local intervention coefficient has passed validation.

The Tree Urban raw extract was obtained from the official Vicmap ArcGIS Feature Service, contains 10,580,207 bbox records, is approximately 435 MB compressed, and records a source edit timestamp of 4 June 2025. The application-ready version `558e07b7-f2d3-47b4-ade4-7f9c53ad02a6` contains 10,473,773 points inside the official ABS `2GMEL` boundary; 106,434 outside-boundary points were excluded and no record failed the configured quality gate.

## Main application-ready datasets

| Dataset | Role |
| --- | --- |
| ABS ASGS Edition 4 GCCSA 2026 | Official Greater Melbourne `2GMEL` project boundary |
| Vicmap Address | Address search, coordinates and Property join key |
| Vicmap Property | Property polygons, identifiers and area |
| Vicmap Vegetation – Tree Urban Point | Mapped individual-tree context, radius and height |
| Vicmap Vegetation – Tree Extent | Melbourne neighbourhood canopy baseline |
| USGS Landsat Collection 2 Surface Temperature | Spatial land-surface-temperature baseline |
| [BOM Melbourne observations](https://www.bom.gov.au/vic/observations/melbourne.shtml) | Recent multi-station air-temperature context; exact official feeds are versioned in `config/bom_stations.json` |
| Reviewed Melbourne-accessible supplier prices | Indicative residential and community greening cost ranges exposed through `application_ready_cost_estimate` |

All source versions retain extraction time, observation period, checksum, source URL, row counts, quality state and publication state.

## Limitations and display rules

### Canopy

- The current Tree Extent baseline is an official rendered API proxy with approximately 19.1 m source pixels, aggregated into 500 m cells.
- It is suitable for neighbourhood comparison, not property-level canopy area or individual crown measurement.
- `property_canopy_percentage` remains null; the application must display `neighbourhood_canopy_percentage` with scope `neighbourhood_500m`.
- The original analytical Vicmap Tree Extent GeoTIFF remains the preferred future replacement.

### Tree Urban points

- Points are machine-derived from aerial imagery and a LiDAR-derived canopy-height model, not a current field inventory.
- The source is described as machine-derived 2019–2020 mapping. Per-feature source metadata in the current extract ranges from 23 October 2019 to 27 January 2021, which may include processing/update timing rather than field observation.
- The dimension audit suppressed 172,179 optional height values outside the conservative 0.5–100 m plausibility range. Tree locations and counts were retained; missing height must not be inferred.
- A point does not prove current tree presence, ownership, health or exact crown extent.
- Results must be labelled “mapped tree points” and should not replace a site inspection.

### Heat and weather

- Landsat values are land-surface temperature, not the air temperature experienced by a resident.
- BOM values are observations from the nearest of ten configured official Greater Melbourne stations, not property-level measurements.
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
- The current coverage includes DIY and installed backyard trees, a container tree, potted plants, an installed garden bed, DIY and installed green walls, and an installed advanced/community tree context.
- Green-roof and unsupported annual-maintenance values remain absent rather than being invented.
- Every record includes its source, assumptions, validity window, verification timestamp, inclusions and confidence level.
- Outputs are indicative estimates, not quotations, and should be rechecked approximately every three months.
- Applications should query `application_ready_cost_estimate` and display its disclaimer.

#### Cost sources and assumptions

The prices below were verified on 26 August 2026 and have a review date of
26 November 2026. Full component fields and source notes are stored in
`data/reference/cost_estimates.csv`.

| Greening option | Indicative range | Source-backed assumption | Confidence |
| --- | ---: | --- | --- |
| DIY small backyard tree | $25–$85 per tree | [Plants Melbourne Nursery](https://plantsmelb.com/store/page/2/) advertised 200–300 mm Ficus stock; delivery, soil, stakes and labour are excluded. | High |
| Professionally planted small tree | $109–$169 per tree | $25–$85 plant plus one $84 advertised landscaping hour from [Landscaping for Melbourne](https://landscapingformelbourne.com/pricing/); assumes a prepared and accessible site. | Medium |
| Container tree | $67.99–$185.68 per tree | [Diaco's Lemon Eureka](https://diacos.com.au/product/lemon-eureka/) at $49–$139 plus a 400 mm pot from [Ladybird Nursery](https://ladybirdnursery.com.au/products/plastic-pot-400mm-pick-up-only) or [Bunnings](https://www.bunnings.com.au/elho-40cm-terracotta-vibia-outdoor-plant-pot_p0366936) at $18.99–$46.68; potting mix, delivery and labour are excluded. | Medium |
| Potted plants | $49–$175 per pot | Melbourne-accessible plants with decorative pots or multi-planters from [The Indoor Plant Co](https://www.theindoorplantco.com.au/collections/all-plants); delivery and ongoing care are excluded. | High |
| Installed garden bed | $105–$190 per m² | Published Melbourne installed garden-construction range from [Landscaping for Melbourne](https://landscapingformelbourne.com/pricing/); the final price depends on site conditions and inclusions. | Medium |
| DIY living green-wall kit | $94.95 per m² | [Vertical Gardens Direct](https://www.verticalgardensdirect.com.au/products/wallgarden-original-vertical-garden-wall-planter-kit-5-pots-1-square-meter) five-pot kit covering 1 m²; plants, growing media, irrigation, fixings and shipping are excluded. | High |
| Professionally installed green wall | $400–$700 per m² | [Green Wall Australia](https://greenwallaustralia.com.au/) Australian outdoor modular-system guide; this is market guidance rather than a Melbourne supplier quotation. | Low |
| Installed advanced/community tree | $425–$600 per tree | Featured starting prices from [Nursery Direct](https://nurserydirect.com.au/), including tree, delivery and standard installation; Melbourne availability and group pricing require confirmation. | Medium |

Blank GST, delivery, setup or annual-maintenance fields mean that the source did
not publish a reliable value. They must not be interpreted as zero.

### Property and boundary

- Small/medium/large lot categories are project assumptions, not statutory planning classifications.
- API extraction uses a reproducible bounding box, while application-ready spatial data are filtered to the official ABS 2026 `2GMEL` boundary.
- Address–Property joins use Vicmap Address `property_pfi` to Vicmap Property `prop_pfi`; unmatched records remain documented rather than silently removed.

## Safety and reproducibility

- Never edit migrations already applied to the shared database; add the next numbered migration.
- `migrate.py --reset` is restricted to a local database.
- Large raw files and credentials are ignored by Git.
- Raw API extracts can be reused after a failed database transaction.
- Only `application_ready` dataset versions and validated analytical models should feed the application.
