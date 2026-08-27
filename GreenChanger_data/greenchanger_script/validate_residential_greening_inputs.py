"""Validate and print Residential Greening Scenario Simulation examples."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_data.scenario_inputs import (  # noqa: E402
    calculate_simulated_action,
    load_input_contract,
)


def main() -> None:
    contract = load_input_contract()
    results = {}
    for action_type, definition in contract["actions"].items():
        example = definition.get("iteration_1_example") or definition.get("example_only")
        inputs = dict(example)
        results[action_type] = calculate_simulated_action(
            action_type, inputs, contract=contract
        )
    print(
        json.dumps(
            {
                "contract_version": contract["contract_version"],
                "scope": contract["scope"],
                "examples_are_application_defaults": False,
                "results": results,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
