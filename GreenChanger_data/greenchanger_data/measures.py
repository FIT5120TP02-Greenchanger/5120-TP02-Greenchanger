"""Validated measures for GreenChanger Data Analytics & Insight Development."""

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


def projected_canopy_proxy_shade_m2(
    projected_canopy_m2: float,
    *,
    survival_probability: float = 1.0,
    site_suitability_factor: float = 1.0,
    overlap_factor: float = 1.0,
) -> float:
    """Return an indicative canopy-area proxy for future shade.

    This is not a sun-angle shadow model. It discounts a supplied future crown
    area for establishment survival, site suitability and overlap with other
    crowns so the result cannot silently assume that every planted tree reaches
    its full, independent mature crown.
    """

    canopy = _number("projected_canopy_m2", projected_canopy_m2)
    if canopy < 0:
        raise ValueError("projected_canopy_m2 cannot be negative")

    factors = {
        "survival_probability": survival_probability,
        "site_suitability_factor": site_suitability_factor,
        "overlap_factor": overlap_factor,
    }
    checked: dict[str, float] = {}
    for name, value in factors.items():
        checked[name] = _number(name, value)
        if not 0 <= checked[name] <= 1:
            raise ValueError(f"{name} must be between 0 and 1")

    return canopy * checked["survival_probability"] * checked[
        "site_suitability_factor"
    ] * checked["overlap_factor"]


def shade_projection_output(
    projected_canopy_m2: float,
    maturity_horizon_years: int,
    *,
    survival_probability: float = 1.0,
    site_suitability_factor: float = 1.0,
    overlap_factor: float = 1.0,
) -> dict[str, float | int | str]:
    """Return a display-safe future shade proxy with its required horizon."""

    horizon = _number("maturity_horizon_years", maturity_horizon_years)
    if horizon <= 0 or not horizon.is_integer():
        raise ValueError("maturity_horizon_years must be a positive whole number")
    shade = projected_canopy_proxy_shade_m2(
        projected_canopy_m2,
        survival_probability=survival_probability,
        site_suitability_factor=site_suitability_factor,
        overlap_factor=overlap_factor,
    )
    return {
        "status": "indicative_planning_estimate",
        "measurement_type": "canopy_area_proxy_for_shade",
        "projected_shade_m2": round(shade, 2),
        "maturity_horizon_years": int(horizon),
        "message": (
            "Canopy-area proxy at the stated horizon; not an immediate or "
            "sun-angle-specific shadow measurement."
        ),
    }


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
    projected_surface_temperature_c: float | None = None,
    *,
    model_validation_status: str = "prototype_only",
    output_precision: str = "suppressed",
    cooling_range_min_c: float | None = None,
    cooling_range_max_c: float | None = None,
) -> dict[str, float | str | None]:
    """Return a display-safe heat projection.

    Validation and output precision are separate gates. A validated model may
    expose an indicative interval without being authorised to expose a precise
    after-temperature. Prototype arithmetic remains internally testable.
    """

    allowed = {
        "draft", "prototype_only", "validation_in_progress", "validated", "retired"
    }
    if model_validation_status not in allowed:
        raise ValueError("unsupported model_validation_status")
    allowed_precision = {"suppressed", "indicative_range", "precise_point_estimate"}
    if output_precision not in allowed_precision:
        raise ValueError("unsupported output_precision")

    base = {
        "measurement_type": "land_surface_temperature",
        "projected_surface_temperature_c": None,
        "estimated_heat_reduction_c": None,
        "cooling_range_min_c": None,
        "cooling_range_max_c": None,
    }
    if model_validation_status != "validated" or output_precision == "suppressed":
        return {
            **base,
            "status": "indicative_model_not_validated",
            "message": (
                "Surface-cooling output is suppressed until a locally calibrated "
                "model passes validation and declares an approved precision."
            ),
        }

    if output_precision == "indicative_range":
        minimum = _number("cooling_range_min_c", cooling_range_min_c)
        maximum = _number("cooling_range_max_c", cooling_range_max_c)
        if minimum < 0 or maximum < minimum:
            raise ValueError(
                "cooling range must be non-negative and maximum must be at least minimum"
            )
        return {
            **base,
            "status": "validated_indicative_range",
            "cooling_range_min_c": minimum,
            "cooling_range_max_c": maximum,
            "message": (
                "Indicative daytime land-surface cooling under comparable "
                "hot-weather conditions; not a guaranteed air-temperature change."
            ),
        }

    if projected_surface_temperature_c is None:
        raise ValueError(
            "projected_surface_temperature_c is required for a precise point estimate"
        )
    return {
        **base,
        "status": "validated_model_output",
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
