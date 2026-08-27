"""Print real Greater Melbourne parcel/canopy/tree/heat sanity checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_data.melbourne_sanity import (  # noqa: E402
    build_report,
    evaluate_property_scenario,
)
from greenchanger_script import db  # noqa: E402


DEFAULT_SCENARIOS = ROOT / "config" / "melbourne_sanity_scenarios.json"


def load_scenarios(path: Path = DEFAULT_SCENARIOS) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_scenario(connection, scenario: dict) -> tuple[list[dict], bool | None]:
    """Fetch an exact property baseline and independently confirm 2GMEL coverage."""

    address = scenario["address"]
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT *
            FROM get_property_baseline(%s, 50)
            WHERE UPPER(full_address) = UPPER(%s)
            """,
            (address, address),
        )
        rows = cursor.fetchall()
        if not rows:
            return rows, None
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM analysis_area AS area
                JOIN address AS candidate ON candidate.address_id = %s
                WHERE area.source_area_code = '2GMEL'
                  AND area.source_year = 2026
                  AND area.support_status = 'supported'
                  AND ST_Covers(area.boundary_geometry, candidate.address_location)
            ) AS inside_greater_melbourne
            """,
            (rows[0]["address_id"],),
        )
        return rows, cursor.fetchone()["inside_greater_melbourne"]


def run(
    connection,
    scenarios: list[dict],
    *,
    coverage_scenarios: list[dict] | None = None,
) -> dict:
    with connection.cursor() as cursor:
        cursor.execute("SELECT CURRENT_TIMESTAMP AS as_of")
        as_of = cursor.fetchone()["as_of"]
    results = []
    for scenario in scenarios:
        rows, inside = fetch_scenario(connection, scenario)
        results.append(
            evaluate_property_scenario(
                scenario, rows, inside_greater_melbourne=inside, as_of=as_of.date()
            )
        )
    report = build_report(coverage_scenarios or scenarios, results, as_of=as_of)
    report["summary"]["scenario_count"] = len(results)
    return report


def print_report(report: dict) -> None:
    print("=== Greater Melbourne property sanity check ===")
    print("As of:", report["as_of"])
    print("Scope:", report["validation_scope"])
    if report["scenario_coverage_failures"]:
        print("Coverage warnings:")
        for message in report["scenario_coverage_failures"]:
            print("  -", message)
    for result in report["results"]:
        print()
        print(f"[{result['status']}] {result['scenario_code']} — {result['zone']}")
        print("  Address:", result["requested_address"])
        print("  Context:", result["context"])
        actual = result["actual"]
        if actual:
            print(
                "  Location:",
                f"{actual['locality']} {actual['postcode']}",
                f"({actual['latitude']:.6f}, {actual['longitude']:.6f})",
                f"inside 2GMEL={actual['inside_greater_melbourne']}",
            )
            print(
                "  Parcel:",
                f"{actual['parcel_area_m2']:.1f} m2",
                f"category={actual['lot_size_category']}",
            )
            print(
                "  Heat:",
                f"{actual['land_surface_temperature_c']:.2f} C",
                f"metric={actual['temperature_measurement_type']}",
                f"observed={actual['heat_observed_on']}",
            )
            print(
                "  Canopy:",
                f"{actual['neighbourhood_canopy_percentage']:.2f}%",
                f"scope={actual['canopy_scope']}",
                f"source={actual['canopy_source_type']}",
                f"observed={actual['canopy_observed_on']}",
            )
            print(
                "  Trees:",
                f"mapped points in parcel={actual['mapped_property_tree_count']}",
                f"status={actual['tree_data_status']}",
            )
            weather_distance = actual["weather_station_distance_km"]
            print(
                "  Weather context:",
                actual["weather_station"],
                f"distance={weather_distance:.1f} km"
                if weather_distance is not None
                else "distance=unavailable",
            )
        for message in result["failures"]:
            print("  FAIL:", message)
        for message in result["warnings"]:
            print("  WARN:", message)

    summary = report["summary"]
    print()
    print("=== Summary ===")
    print(
        f"Overall={report['overall_status']} scenarios={summary['scenario_count']} "
        f"PASS={summary['PASS']} WARN={summary['WARN']} FAIL={summary['FAIL']}"
    )
    print(
        "Interpretation: PASS/WARN confirms query and range plausibility only; "
        "visual imagery or field checks are still required for ground truth."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario-file", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument(
        "--scenario",
        action="append",
        help="Run only a named scenario code; may be supplied more than once.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Return a non-zero exit code when any warning is found.",
    )
    args = parser.parse_args()

    scenario_document = load_scenarios(args.scenario_file)
    all_scenarios = scenario_document["scenarios"]
    scenarios = all_scenarios
    if args.scenario:
        selected = set(args.scenario)
        scenarios = [s for s in scenarios if s["scenario_code"] in selected]
        missing = selected - {s["scenario_code"] for s in scenarios}
        if missing:
            parser.error("unknown scenario code(s): " + ", ".join(sorted(missing)))

    connection = db.connect()
    try:
        report = run(connection, scenarios, coverage_scenarios=all_scenarios)
    finally:
        connection.close()

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)

    has_failures = report["summary"]["FAIL"] > 0
    has_warnings = report["summary"]["WARN"] > 0
    raise SystemExit(1 if has_failures or (args.fail_on_warning and has_warnings) else 0)


if __name__ == "__main__":
    main()
