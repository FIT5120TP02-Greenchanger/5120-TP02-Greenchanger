"""Run and print greening actions for small, medium and large Melbourne properties."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_data.residential_scenarios import (  # noqa: E402
    evaluate_property_actions,
    load_cost_rows,
)
from greenchanger_data.scenario_inputs import load_input_contract  # noqa: E402
from greenchanger_script import db  # noqa: E402
from greenchanger_script.sanity_check_melbourne import (  # noqa: E402
    DEFAULT_SCENARIOS,
    load_scenarios,
    run as run_property_checks,
)


DEFAULT_RUN_CONFIG = ROOT / "config" / "residential_greening_property_scenarios.json"


def run(connection, run_config: dict) -> dict:
    baseline_document = load_scenarios(DEFAULT_SCENARIOS)
    scenario_codes = set(run_config["property_scenario_codes"])
    selected = [
        scenario
        for scenario in baseline_document["scenarios"]
        if scenario["scenario_code"] in scenario_codes
    ]
    missing = scenario_codes - {scenario["scenario_code"] for scenario in selected}
    if missing:
        raise ValueError("unknown property scenario codes: " + ", ".join(sorted(missing)))
    baseline_report = run_property_checks(
        connection,
        selected,
        coverage_scenarios=baseline_document["scenarios"],
    )
    contract = load_input_contract()
    if contract["contract_version"] != run_config["input_contract_version"]:
        raise ValueError("run configuration targets a different input contract")
    costs = load_cost_rows()
    results = [
        evaluate_property_actions(
            result,
            contract=contract,
            cost_rows=costs,
            action_types=run_config["action_types"],
        )
        for result in baseline_report["results"]
    ]
    counts = {status: sum(item["validation_status"] == status for item in results) for status in ("PASS", "WARN", "FAIL")}
    return {
        "scenario_set": run_config["scenario_set"],
        "as_of": baseline_report["as_of"],
        "input_contract_version": contract["contract_version"],
        "impact_model_version": contract["impact_model_version"],
        "property_count": len(results),
        "action_count": sum(len(item["actions"]) for item in results),
        "summary": counts,
        "overall_status": "FAIL" if counts["FAIL"] else ("WARN" if counts["WARN"] else "PASS"),
        "results": results,
    }


def print_report(report: dict) -> None:
    print("=== Residential Greening Scenario Simulation ===")
    print("As of:", report["as_of"])
    print("Contract:", report["input_contract_version"])
    print("Impact model:", report["impact_model_version"])
    for property_result in report["results"]:
        baseline = property_result["baseline"]
        print()
        print(
            f"[{property_result['validation_status']}] {property_result['scenario_code']} — "
            f"{property_result['lot_size_category']} — {property_result['address']}"
        )
        print(f"  Parcel: {property_result['parcel_area_m2']:.1f} m2")
        print(
            f"  Baseline: LST={baseline['land_surface_temperature_c']:.3f} C "
            f"({baseline['heat_classification']}), canopy={baseline['neighbourhood_canopy_percentage']:.2f}% "
            f"({baseline['canopy_classification']}, {baseline['canopy_scope']})"
        )
        for action in property_result["actions"]:
            area = action["canopy_shade_or_green_area_gain_m2"]
            temperature = action["indicative_heat_reduction_range_c"]
            print(
                f"  {action['action_type']}: {action['impact_area_type']}="
                f"{area['minimum']:.3f}-{area['maximum']:.3f} m2"
            )
            if temperature is None:
                print("    Heat: Unavailable (insufficient action-specific evidence)")
            else:
                print(
                    f"    Heat: {temperature['minimum']:.3f}-{temperature['maximum']:.3f} C "
                    f"indicative reduction ({temperature['metric']})"
                )
            for cost in action["estimated_costs"]:
                print(
                    f"    Cost [{cost['option_code']}]: "
                    f"AUD {cost['minimum_cost_aud']:.2f}-{cost['maximum_cost_aud']:.2f} "
                    f"({cost['confidence_level']}, valid to {cost['valid_to']})"
                )
            print("    Output checks:", action["output_check_status"])
        for warning in property_result["baseline_warnings"]:
            print("  WARN:", warning)
    print()
    print(
        f"Overall={report['overall_status']} properties={report['property_count']} "
        f"actions={report['action_count']} PASS={report['summary']['PASS']} "
        f"WARN={report['summary']['WARN']} FAIL={report['summary']['FAIL']}"
    )
    print(
        "Interpretation: output ranges are indicative and source-bounded; "
        "they are not guaranteed outcomes, after-temperatures or quotations."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_RUN_CONFIG)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    run_config = json.loads(args.config.read_text(encoding="utf-8"))
    connection = db.connect()
    try:
        report = run(connection, run_config)
    finally:
        connection.close()
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_report(report)
    raise SystemExit(1 if report["overall_status"] == "FAIL" else 0)


if __name__ == "__main__":
    main()
