"""Unified GreenShift ingestion jobs for PostgreSQL/PostGIS.

Examples:
    python ingestion.py sources
    python ingestion.py bom
    python ingestion.py costs --cost-file data/reference/cost_estimates.csv
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Callable, Sequence

import db
from greenchanger_data.bom import (
    DEFAULT_BOM_URL,
    extract_rows,
    fetch_observations,
    normalise_rows,
    save_raw,
)
from greenchanger_data.quality import QualityReport, validate_records
from greenchanger_data.sources import load_source_registry, sha256_file


ROOT = Path(__file__).resolve().parent
BATCH_SIZE = 2_000
TARGET_SRID = 7855
DATASETS_CONFIG = ROOT / "config" / "datasets.json"
QUALITY_CONFIG = ROOT / "config" / "quality_rules.json"
DEFAULT_COST_FILE = ROOT / "data" / "reference" / "cost_estimates_template.csv"


def write_batches(connection, sql: str, rows: Sequence[Sequence[Any]]) -> int:
    """Send PostgreSQL writes in bounded batches."""

    with connection.cursor() as cursor:
        for start in range(0, len(rows), BATCH_SIZE):
            cursor.executemany(sql, rows[start : start + BATCH_SIZE])
    return len(rows)


def quality_configuration(dataset_key: str) -> tuple[list[dict[str, Any]], float]:
    config = json.loads(QUALITY_CONFIG.read_text(encoding="utf-8"))
    try:
        rules = config["datasets"][dataset_key]
    except KeyError as error:
        raise ValueError(f"No quality rules configured for {dataset_key}") from error
    return rules, float(config.get("quality_threshold_pct", 95.0))


def source_id(connection, source_name: str, publisher: str):
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT source_id FROM dataset_source
               WHERE source_name = %s AND publisher = %s""",
            (source_name, publisher),
        )
        row = cursor.fetchone()
    if row is None:
        raise ValueError(
            f"Source not registered: {source_name}. Run `python ingestion.py sources`."
        )
    return row["source_id"]


def create_dataset_version(
    connection,
    *,
    registered_source_id,
    row_count: int,
    checksum: str,
    observed_from=None,
    observed_to=None,
):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO dataset_version (
                source_id, source_observed_from, source_observed_to,
                raw_row_count, checksum
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING dataset_version_id
            """,
            (
                registered_source_id,
                observed_from,
                observed_to,
                row_count,
                checksum,
            ),
        )
        return cursor.fetchone()["dataset_version_id"]


def quality_dimension(rule_type: str) -> str:
    return {
        "required": "completeness",
        "unique": "uniqueness",
        "range": "validity",
        "allowed": "validity",
        "field_order": "consistency",
    }[rule_type]


def record_quality_run(connection, dataset_version_id, report: QualityReport) -> None:
    """Save the record-level gate and each rule result for KPI 1 evidence."""

    run_status = "passed" if report.passed_gate else "failed"
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO data_quality_run (
                dataset_version_id, completed_at, assessed_record_count,
                passing_record_count, failing_record_count, overall_pass_rate,
                run_status
            )
            VALUES (%s, CURRENT_TIMESTAMP, %s, %s, %s, %s, %s)
            RETURNING quality_run_id
            """,
            (
                dataset_version_id,
                report.total_records,
                report.passing_records,
                report.failing_records,
                report.pass_rate,
                run_status,
            ),
        )
        quality_run_id = cursor.fetchone()["quality_run_id"]

        for result in report.rule_results:
            cursor.execute(
                """
                INSERT INTO data_quality_rule (
                    rule_code, rule_name, quality_dimension, target_table,
                    rule_description, minimum_pass_rate
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (rule_code) DO UPDATE SET
                    rule_name = EXCLUDED.rule_name,
                    quality_dimension = EXCLUDED.quality_dimension,
                    target_table = EXCLUDED.target_table,
                    rule_description = EXCLUDED.rule_description,
                    minimum_pass_rate = EXCLUDED.minimum_pass_rate,
                    active = TRUE
                RETURNING quality_rule_id
                """,
                (
                    result.rule_code,
                    result.rule_code.replace("_", " ").title(),
                    quality_dimension(result.rule_type),
                    report.dataset_name,
                    f"Configured {result.rule_type} check for {report.dataset_name}.",
                    report.threshold_pct,
                ),
            )
            rule_id = cursor.fetchone()["quality_rule_id"]
            cursor.execute(
                """
                INSERT INTO data_quality_result (
                    quality_run_id, quality_rule_id, assessed_count,
                    passed_count, failed_count, pass_rate, sample_failure,
                    result_status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                """,
                (
                    quality_run_id,
                    rule_id,
                    result.assessed_count,
                    result.passed_count,
                    result.failed_count,
                    result.pass_rate,
                    json.dumps({"failed_indices": list(result.failed_indices[:20])}),
                    "passed" if result.pass_rate >= report.threshold_pct else "failed",
                ),
            )

        cursor.execute(
            """UPDATE dataset_version
               SET quality_pass_rate = %s, quality_status = %s
               WHERE dataset_version_id = %s""",
            (report.pass_rate, run_status, dataset_version_id),
        )


