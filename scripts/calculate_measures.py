"""Calculate GreenShift KPI 2 measures from command-line inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_data.measures import (  # noqa: E402
    canopy_gain_m2,
    estimated_heat_reduction_c,
    greening_gain_pct,
)


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
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    values = json.loads(args.input.read_text(encoding="utf-8")) if args.input else {}
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
            parser.error(f"missing input: {name}")

    result = {
        "canopy_gain_m2": canopy_gain_m2(
            values["baseline_canopy_m2"], values["projected_canopy_m2"]
        ),
        "greening_gain_pct": greening_gain_pct(
            values["baseline_greenery_pct"], values["projected_greenery_pct"]
        ),
        "estimated_heat_reduction_c": estimated_heat_reduction_c(
            values["baseline_surface_temperature_c"],
            values["projected_surface_temperature_c"],
        ),
        "result_type": "modelled_scenario",
    }
    text = json.dumps(result, indent=2)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
