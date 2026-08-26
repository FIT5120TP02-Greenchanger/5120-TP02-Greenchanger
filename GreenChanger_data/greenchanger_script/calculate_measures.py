"""Calculate GreenChanger Data Analytics & Insight Development measures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_data.measures import (  # noqa: E402
    canopy_gain_m2,
    community_totals,
    cost_per_canopy_m2,
    estimated_heat_reduction_c,
    greening_gain_pct,
    heat_projection_output,
)


SAMPLE_INPUTS = {
    "baseline_canopy_m2": 25,
    "projected_canopy_m2": 40,
    "baseline_greenery_pct": 18.5,
    "projected_greenery_pct": 31,
    "baseline_surface_temperature_c": 43.2,
    "projected_surface_temperature_c": 40.7,
    "total_cost": 1200,
    "community_interventions": [
        {
            "quantity": 2,
            "intervention_area_m2": 20,
            "minimum_cost": 400,
            "maximum_cost": 700,
        },
        {
            "quantity": 1,
            "intervention_area_m2": 8,
            "minimum_cost": 250,
            "maximum_cost": 400,
        },
    ],
}


def calculate_all(values: dict) -> dict:
    """Calculate every measure supported by the supplied inputs."""

    canopy_gain = canopy_gain_m2(
        values["baseline_canopy_m2"], values["projected_canopy_m2"]
    )
    result = {
        "canopy_gain_m2": canopy_gain,
        "greening_gain_pct": greening_gain_pct(
            values["baseline_greenery_pct"], values["projected_greenery_pct"]
        ),
        "heat_projection": heat_projection_output(
            values["baseline_surface_temperature_c"],
            values["projected_surface_temperature_c"],
            model_validation_status=values.get("model_validation_status", "prototype_only"),
        ),
        "result_type": "modelled_scenario",
    }
    if "total_cost" in values:
        result["cost_per_canopy_m2"] = cost_per_canopy_m2(
            values["total_cost"], canopy_gain
        )
    if "community_interventions" in values:
        result["community_totals"] = community_totals(
            values["community_interventions"]
        )
    return result


def sample_report() -> dict:
    """Return formulas, sample inputs and outputs for every calculation."""

    outputs = calculate_all(SAMPLE_INPUTS)
    return {
        "sample": True,
        "calculations": {
            "canopy_gain_m2": {
                "formula": "projected_canopy_m2 - baseline_canopy_m2",
                "sample_inputs": {"projected_canopy_m2": 40, "baseline_canopy_m2": 25},
                "sample_output": outputs["canopy_gain_m2"],
                "unit": "m2",
            },
            "greening_gain_pct": {
                "formula": "projected_greenery_pct - baseline_greenery_pct",
                "sample_inputs": {"projected_greenery_pct": 31, "baseline_greenery_pct": 18.5},
                "sample_output": outputs["greening_gain_pct"],
                "unit": "percentage_points",
            },
            "estimated_heat_reduction_c": {
                "formula": "baseline_surface_temperature_c - projected_surface_temperature_c",
                "sample_inputs": {
                    "baseline_surface_temperature_c": 43.2,
                    "projected_surface_temperature_c": 40.7,
                },
                "sample_output": outputs["heat_projection"],
                "unit": "degC",
                "note": "Precise output is suppressed because the prototype model is not validated.",
            },
            "cost_per_canopy_m2": {
                "formula": "total_cost / canopy_gain_m2",
                "sample_inputs": {"total_cost": 1200, "canopy_gain_m2": 15},
                "sample_output": outputs["cost_per_canopy_m2"],
                "unit": "AUD_per_m2",
            },
            "community_totals": {
                "formula": "sum each intervention quantity, area, minimum cost and maximum cost",
                "sample_inputs": SAMPLE_INPUTS["community_interventions"],
                "sample_output": outputs["community_totals"],
                "units": {
                    "quantity": "interventions",
                    "intervention_area_m2": "m2",
                    "minimum_cost": "AUD",
                    "maximum_cost": "AUD",
                },
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        help="Optional JSON file containing all six measure inputs.",
    )
    parser.add_argument("--baseline-canopy-m2", type=float)
    parser.add_argument("--projected-canopy-m2", type=float)
    parser.add_argument("--baseline-greenery-pct", type=float)
    parser.add_argument("--projected-greenery-pct", type=float)
    parser.add_argument("--baseline-surface-temperature-c", type=float)
    parser.add_argument("--projected-surface-temperature-c", type=float)
    parser.add_argument("--total-cost", type=float)
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Print formulas and sample outputs for every calculation.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    supplied_measure_value = any(
        getattr(args, name) is not None
        for name in (
            "baseline_canopy_m2",
            "projected_canopy_m2",
            "baseline_greenery_pct",
            "projected_greenery_pct",
            "baseline_surface_temperature_c",
            "projected_surface_temperature_c",
            "total_cost",
        )
    )
    show_sample = args.sample or (args.input is None and not supplied_measure_value)
    values = (
        json.loads(args.input.read_text(encoding="utf-8")) if args.input else {}
    )
    names = (
        "baseline_canopy_m2",
        "projected_canopy_m2",
        "baseline_greenery_pct",
        "projected_greenery_pct",
        "baseline_surface_temperature_c",
        "projected_surface_temperature_c",
    )
    for name in names:
        command_value = getattr(args, name)
        if command_value is not None:
            values[name] = command_value
        if name not in values:
            if not show_sample:
                parser.error(f"missing input: {name}")

    if args.total_cost is not None:
        values["total_cost"] = args.total_cost

    result = sample_report() if show_sample else calculate_all(values)
    text = json.dumps(result, indent=2)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
