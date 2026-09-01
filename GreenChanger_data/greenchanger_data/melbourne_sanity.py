"""Pure validation rules for real Melbourne property spot checks."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any


REQUIRED_ZONES = {
    "Melbourne CBD",
    "Inner suburbs",
    "Western growth area",
    "Northern growth area",
    "Eastern suburbs",
    "Southeastern suburbs",
}
REQUIRED_LOT_SIZES = {"small", "medium", "large"}


def _float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _serialise(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _serialise(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialise(item) for item in value]
    return value


def validate_scenario_set(scenarios: list[dict[str, Any]]) -> list[str]:
    """Return missing coverage requirements for the configured scenario set."""

    zones = {scenario.get("zone") for scenario in scenarios}
    lot_sizes = {scenario.get("expected_lot_size") for scenario in scenarios}
    failures = []
    missing_zones = sorted(REQUIRED_ZONES - zones)
    missing_lots = sorted(REQUIRED_LOT_SIZES - lot_sizes)
    if missing_zones:
        failures.append("missing zones: " + ", ".join(missing_zones))
    if missing_lots:
        failures.append("missing lot sizes: " + ", ".join(missing_lots))
    return failures


def evaluate_property_scenario(
    scenario: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    inside_greater_melbourne: bool | None,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Evaluate one exact-address lookup without inventing missing evidence."""

    as_of = as_of or datetime.now(timezone.utc).date()
    failures: list[str] = []
    warnings: list[str] = []
    checks: list[str] = []

    if len(rows) != 1:
        failures.append(
            f"expected one exact address match but received {len(rows)}; "
            "inspect address/property join uniqueness"
        )
    if not rows:
        return {
            "scenario_code": scenario["scenario_code"],
            "zone": scenario["zone"],
            "requested_address": scenario["address"],
            "context": scenario.get("context"),
            "status": "FAIL",
            "checks": checks,
            "warnings": warnings,
            "failures": failures,
            "actual": None,
        }

    row = rows[0]
    locality = row.get("locality_name")
    if locality not in scenario["expected_localities"]:
        failures.append(
            f"locality {locality!r} is outside expected values "
            f"{scenario['expected_localities']}"
        )
    else:
        checks.append("locality matches the configured Melbourne zone")

    if inside_greater_melbourne is not True:
        failures.append("address point is not covered by the official 2GMEL boundary")
    else:
        checks.append("address point is inside the official 2GMEL boundary")

    parcel_area = _float(row.get("parcel_area_m2"))
    if row.get("parcel_id") is None or parcel_area is None or parcel_area <= 0:
        failures.append("parcel geometry/area is missing or invalid")
    else:
        checks.append("parcel join produced a positive area")
    if row.get("lot_size_category") != scenario["expected_lot_size"]:
        failures.append(
            f"lot category {row.get('lot_size_category')!r} does not match "
            f"expected {scenario['expected_lot_size']!r}"
        )
    else:
        checks.append("lot-size category matches the scenario")

    longitude = _float(row.get("longitude"))
    latitude = _float(row.get("latitude"))
    if longitude is None or latitude is None:
        failures.append("WGS84 property coordinates are missing")
    elif not (144.0 <= longitude <= 146.0 and -39.5 <= latitude <= -37.0):
        failures.append("coordinates fall outside the broad Melbourne reasonableness box")
    else:
        checks.append("coordinates are numerically plausible for Melbourne")

    heat = _float(row.get("land_surface_temperature_c"))
    heat_date = _date(row.get("surface_temperature_observed_on"))
    if heat is None:
        failures.append("Landsat heat baseline is missing")
    elif not (-20.0 <= heat <= 80.0):
        failures.append(f"land-surface temperature {heat:.2f} C is implausible")
    else:
        checks.append("Landsat land-surface temperature is in the validity range")
    if row.get("temperature_measurement_type") != "land_surface_temperature":
        failures.append("heat value is not labelled land_surface_temperature")
    heat_classification = row.get("heat_classification")
    if heat is None:
        if heat_classification != "Unavailable":
            failures.append("missing heat is not classified as Unavailable")
    elif heat_classification not in {"Low", "Medium", "High"}:
        failures.append(f"invalid heat classification {heat_classification!r}")
    else:
        checks.append("heat has a supported Melbourne-relative classification")
    if heat_date is None:
        failures.append("Landsat observation date is missing")
    elif heat_date > as_of:
        failures.append("Landsat observation date is in the future")
    elif (as_of - heat_date).days > 365:
        warnings.append(f"Landsat heat observation is {(as_of - heat_date).days} days old")

    canopy = _float(row.get("neighbourhood_canopy_percentage"))
    if canopy is None:
        failures.append("500 m neighbourhood canopy baseline is missing")
    elif not (0.0 <= canopy <= 100.0):
        failures.append(f"canopy percentage {canopy:.2f}% is outside 0-100")
    else:
        checks.append("neighbourhood canopy percentage is valid")
        if canopy <= 1.0 or canopy >= 90.0:
            warnings.append(
                f"extreme proxy canopy value ({canopy:.2f}%); compare with imagery "
                "before using it for a property decision"
            )
    if row.get("canopy_analysis_scope") != "neighbourhood_500m":
        failures.append("canopy output is not labelled neighbourhood_500m")
    if row.get("canopy_source_is_proxy") is not True:
        failures.append("current canopy baseline is not explicitly marked as a proxy")
    if row.get("property_canopy_percentage") is not None:
        failures.append("property canopy must remain suppressed for the proxy source")
    canopy_classification = row.get("canopy_classification")
    if canopy is None:
        if canopy_classification != "Unavailable":
            failures.append("missing canopy is not classified as Unavailable")
    elif canopy_classification not in {"Low", "Medium", "High"}:
        failures.append(f"invalid canopy classification {canopy_classification!r}")
    else:
        checks.append("canopy has a supported Melbourne-relative classification")

    classification_version = row.get("classification_scheme_version")
    classification_scope = row.get("classification_scope")
    if not classification_version:
        failures.append("environmental classification scheme version is missing")
    if classification_scope != "relative_to_greater_melbourne_application_ready_baseline":
        failures.append(f"invalid environmental classification scope {classification_scope!r}")

    tree_count = row.get("mapped_property_tree_count")
    if row.get("property_tree_data_status") != "mapped_tree_points_available":
        failures.append("Vicmap mapped-tree dataset is not available for the parcel")
    elif tree_count is None or int(tree_count) < 0:
        failures.append("mapped property-tree count is missing or negative")
    else:
        checks.append("mapped-tree join returned a non-negative count")
        if int(tree_count) == 0:
            warnings.append(
                "zero mapped tree points; this may be real or a limitation of the "
                "machine-derived 2019-2020 source"
            )

    weather_distance = _float(row.get("weather_station_distance_km"))
    weather_status = row.get("air_temperature_context_status")
    air_temperature = _float(row.get("current_air_temperature_c"))
    if weather_status == "good_local_context":
        if weather_distance is None or weather_distance > 10.0 or air_temperature is None:
            failures.append("good local weather status contradicts distance or temperature")
        else:
            checks.append("BOM station is within 10 km and no older than three hours")
    elif weather_status == "regional_context_warning":
        if weather_distance is None or not (10.0 < weather_distance <= 25.0):
            failures.append("regional weather status contradicts station distance")
        else:
            warnings.append(
                f"nearest current BOM station is {weather_distance:.1f} km away; "
                "regional context only"
            )
    elif weather_status == "too_distant_temperature_suppressed":
        if air_temperature is not None:
            failures.append("air temperature was not suppressed beyond 25 km")
        if weather_distance is None or weather_distance <= 25.0:
            failures.append("too-distant weather status contradicts station distance")
        else:
            warnings.append(
                f"nearest current BOM station is {weather_distance:.1f} km away; "
                "temperature correctly suppressed"
            )
    elif weather_status == "unavailable_no_observation_within_3_hours":
        if air_temperature is not None:
            failures.append("stale/unavailable weather context exposes a temperature")
        warnings.append("no integrated BOM observation is available within three hours")
    else:
        failures.append(f"unknown weather context status {weather_status!r}")

    if row.get("data_quality_status") != "passed":
        failures.append(
            f"database property lookup quality status is {row.get('data_quality_status')!r}"
        )
    else:
        checks.append("database property lookup quality status passed")

    actual = {
        "address": row.get("full_address"),
        "locality": locality,
        "postcode": row.get("postcode"),
        "longitude": longitude,
        "latitude": latitude,
        "inside_greater_melbourne": inside_greater_melbourne,
        "parcel_area_m2": parcel_area,
        "lot_size_category": row.get("lot_size_category"),
        "land_surface_temperature_c": heat,
        "heat_observed_on": _serialise(heat_date),
        "temperature_measurement_type": row.get("temperature_measurement_type"),
        "heat_classification": heat_classification,
        "neighbourhood_canopy_percentage": canopy,
        "canopy_classification": canopy_classification,
        "classification_scheme_version": classification_version,
        "classification_scope": classification_scope,
        "canopy_scope": row.get("canopy_analysis_scope"),
        "canopy_observed_on": _serialise(row.get("canopy_observed_on")),
        "canopy_source_type": row.get("canopy_source_type"),
        "mapped_property_tree_count": int(tree_count) if tree_count is not None else None,
        "tree_data_status": row.get("property_tree_data_status"),
        "weather_station": row.get("weather_station_name"),
        "weather_observed_at": _serialise(row.get("weather_observed_at")),
        "weather_station_distance_km": weather_distance,
        "air_temperature_c": air_temperature,
        "air_temperature_context_status": weather_status,
        "database_quality_status": row.get("data_quality_status"),
        "limitations": _serialise(row.get("limitations") or {}),
    }
    return {
        "scenario_code": scenario["scenario_code"],
        "zone": scenario["zone"],
        "requested_address": scenario["address"],
        "context": scenario.get("context"),
        "status": "FAIL" if failures else ("WARN" if warnings else "PASS"),
        "checks": checks,
        "warnings": warnings,
        "failures": failures,
        "actual": actual,
    }


def build_report(
    scenarios: list[dict[str, Any]], results: list[dict[str, Any]], *, as_of: Any
) -> dict[str, Any]:
    """Build a serialisable scenario report with coverage and status counts."""

    coverage_failures = validate_scenario_set(scenarios)
    counts = {
        status: sum(result["status"] == status for result in results)
        for status in ("PASS", "WARN", "FAIL")
    }
    return {
        "scenario_set": "greater-melbourne-property-baseline-v1",
        "as_of": _serialise(as_of),
        "validation_scope": (
            "Real-address geographic and join sanity checks; not ground-truth field validation"
        ),
        "scenario_coverage_failures": coverage_failures,
        "summary": {"scenario_count": len(results), **counts},
        "results": results,
        "overall_status": "FAIL"
        if coverage_failures or counts["FAIL"]
        else ("WARN" if counts["WARN"] else "PASS"),
    }
