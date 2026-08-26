"""Validate a staging CSV and produce a Data Quality & Preparation report."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_data.quality import validate_records  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", help="Dataset key in config/quality_rules.json")
    parser.add_argument("input", type=Path, help="Staging CSV to validate")
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config" / "quality_rules.json",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Output JSON report path; defaults to data/quality/<dataset>.json",
    )
    parser.add_argument(
        "--rejected",
        type=Path,
        default=None,
        help="Optional CSV path for rejected records.",
    )
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    try:
        rules = config["datasets"][args.dataset]
    except KeyError as error:
        raise SystemExit(f"No configured rules for dataset: {args.dataset}") from error

    with args.input.open(newline="", encoding="utf-8") as handle:
        records = list(csv.DictReader(handle))

    report = validate_records(
        args.dataset,
        records,
        rules,
        threshold_pct=float(config.get("quality_threshold_pct", 95.0)),
    )

    report_path = args.report or ROOT / "data" / "quality" / f"{args.dataset}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

    if args.rejected and report.failed_indices:
        args.rejected.parent.mkdir(parents=True, exist_ok=True)
        with args.rejected.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records[index] for index in report.failed_indices)

    print(f"Dataset: {report.dataset_name}")
    print(f"Records: {report.total_records}")
    print(f"Pass rate: {report.pass_rate:.2f}%")
    print(f"95% quality gate: {'PASS' if report.passed_gate else 'FAIL'}")
    print(f"Report: {report_path}")

    if not report.passed_gate:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
