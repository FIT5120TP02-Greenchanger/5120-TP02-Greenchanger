"""Literature-bounded intervention ranges with explicit outcome scopes."""

from __future__ import annotations

import json
from math import isfinite
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PARAMETERS = ROOT / "config" / "intervention_model_parameters.json"


def _number(name: str, value: object) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be numeric") from error
    if not isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _range(name: str, value: object, *, fraction: bool = False) -> tuple[float, float]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must contain minimum and maximum")
    minimum = _number(f"{name}.minimum", value.get("minimum"))
    maximum = _number(f"{name}.maximum", value.get("maximum"))
    if minimum < 0 or maximum < minimum:
        raise ValueError(f"{name} must be a non-negative ordered range")
    if fraction and maximum > 1:
        raise ValueError(f"{name} must be between 0 and 1")
    return minimum, maximum


def load_parameter_registry(path: Path | None = None) -> dict[str, Any]:
    """Load and minimally validate the versioned parameter registry."""

    source = path or DEFAULT_PARAMETERS
    registry = json.loads(source.read_text(encoding="utf-8"))
    required_actions = {"tree", "potted_plants", "garden_bed", "green_wall"}
    if set(registry.get("actions", {})) != required_actions:
        raise ValueError("parameter registry must define exactly the four supported actions")
    if registry.get("output_precision") != "indicative_range":
        raise ValueError("intervention model must use indicative_range output precision")
    return registry


def _temperature_range(
    action: Mapping[str, Any], maximum_coverage_fraction: float
) -> dict[str, float | str] | None:
    evidence = action.get("temperature_evidence_bound")
    if evidence is None:
        return None
    maximum_coverage = min(max(maximum_coverage_fraction, 0.0), 1.0)
    minimum = _number("temperature_evidence_bound.minimum_c", evidence["minimum_c"])
    maximum = _number("temperature_evidence_bound.maximum_c", evidence["maximum_c"])
    if minimum < 0 or maximum < minimum:
        raise ValueError("temperature evidence bound must be non-negative and ordered")
    return {
        "minimum": round(minimum * maximum_coverage, 3),
        "maximum": round(maximum * maximum_coverage, 3),
        "metric": evidence["metric"],
        "scope": evidence["scope"],
        "source_key": evidence["source_key"],
        "source_url": evidence["source_url"],
    }


