"""Validate literature-bounded intervention ranges and optionally record status."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_data.intervention_model import (  # noqa: E402
    evaluate_validation_cases,
    load_parameter_registry,
)
from greenchanger_script import db  # noqa: E402


DEFAULT_CASES = ROOT / "tests" / "fixtures" / "intervention_evidence_cases.json"


def run_validation(cases_path: Path = DEFAULT_CASES) -> dict:
    """Run the versioned evidence cases without changing database state."""

    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    return evaluate_validation_cases(cases, registry=load_parameter_registry())


def persist_validation(connection, report: dict) -> str:
    """Record the run and validate the model only when every case passed."""

    from psycopg.types.json import Jsonb

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT model_version_id, validation_status
            FROM model_version
            WHERE model_name = %s AND version_label = %s
            FOR UPDATE
            """,
            (report["model_name"], report["model_version"]),
        )
        model = cursor.fetchone()
        if model is None:
            raise RuntimeError(
                "model version is missing; apply migration 015 before updating status"
            )

        cursor.execute(
            """
            INSERT INTO intervention_model_validation_run (
                model_version_id, case_count, passed_count, failed_count,
                all_passed, validation_scope, completed_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            RETURNING validation_run_id
            """,
            (
                model["model_version_id"],
                report["case_count"],
                report["passed_count"],
                report["failed_count"],
                report["all_passed"],
                report["validation_scope"],
            ),
        )
        run_id = cursor.fetchone()["validation_run_id"]
        for result in report["results"]:
            cursor.execute(
                """
                INSERT INTO intervention_model_validation_result (
                    validation_run_id, case_code, source_keys, expected_output,
                    actual_output, passed, failure_messages
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    run_id,
                    result["case_code"],
                    result["source_keys"],
                    Jsonb(result["expected"]),
                    Jsonb(result["actual"]),
                    result["passed"],
                    result["failures"],
                ),
            )

        if report["all_passed"]:
            cursor.execute(
                """
                UPDATE model_version
                SET validation_status = 'validated',
                    validation_completed_at = CURRENT_TIMESTAMP,
                    validation_summary = %s
                WHERE model_version_id = %s
                """,
                (
                    (
                        f"All {report['case_count']} literature-evidence cases passed. "
                        "Validated only for indicative, literature-bounded ranges; "
                        "not for precise or causal after-temperature claims."
                    ),
                    model["model_version_id"],
                ),
            )
            status = "validated"
        else:
            cursor.execute(
                """
                UPDATE model_version
                SET validation_status = 'validation_in_progress',
                    validation_completed_at = NULL,
                    validation_summary = %s
                WHERE model_version_id = %s
                """,
                (
                    (
                        f"Validation failed: {report['failed_count']} of "
                        f"{report['case_count']} evidence cases failed."
                    ),
                    model["model_version_id"],
                ),
            )
            status = "validation_in_progress"
    connection.commit()
    return status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--update-status",
        action="store_true",
        help="Record results and update model status in the configured database.",
    )
    parser.add_argument(
        "--confirm-shared",
        action="store_true",
        help="Required with --update-status for shared Aurora.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.update_status and not db.is_local() and not args.confirm_shared:
        sys.exit(
            "Refusing to update the shared model without --confirm-shared.\n"
            "Run without --update-status to inspect the report first."
        )

    report = run_validation(args.cases)
    if args.update_status:
        connection = db.connect()
        try:
            report["database_status"] = persist_validation(connection, report)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    output = json.dumps(report, indent=2)
    print(output)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    if not report["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