def sync_sources(connection, _args: argparse.Namespace) -> dict[str, Any]:
    """Synchronise config/datasets.json with dataset_source."""

    registry = load_source_registry(DATASETS_CONFIG)
    rows = [
        (
            source["name"],
            source["publisher"],
            source["url"],
            source.get("licence"),
            source["category"],
            source["coverage"],
            source.get("access_method"),
            source.get("update_frequency"),
        )
        for source in registry["datasets"]
    ]
    written = write_batches(
        connection,
        """
        INSERT INTO dataset_source (
            source_name, publisher, source_url, licence, source_category,
            geographic_coverage, access_method, update_frequency
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (source_name, publisher) DO UPDATE SET
            source_url = EXCLUDED.source_url,
            licence = EXCLUDED.licence,
            source_category = EXCLUDED.source_category,
            geographic_coverage = EXCLUDED.geographic_coverage,
            access_method = EXCLUDED.access_method,
            update_frequency = EXCLUDED.update_frequency
        """,
        rows,
    )
    return {
        "rows_in": len(rows),
        "rows_written": written,
        "rows_rejected": 0,
        "message": f"{written} source definitions synchronised",
    }


def ingest_bom(connection, args: argparse.Namespace) -> dict[str, Any]:
    """Fetch, preserve, validate, version and integrate BOM observations."""

    document = fetch_observations(args.bom_url)
    raw_rows = extract_rows(document)
    rows = normalise_rows(raw_rows)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = ROOT / "data" / "raw" / "bom" / f"observations_{stamp}.json"
    save_raw(document, raw_path)

    registered_source_id = source_id(
        connection,
        "BOM Melbourne Olympic Park observations",
        "Bureau of Meteorology",
    )
    dates = sorted(row["observed_at"][:10] for row in rows if row["observed_at"])
    version_id = create_dataset_version(
        connection,
        registered_source_id=registered_source_id,
        row_count=len(raw_rows),
        checksum=sha256_file(raw_path),
        observed_from=dates[0] if dates else None,
        observed_to=dates[-1] if dates else None,
    )

    rules, threshold = quality_configuration("weather_observation")
    report = validate_records("weather_observation", rows, rules, threshold_pct=threshold)
    record_quality_run(connection, version_id, report)
    if not report.passed_gate:
        connection.commit()  # retain failed-version and quality evidence
        return {
            "rows_in": len(raw_rows),
            "rows_written": 0,
            "rows_rejected": report.failing_records,
            "quality_pass_rate": report.pass_rate,
            "message": "BOM extract failed the quality gate; nothing integrated",
        }

    sql = f"""
        INSERT INTO weather_observation (
            dataset_version_id, station_code, station_name, observed_at,
            air_temperature_c, apparent_temperature_c, humidity_pct,
            wind_speed_ms, rainfall_since_9am_mm, observation_location,
            quality_status
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s,
            CASE WHEN %s IS NULL THEN NULL
                 ELSE ST_Transform(ST_GeomFromText(%s, %s), {TARGET_SRID}) END,
            'passed'
        )
        ON CONFLICT (dataset_version_id, station_code, observed_at) DO UPDATE SET
            station_name = EXCLUDED.station_name,
            air_temperature_c = EXCLUDED.air_temperature_c,
            apparent_temperature_c = EXCLUDED.apparent_temperature_c,
            humidity_pct = EXCLUDED.humidity_pct,
            wind_speed_ms = EXCLUDED.wind_speed_ms,
            rainfall_since_9am_mm = EXCLUDED.rainfall_since_9am_mm,
            observation_location = EXCLUDED.observation_location,
            quality_status = EXCLUDED.quality_status
    """
    values = [
        (
            version_id,
            row["station_code"], row["station_name"], row["observed_at"],
            row["air_temperature_c"], row["apparent_temperature_c"],
            row["humidity_pct"], row["wind_speed_ms"],
            row["rainfall_since_9am_mm"], row["geometry_wkt"],
            row["geometry_wkt"], row["source_srid"],
        )
        for row in rows
    ]
    written = write_batches(connection, sql, values)
    with connection.cursor() as cursor:
        cursor.execute(
            """UPDATE dataset_version
               SET integration_status = 'integrated',
                   publication_status = 'application_ready'
               WHERE dataset_version_id = %s""",
            (version_id,),
        )
    return {
        "rows_in": len(raw_rows),
        "rows_written": written,
        "rows_rejected": report.failing_records,
        "quality_pass_rate": report.pass_rate,
        "dataset_version_id": str(version_id),
        "message": f"{written} BOM observations integrated from {raw_path.name}",
    }