def calculate_intervention_impact(
    action_type: str,
    inputs: Mapping[str, Any],
    *,
    registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate an uncertainty range without presenting a guaranteed effect."""

    parameters = dict(registry or load_parameter_registry())
    actions = parameters["actions"]
    if action_type not in actions:
        raise ValueError(f"unsupported action_type: {action_type}")
    action = actions[action_type]

    if action_type == "tree":
        horizon = _number(
            "maturity_horizon_years", inputs.get("maturity_horizon_years")
        )
        if horizon <= 0 or not horizon.is_integer():
            raise ValueError("maturity_horizon_years must be a positive whole number")
        if "projected_canopy_m2" in inputs:
            canopy_min, canopy_max = _range(
                "projected_canopy_m2", inputs.get("projected_canopy_m2")
            )
        else:
            initial_min, initial_max = _range(
                "initial_canopy_m2", inputs.get("initial_canopy_m2")
            )
            growth_min, growth_max = _range(
                "annual_crown_growth_m2_per_year",
                inputs.get("annual_crown_growth_m2_per_year"),
            )
            canopy_min = initial_min + growth_min * horizon
            canopy_max = initial_max + growth_max * horizon
        survival_min, survival_max = _range(
            "survival_probability", inputs.get("survival_probability"), fraction=True
        )
        suitability_min, suitability_max = _range(
            "site_suitability_factor",
            inputs.get("site_suitability_factor"),
            fraction=True,
        )
        overlap_min, overlap_max = _range(
            "overlap_factor", inputs.get("overlap_factor"), fraction=True
        )
        site_area = _number("site_area_m2", inputs.get("site_area_m2"))
        if site_area <= 0:
            raise ValueError("site_area_m2 must be positive")
        area_min = canopy_min * survival_min * suitability_min * overlap_min
        area_max = canopy_max * survival_max * suitability_max * overlap_max
        extra = {
            "maturity_horizon_years": int(horizon),
            "projected_canopy_range_m2": {
                "minimum": round(canopy_min, 3),
                "maximum": round(canopy_max, 3),
            },
        }
        denominator = site_area
    elif action_type == "potted_plants":
        quantity = _number("quantity", inputs.get("quantity"))
        if quantity < 0 or not quantity.is_integer():
            raise ValueError("quantity must be a non-negative whole number")
        foliage_min, foliage_max = _range(
            "foliage_area_per_pot_m2", inputs.get("foliage_area_per_pot_m2")
        )
        area_min = quantity * foliage_min
        area_max = quantity * foliage_max
        denominator = 1.0
        extra = {"quantity": int(quantity)}
    elif action_type == "garden_bed":
        planted_min, planted_max = _range(
            "planted_area_m2", inputs.get("planted_area_m2")
        )
        cover_min, cover_max = _range(
            "established_cover_fraction",
            inputs.get("established_cover_fraction"),
            fraction=True,
        )
        area_min = planted_min * cover_min
        area_max = planted_max * cover_max
        denominator = _number("site_area_m2", inputs.get("site_area_m2"))
        if denominator <= 0:
            raise ValueError("site_area_m2 must be positive")
        extra = {}
    else:
        wall_min, wall_max = _range(
            "installed_wall_area_m2", inputs.get("installed_wall_area_m2")
        )
        cover_min, cover_max = _range(
            "established_cover_fraction",
            inputs.get("established_cover_fraction"),
            fraction=True,
        )
        area_min = wall_min * cover_min
        area_max = wall_max * cover_max
        denominator = _number(
            "target_wall_area_m2", inputs.get("target_wall_area_m2")
        )
        if denominator <= 0:
            raise ValueError("target_wall_area_m2 must be positive")
        extra = {}

    temperature = _temperature_range(action, area_max / denominator)
    status = "indicative_range" if temperature is not None else "evidence_insufficient_for_temperature"
    return {
        "model_version": parameters["version_label"],
        "action_type": action_type,
        "status": status,
        "impact_area_type": action["area_output"],
        "impact_area_range_m2": {
            "minimum": round(area_min, 3),
            "maximum": round(area_max, 3),
        },
        "temperature_change_range_c": temperature,
        **extra,
        "guaranteed_outcome": False,
        "calculation_assumption": action["calculation_assumption"],
    }


def _compare_subset(
    actual: object,
    expected: object,
    *,
    tolerance: float,
    path: str = "result",
) -> list[str]:
    failures: list[str] = []
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping):
            return [f"{path}: expected an object"]
        for key, expected_value in expected.items():
            if key not in actual:
                failures.append(f"{path}.{key}: missing")
                continue
            failures.extend(
                _compare_subset(
                    actual[key],
                    expected_value,
                    tolerance=tolerance,
                    path=f"{path}.{key}",
                )
            )
        return failures
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        try:
            actual_number = float(actual)
        except (TypeError, ValueError):
            return [f"{path}: expected numeric {expected}, got {actual!r}"]
        if abs(actual_number - float(expected)) > tolerance:
            failures.append(f"{path}: expected {expected}, got {actual_number}")
    elif actual != expected:
        failures.append(f"{path}: expected {expected!r}, got {actual!r}")
    return failures


def evaluate_validation_cases(
    cases: Mapping[str, Any],
    *,
    registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run published-evidence cases and return an auditable validation report."""

    parameters = dict(registry or load_parameter_registry())
    if cases.get("model_version") != parameters["version_label"]:
        raise ValueError("validation cases target a different model version")
    tolerance = _number("tolerance", cases.get("tolerance", 0))
    results = []
    for case in cases.get("cases", []):
        actual = calculate_intervention_impact(
            case["action_type"], case["inputs"], registry=parameters
        )
        failures = _compare_subset(
            actual, case["expected"], tolerance=tolerance
        )
        results.append(
            {
                "case_code": case["case_code"],
                "description": case["description"],
                "source_keys": case.get("source_keys", []),
                "passed": not failures,
                "failures": failures,
                "expected": case["expected"],
                "actual": actual,
            }
        )
    passed_count = sum(result["passed"] for result in results)
    return {
        "model_name": parameters["model_name"],
        "model_version": parameters["version_label"],
        "validation_scope": "literature-bounded indicative ranges; not local causal validation",
        "case_count": len(results),
        "passed_count": passed_count,
        "failed_count": len(results) - passed_count,
        "all_passed": bool(results) and passed_count == len(results),
        "results": results,
    }
