"""Versioned Residential Greening Scenario Simulation input preparation."""

from __future__ import annotations

import json
from math import isfinite
from pathlib import Path
from typing import Any, Mapping

from .intervention_model import calculate_intervention_impact


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "config" / "residential_greening_simulation_inputs.json"
SUPPORTED_ACTIONS = {"tree", "potted_plants", "garden_bed", "green_wall"}


def _number(name: str, value: object) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be numeric") from error
    if not isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _positive_integer(name: str, value: object) -> int:
    result = _number(name, value)
    if result <= 0 or not result.is_integer():
        raise ValueError(f"{name} must be a positive whole number")
    return int(result)


def _range(name: str, value: object, *, fraction: bool = False) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must contain minimum and maximum")
    minimum = _number(f"{name}.minimum", value.get("minimum"))
    maximum = _number(f"{name}.maximum", value.get("maximum"))
    if minimum < 0 or maximum < minimum:
        raise ValueError(f"{name} must be a non-negative ordered range")
    if fraction and maximum > 1:
        raise ValueError(f"{name} must be between 0 and 1")
    return {"minimum": minimum, "maximum": maximum}


def _multiply_ranges(*ranges: Mapping[str, float]) -> dict[str, float]:
    minimum = 1.0
    maximum = 1.0
    for value in ranges:
        minimum *= value["minimum"]
        maximum *= value["maximum"]
    return {"minimum": minimum, "maximum": maximum}


def load_input_contract(path: Path | None = None) -> dict[str, Any]:
    """Load and structurally validate the versioned scenario-input contract."""

    contract = json.loads((path or DEFAULT_CONTRACT).read_text(encoding="utf-8"))
    if set(contract.get("actions", {})) != SUPPORTED_ACTIONS:
        raise ValueError("input contract must define exactly the four supported actions")
    policy = contract.get("output_policy", {})
    if policy.get("precision") != "indicative_range":
        raise ValueError("scenario outputs must use indicative_range precision")
    if policy.get("exact_after_temperature_permitted") is not False:
        raise ValueError("exact after-temperature must remain prohibited")
    return contract


def prepare_model_inputs(
    action_type: str,
    inputs: Mapping[str, Any],
    *,
    contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate common inputs and translate one scenario to model-v1 inputs."""

    definitions = dict(contract or load_input_contract())
    if action_type not in SUPPORTED_ACTIONS:
        raise ValueError(f"unsupported action_type: {action_type}")
    action = definitions["actions"][action_type]
    quantity = _positive_integer("quantity", inputs.get("quantity"))
    constraints = action["quantity_constraints"]
    if quantity < constraints["minimum"]:
        raise ValueError("quantity is below the action minimum")
    if constraints.get("maximum") is not None and quantity > constraints["maximum"]:
        raise ValueError("quantity exceeds the action maximum")

    horizon = _positive_integer(
        "maturity_horizon_years", inputs.get("maturity_horizon_years")
    )
    survival = _range(
        "survival_probability", inputs.get("survival_probability"), fraction=True
    )
    suitability = _range(
        "site_suitability_factor",
        inputs.get("site_suitability_factor"),
        fraction=True,
    )

    if action_type == "tree":
        per_unit = _range(
            "projected_canopy_per_tree_m2",
            inputs.get("projected_canopy_per_tree_m2"),
        )
        overlap = _range("overlap_factor", inputs.get("overlap_factor"), fraction=True)
        site_area = _number("site_area_m2", inputs.get("site_area_m2"))
        if site_area <= 0:
            raise ValueError("site_area_m2 must be positive")
        return {
            "projected_canopy_m2": {
                "minimum": per_unit["minimum"] * quantity,
                "maximum": per_unit["maximum"] * quantity,
            },
            "survival_probability": survival,
            "site_suitability_factor": suitability,
            "overlap_factor": overlap,
            "site_area_m2": site_area,
            "maturity_horizon_years": horizon,
        }

    if action_type == "potted_plants":
        foliage = _range(
            "foliage_area_per_pot_m2", inputs.get("foliage_area_per_pot_m2")
        )
        effective_foliage = _multiply_ranges(foliage, survival, suitability)
        return {"quantity": quantity, "foliage_area_per_pot_m2": effective_foliage}

    cover = _range(
        "established_cover_fraction",
        inputs.get("established_cover_fraction"),
        fraction=True,
    )
    effective_cover = _multiply_ranges(cover, survival, suitability)
    if action_type == "garden_bed":
        per_unit = _range(
            "planted_area_per_bed_m2", inputs.get("planted_area_per_bed_m2")
        )
        return {
            "planted_area_m2": {
                "minimum": per_unit["minimum"] * quantity,
                "maximum": per_unit["maximum"] * quantity,
            },
            "established_cover_fraction": effective_cover,
            "site_area_m2": _number("site_area_m2", inputs.get("site_area_m2")),
        }

    per_unit = _range(
        "installed_wall_area_per_unit_m2",
        inputs.get("installed_wall_area_per_unit_m2"),
    )
    return {
        "installed_wall_area_m2": {
            "minimum": per_unit["minimum"] * quantity,
            "maximum": per_unit["maximum"] * quantity,
        },
        "established_cover_fraction": effective_cover,
        "target_wall_area_m2": _number(
            "target_wall_area_m2", inputs.get("target_wall_area_m2")
        ),
    }


def calculate_simulated_action(
    action_type: str,
    inputs: Mapping[str, Any],
    *,
    contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate one scenario and preserve its contract and uncertainty metadata."""

    definitions = dict(contract or load_input_contract())
    model_inputs = prepare_model_inputs(action_type, inputs, contract=definitions)
    result = calculate_intervention_impact(action_type, model_inputs)
    result.update(
        {
            "input_contract_version": definitions["contract_version"],
            "quantity": int(inputs["quantity"]),
            "maturity_horizon_years": int(inputs["maturity_horizon_years"]),
            "survival_probability": inputs["survival_probability"],
            "site_suitability_factor": inputs["site_suitability_factor"],
            "exact_after_temperature_permitted": False,
            "scenario_inputs_are_guarantees": False,
        }
    )
    return result