def optional_float(value: str | None) -> float | None:
    return float(value) if value not in (None, "") else None


def optional_bool(value: str | None) -> bool | None:
    if value in (None, ""):
        return None
    normalised = value.strip().casefold()
    if normalised not in {"true", "false", "1", "0", "yes", "no"}:
        raise ValueError(f"Invalid Boolean value: {value}")
    return normalised in {"true", "1", "yes"}


def ingest_costs(connection, args: argparse.Namespace) -> dict[str, Any]:
    """Validate and insert manually verified, versioned cost estimates."""

    with args.cost_file.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    rules, threshold = quality_configuration("cost_estimate")
    report = validate_records("cost_estimate", rows, rules, threshold_pct=threshold)
    if not report.passed_gate:
        return {
            "rows_in": len(rows),
            "rows_written": 0,
            "rows_rejected": report.failing_records,
            "quality_pass_rate": report.pass_rate,
            "message": "Cost file failed the quality gate; nothing integrated",
        }

    values = [
        (
            row["cost_context"], row["cost_basis"], row["tree_size_category"] or None,
            row["planting_method"] or None, row["stock_size"] or None,
            float(row["minimum_cost"]), float(row["maximum_cost"]),
            optional_float(row["material_min_cost"]), optional_float(row["material_max_cost"]),
            optional_float(row["installation_min_cost"]), optional_float(row["installation_max_cost"]),
            optional_float(row["delivery_min_cost"]), optional_float(row["delivery_max_cost"]),
            optional_float(row["setup_min_cost"]), optional_float(row["setup_max_cost"]),
            row["currency"] or "AUD", optional_bool(row["gst_included"]),
            optional_bool(row["includes_installation"]), optional_float(row["annual_maintenance_cost"]),
            row["source_name"], row["source_reference"] or None, row["source_url"] or None,
            row["valid_from"], row["valid_to"] or None, row["last_verified_at"],
            row["confidence_level"], row["option_code"],
        )
        for row in rows
    ]
    written = write_batches(
        connection,
        """
        INSERT INTO cost_estimate (
            greening_option_id, cost_context, cost_basis, tree_size_category,
            planting_method, stock_size, minimum_cost, maximum_cost,
            material_min_cost, material_max_cost, installation_min_cost,
            installation_max_cost, delivery_min_cost, delivery_max_cost,
            setup_min_cost, setup_max_cost, currency, gst_included,
            includes_installation, annual_maintenance_cost, source_name,
            source_reference, source_url, valid_from, valid_to,
            last_verified_at, confidence_level
        )
        SELECT
            go.greening_option_id, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s
        FROM greening_option AS go
        WHERE go.option_code = %s
        """,
        values,
    )
    return {
        "rows_in": len(rows),
        "rows_written": written,
        "rows_rejected": report.failing_records,
        "quality_pass_rate": report.pass_rate,
        "message": f"{written} verified cost estimates integrated",
    }


Job = Callable[[Any, argparse.Namespace], dict[str, Any]]
JOBS: dict[str, Job] = {
    "sources": sync_sources,
    "bom": ingest_bom,
    "costs": ingest_costs,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jobs", nargs="*", choices=JOBS, default=["sources"])
    parser.add_argument("--bom-url", default=DEFAULT_BOM_URL)
    parser.add_argument("--cost-file", type=Path, default=DEFAULT_COST_FILE)
    parser.add_argument(
        "--confirm-shared",
        action="store_true",
        help="Required before writing to the team's shared Aurora database.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not db.is_local() and not args.confirm_shared:
        sys.exit(
            "Refusing to write to the shared database without --confirm-shared.\n"
            "Use a local DB_HOST or explicitly confirm the shared target."
        )

    connection = db.connect()
    try:
        for name in args.jobs:
            print(f"--- {name}")
            result = JOBS[name](connection, args)
            connection.commit()
            print(json.dumps(result, indent=2))
            if result.get("rows_in", 0) and not result.get("rows_written", 0):
                raise RuntimeError(result["message"])
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()
