"""Evaluate greening actions against real property baselines and cost evidence."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterable, Mapping

from .scenario_inputs import calculate_simulated_action, load_input_contract


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COSTS = ROOT / "data" / "reference" / "cost_estimates.csv"
COST_OPTIONS = {
    "tree": ("backyard_tree_diy", "backyard_tree_installed"),
    "potted_plants": ("potted_plants",),
    "garden_bed": ("garden_bed",),
    "green_wall": ("green_wall",),
}


def load_cost_rows(path: Path = DEFAULT_COSTS) -> list[dict[str, str]]:
    """Load the reviewed, version-controlled cost evidence."""

    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def _cost_units(action_type: str, inputs: Mapping[str, Any]) -> tuple[float, float]:
    quantity = float(inputs["quantity"])
    if action_type in {"tree", "potted_plants"}:
        return quantity, quantity
    if action_type == "garden_bed":
        area = inputs["planted_area_per_bed_m2"]
    else:
        area = inputs["installed_wall_area_per_unit_m2"]
    return quantity * float(area["minimum"]), quantity * float(area["maximum"])


def estimate_action_costs(
    action_type: str,
    inputs: Mapping[str, Any],
    cost_rows: Iterable[Mapping[str, str]],
) -> list[dict[str, Any]]:
    """Calculate source-backed cost ranges at the source's documented unit."""

    if action_type not in COST_OPTIONS:
        raise ValueError(f"unsupported action_type: {action_type}")
    minimum_units, maximum_units = _cost_units(action_type, inputs)
    wanted = set(COST_OPTIONS[action_type])
    requested_tree_type = str(inputs.get("tree_type") or "").strip().casefold()
    estimates = []
    for row in cost_rows:
        if row["option_code"] not in wanted:
            continue
        if (
            action_type == "tree"
            and requested_tree_type
            and str(row.get("tree_type") or "").strip().casefold()
            != requested_tree_type
        ):
            continue
        estimates.append(
            {
                "option_code": row["option_code"],
                "cost_context": row["cost_context"],
                "cost_basis": row["cost_basis"],
                "tree_type": row.get("tree_type") or None,
                "botanical_name": row.get("botanical_name") or None,
                "minimum_cost_aud": round(minimum_units * float(row["minimum_cost"]), 2),
                "maximum_cost_aud": round(maximum_units * float(row["maximum_cost"]), 2),
                "confidence_level": row["confidence_level"],
                "valid_to": row["valid_to"],
                "source_name": row["source_name"],
                "source_url": row["source_url"],
                "disclaimer": "Indicative estimate only; not a supplier quotation.",
            }
        )
    if not estimates:
        detail = f" and tree type {inputs['tree_type']!r}" if requested_tree_type else ""
        raise ValueError(f"no reviewed cost estimate found for {action_type}{detail}")
    return estimates


def validate_action_output(action_type: str, output: Mapping[str, Any]) -> list[str]:
    """Return calculation or semantic failures for one action output."""

    failures = []
    area = output["impact_area_range_m2"]
    if area["minimum"] < 0 or area["maximum"] < area["minimum"]:
        failures.append("impact-area range is invalid")
    temperature = output["temperature_change_range_c"]
    if action_type == "potted_plants" and temperature is not None:
        failures.append("potted plants must not expose a temperature range")
    if temperature is not None:
        if temperature["minimum"] < 0 or temperature["maximum"] < temperature["minimum"]:
            failures.append("temperature range is invalid")
        if action_type == "green_wall" and temperature["metric"] != "wall_surface_temperature":
            failures.append("green-wall temperature must retain wall-surface scope")
        if action_type in {"tree", "garden_bed"} and temperature["metric"] != "land_surface_temperature":
            failures.append("land greening must retain land-surface-temperature scope")
    if output.get("exact_after_temperature_permitted") is not False:
        failures.append("exact after-temperature is not explicitly prohibited")
    return failures


def evaluate_property_actions(
    property_result: Mapping[str, Any],
    *,
    contract: Mapping[str, Any] | None = None,
    cost_rows: Iterable[Mapping[str, str]] | None = None,
    action_types: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Apply the configured action examples to one validated property baseline."""

    actual = property_result.get("actual")
    if not actual:
        raise ValueError("property result has no application-ready baseline")
    parcel_area = float(actual["parcel_area_m2"])
    if parcel_area <= 0:
        raise ValueError("property parcel area must be positive")
    definitions = dict(contract or load_input_contract())
    rows = list(cost_rows or load_cost_rows())
    selected_actions = list(action_types or definitions["actions"])
    action_results = []
    for action_type in selected_actions:
        definition = definitions["actions"][action_type]
        example = definition.get("iteration_1_example") or definition.get("example_only")
        inputs = dict(example)
        if action_type in {"tree", "garden_bed"}:
            inputs["site_area_m2"] = parcel_area
        output = calculate_simulated_action(action_type, inputs, contract=definitions)
        costs = estimate_action_costs(action_type, inputs, rows)
        failures = validate_action_output(action_type, output)
        if any(item["maximum_cost_aud"] < item["minimum_cost_aud"] for item in costs):
            failures.append("cost range is invalid")
        action_results.append(
            {
                "action_type": action_type,
                "inputs": inputs,
                "impact_area_type": output["impact_area_type"],
                "canopy_shade_or_green_area_gain_m2": output["impact_area_range_m2"],
                "indicative_heat_reduction_range_c": output["temperature_change_range_c"],
                "estimated_costs": costs,
                "output_check_status": "PASS" if not failures else "FAIL",
                "output_check_failures": failures,
                "guaranteed_outcome": False,
            }
        )
    failures = [
        f"{result['action_type']}: {failure}"
        for result in action_results
        for failure in result["output_check_failures"]
    ]
    warnings = list(property_result.get("warnings", []))
    return {
        "scenario_code": property_result["scenario_code"],
        "zone": property_result["zone"],
        "address": property_result["requested_address"],
        "lot_size_category": actual["lot_size_category"],
        "parcel_area_m2": parcel_area,
        "baseline": {
            "land_surface_temperature_c": actual["land_surface_temperature_c"],
            "heat_classification": actual["heat_classification"],
            "neighbourhood_canopy_percentage": actual["neighbourhood_canopy_percentage"],
            "canopy_classification": actual["canopy_classification"],
            "canopy_scope": actual["canopy_scope"],
        },
        "actions": action_results,
        "validation_status": "FAIL" if failures else ("WARN" if warnings else "PASS"),
        "validation_failures": failures,
        "baseline_warnings": warnings,
        "output_limitations": [
            "Canopy/green-area gain is not added to the 500 m neighbourhood canopy percentage.",
            "Heat values are indicative reduction ranges, not predicted after-temperatures.",
            "Landsat represents land-surface temperature, not air temperature.",
            "Green-wall temperature applies only to the exterior wall surface.",
            "Costs are indicative source-backed ranges and not quotations.",
        ],
    }
