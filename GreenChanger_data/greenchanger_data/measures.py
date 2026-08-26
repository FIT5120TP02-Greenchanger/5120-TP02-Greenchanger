"""Validated analytical measures for GreenChanger KPI 2."""

from __future__ import annotations

from math import isfinite
from typing import Iterable, Mapping


def _number(name: str, value: float | int) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be numeric") from error
    if not isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def canopy_gain_m2(baseline_canopy_m2: float, projected_canopy_m2: float) -> float:
    """Return projected canopy area minus baseline canopy area."""

    baseline = _number("baseline_canopy_m2", baseline_canopy_m2)
    projected = _number("projected_canopy_m2", projected_canopy_m2)
    if baseline < 0 or projected < 0:
        raise ValueError("canopy areas cannot be negative")
    return projected - baseline


def greening_gain_pct(baseline_greenery_pct: float, projected_greenery_pct: float) -> float:
    """Return the percentage-point change in total greenery."""

    baseline = _number("baseline_greenery_pct", baseline_greenery_pct)
    projected = _number("projected_greenery_pct", projected_greenery_pct)
    if not 0 <= baseline <= 100 or not 0 <= projected <= 100:
        raise ValueError("greenery percentages must be between 0 and 100")
    return projected - baseline


def estimated_heat_reduction_c(
    baseline_surface_temperature_c: float,
    projected_surface_temperature_c: float,
) -> float:
    """Return baseline LST minus modelled scenario LST in degrees Celsius."""

    baseline = _number(
        "baseline_surface_temperature_c", baseline_surface_temperature_c
    )
    projected = _number(
        "projected_surface_temperature_c", projected_surface_temperature_c
    )
    return baseline - projected


def heat_projection_output(
    baseline_surface_temperature_c: float,
    projected_surface_temperature_c: float,
    *,
    model_validation_status: str = "prototype_only",
) -> dict[str, float | str | None]:
    """Return a display-safe heat projection.

    A point estimate is exposed only for a model explicitly marked validated.
    Prototype arithmetic remains testable internally but cannot become a
    resident-facing temperature claim by accident.
    """

    allowed = {
        "draft", "prototype_only", "validation_in_progress", "validated", "retired"
    }
    if model_validation_status not in allowed:
        raise ValueError("unsupported model_validation_status")
    if model_validation_status != "validated":
        return {
            "status": "indicative_model_not_validated",
            "measurement_type": "land_surface_temperature",
            "projected_surface_temperature_c": None,
            "estimated_heat_reduction_c": None,
            "message": "A precise after-temperature is suppressed until model validation passes.",
        }
    return {
        "status": "validated_model_output",
        "measurement_type": "land_surface_temperature",
        "projected_surface_temperature_c": _number(
            "projected_surface_temperature_c", projected_surface_temperature_c
        ),
        "estimated_heat_reduction_c": estimated_heat_reduction_c(
            baseline_surface_temperature_c, projected_surface_temperature_c
        ),
        "message": None,
    }


def cost_per_canopy_m2(total_cost: float, canopy_gain: float) -> float:
    """Return indicative cost per square metre of positive canopy gain."""

    cost = _number("total_cost", total_cost)
    gain = _number("canopy_gain", canopy_gain)
    if cost < 0:
        raise ValueError("total_cost cannot be negative")
    if gain <= 0:
        raise ValueError("canopy_gain must be greater than zero")
    return cost / gain


def community_totals(interventions: Iterable[Mapping[str, float]]) -> dict[str, float]:
    """Aggregate quantities, areas and indicative min/max community costs."""

    quantity = 0.0
    intervention_area_m2 = 0.0
    minimum_cost = 0.0
    maximum_cost = 0.0

    for intervention in interventions:
        row_quantity = _number("quantity", intervention.get("quantity", 0))
        row_area = _number(
            "intervention_area_m2", intervention.get("intervention_area_m2", 0)
        )
        row_minimum = _number("minimum_cost", intervention.get("minimum_cost", 0))
        row_maximum = _number("maximum_cost", intervention.get("maximum_cost", 0))

        if min(row_quantity, row_area, row_minimum, row_maximum) < 0:
            raise ValueError("community intervention values cannot be negative")
        if row_maximum < row_minimum:
            raise ValueError("maximum_cost cannot be lower than minimum_cost")

        quantity += row_quantity
        intervention_area_m2 += row_area
        minimum_cost += row_minimum
        maximum_cost += row_maximum

    return {
        "quantity": quantity,
        "intervention_area_m2": intervention_area_m2,
        "minimum_cost": minimum_cost,
        "maximum_cost": maximum_cost,
    }
