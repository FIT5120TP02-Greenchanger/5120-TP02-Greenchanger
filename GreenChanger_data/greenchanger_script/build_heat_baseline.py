"""Build one deduplicated baseline Landsat heat mosaic for Melbourne."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_data.heat_baseline import BASELINE_METHOD  # noqa: E402
from greenchanger_script import db  # noqa: E402


TRANSFORMATION_NAME = "landsat_latest_daily_mosaic_v1"
SCRIPT_VERSION = "1.0"


def input_version(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT dv.*
            FROM dataset_version AS dv
            JOIN dataset_source AS ds USING(source_id)
            JOIN analysis_area AS aa USING(analysis_area_id)
            WHERE ds.source_name = 'USGS Landsat Collection 2 Surface Temperature'
              AND aa.source_area_code = '2GMEL' AND aa.source_year = 2026
              AND dv.integration_status = 'integrated'
              AND dv.publication_status = 'application_ready'
              AND dv.derivation_method LIKE 'clip_to_abs_gccsa_2GMEL_2026_v1:%'
              AND EXISTS (
                  SELECT 1 FROM heat_observation AS h
                  WHERE h.dataset_version_id = dv.dataset_version_id
              )
            ORDER BY dv.extracted_at DESC LIMIT 1
            """
        )
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError("No application-ready Melbourne Landsat version found")
    return row


def completed_output(connection, input_id):
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT output_version_id, output_record_count
               FROM transformation_run
               WHERE input_version_id = %s AND transformation_name = %s
                 AND run_status = 'completed'
               ORDER BY completed_at DESC LIMIT 1""",
            (input_id, TRANSFORMATION_NAME),
        )
        return cursor.fetchone()


def create_output_version(connection, source):
    fingerprint = hashlib.sha256(
        f"{TRANSFORMATION_NAME}|{source['dataset_version_id']}".encode("utf-8")
    ).hexdigest()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO dataset_version (
                source_id, source_updated_at, source_observed_from,
                source_observed_to, spatial_resolution_m, coverage_pass_rate,
                cloud_cover_pct, raw_row_count, checksum, quality_pass_rate,
                quality_status, integration_status, publication_status,
                parent_version_id, analysis_area_id, derivation_method
            ) VALUES (
                %s, %s, %s, %s, %s, 100.00, %s, 0, %s, NULL,
                'pending', 'running', 'internal', %s, %s, %s
            ) RETURNING dataset_version_id
            """,
            (
                source["source_id"], source["source_updated_at"],
                source["source_observed_from"], source["source_observed_to"],
                source["spatial_resolution_m"], source["cloud_cover_pct"], fingerprint,
                source["dataset_version_id"], source["analysis_area_id"],
                TRANSFORMATION_NAME,
            ),
        )
        return cursor.fetchone()["dataset_version_id"]


def quality_checks(connection, output_id) -> list[dict]:
    checks = [
        (
            "HEAT_BASELINE_REQUIRED", "completeness",
            "baseline temperature, date, geometry and source scenes are present",
            "baseline_surface_temperature_c IS NOT NULL AND observed_on IS NOT NULL "
            "AND cell_geometry IS NOT NULL AND cardinality(source_scene_ids) > 0",
        ),
        (
            "HEAT_BASELINE_TEMPERATURE_RANGE", "validity",
            "baseline surface temperature is between -50 and 80 degrees Celsius",
            "baseline_surface_temperature_c BETWEEN -50 AND 80",
        ),
        (
            "HEAT_BASELINE_GEOMETRY_VALID", "validity",
            "cell geometry is valid EPSG:7855 Polygon geometry",
            "ST_IsValid(cell_geometry) AND ST_SRID(cell_geometry) = 7855 "
            "AND GeometryType(cell_geometry) = 'POLYGON'",
        ),
        (
            "HEAT_BASELINE_CELL_UNIQUE", "uniqueness",
            "one baseline record exists per grid-cell geometry",
            "TRUE",
        ),
        (
            "HEAT_BASELINE_MELBOURNE_CENTROID", "coverage",
            "cell centroid is covered by the official Melbourne boundary",
            "EXISTS (SELECT 1 FROM analysis_area_tile t "
            "WHERE t.analysis_area_id = heat_baseline_cell.analysis_area_id "
            "AND heat_baseline_cell.cell_geometry && t.tile_geometry "
            "AND ST_Covers(t.tile_geometry, ST_Centroid(heat_baseline_cell.cell_geometry)))",
        ),
    ]
    results = []
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS count FROM heat_baseline_cell WHERE dataset_version_id = %s",
            (output_id,),
        )
        assessed = cursor.fetchone()["count"]
        for code, dimension, description, condition in checks:
            if code == "HEAT_BASELINE_CELL_UNIQUE":
                cursor.execute(
                    """SELECT COUNT(*) - COUNT(DISTINCT ST_AsEWKB(cell_geometry)) AS failed
                       FROM heat_baseline_cell WHERE dataset_version_id = %s""",
                    (output_id,),
                )
            else:
                cursor.execute(
                    f"""SELECT COUNT(*) AS failed FROM heat_baseline_cell
                         WHERE dataset_version_id = %s AND NOT ({condition})""",
                    (output_id,),
                )
            failed = cursor.fetchone()["failed"]
            results.append({
                "code": code, "dimension": dimension, "description": description,
                "assessed": assessed, "passed": assessed - failed, "failed": failed,
                "pass_rate": (assessed - failed) * 100 / assessed if assessed else 0,
            })
    return results


def record_quality(connection, output_id, checks: list[dict]) -> float:
    overall = min(check["pass_rate"] for check in checks) if checks else 0.0
    status = "passed" if overall >= 95 else "failed"
    assessed = checks[0]["assessed"] if checks else 0
    failed_records = max(check["failed"] for check in checks) if checks else 0
    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO data_quality_run (
                   dataset_version_id, completed_at, assessed_record_count,
                   passing_record_count, failing_record_count, overall_pass_rate,
                   run_status
               ) VALUES (%s, CURRENT_TIMESTAMP, %s, %s, %s, %s, %s)
               RETURNING quality_run_id""",
            (output_id, assessed, assessed - failed_records, failed_records, overall, status),
        )
        run_id = cursor.fetchone()["quality_run_id"]
        for check in checks:
            cursor.execute(
                """INSERT INTO data_quality_rule (
                       rule_code, rule_name, quality_dimension, target_table,
                       rule_description, minimum_pass_rate
                   ) VALUES (%s, %s, %s, 'heat_baseline_cell', %s, 95.00)
                   ON CONFLICT (rule_code) DO UPDATE SET active = TRUE
                   RETURNING quality_rule_id""",
                (
                    check["code"], check["code"].replace("_", " ").title(),
                    check["dimension"], check["description"],
                ),
            )
            rule_id = cursor.fetchone()["quality_rule_id"]
            cursor.execute(
                """INSERT INTO data_quality_result (
                       quality_run_id, quality_rule_id, assessed_count,
                       passed_count, failed_count, pass_rate, result_status
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    run_id, rule_id, check["assessed"], check["passed"],
                    check["failed"], check["pass_rate"],
                    "passed" if check["pass_rate"] >= 95 else "failed",
                ),
            )
    return overall


def build(connection) -> dict:
    source = input_version(connection)
    existing = completed_output(connection, source["dataset_version_id"])
    if existing:
        return {
            "status": "already_completed",
            "input_version_id": str(source["dataset_version_id"]),
            "output_version_id": str(existing["output_version_id"]),
            "cells_written": existing["output_record_count"],
        }

    output_id = create_output_version(connection, source)
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT COUNT(*) AS count FROM heat_observation
               WHERE dataset_version_id = %s""",
            (source["dataset_version_id"],),
        )
        input_count = cursor.fetchone()["count"]
        cursor.execute(
            """INSERT INTO transformation_run (
                   input_version_id, output_version_id, transformation_name,
                   script_version, input_record_count, run_status, notes
               ) VALUES (%s, %s, %s, %s, %s, 'running', %s)
               RETURNING transformation_run_id""",
            (
                source["dataset_version_id"], output_id, TRANSFORMATION_NAME,
                SCRIPT_VERSION, input_count,
                json.dumps({
                    "same_day_overlap": "arithmetic mean",
                    "across_dates": "latest valid date per cell",
                    "baseline_method": BASELINE_METHOD,
                }),
            ),
        )
        run_id = cursor.fetchone()["transformation_run_id"]
        cursor.execute(
            """
            WITH daily AS (
                SELECT observation_geometry, observed_on,
                       AVG(heat_value) AS daily_mean_c,
                       MIN(heat_value) AS daily_min_c,
                       MAX(heat_value) AS daily_max_c,
                       COUNT(*)::integer AS observation_count,
                       COUNT(DISTINCT source_scene_id)::integer AS scene_count,
                       ARRAY_AGG(DISTINCT source_scene_id ORDER BY source_scene_id) AS scene_ids,
                       AVG(cloud_cover_pct) AS mean_cloud_pct
                FROM heat_observation
                WHERE dataset_version_id = %s
                GROUP BY observation_geometry, observed_on
            ), ranked AS (
                SELECT daily.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY observation_geometry ORDER BY observed_on DESC
                       ) AS date_rank
                FROM daily
            )
            INSERT INTO heat_baseline_cell (
                dataset_version_id, analysis_area_id, cell_geometry,
                baseline_surface_temperature_c, observed_on, observation_count,
                scene_count, source_scene_ids, mean_cloud_cover_pct,
                minimum_contributing_temperature_c,
                maximum_contributing_temperature_c, same_day_spread_c,
                baseline_method, quality_status
            )
            SELECT %s, %s, observation_geometry, daily_mean_c, observed_on,
                   observation_count, scene_count, scene_ids, mean_cloud_pct,
                   daily_min_c, daily_max_c, daily_max_c - daily_min_c,
                   %s, 'passed'
            FROM ranked WHERE date_rank = 1
            """,
            (
                source["dataset_version_id"], output_id,
                source["analysis_area_id"], BASELINE_METHOD,
            ),
        )
        output_count = cursor.rowcount

    checks = quality_checks(connection, output_id)
    overall = record_quality(connection, output_id, checks)
    if overall < 95:
        raise RuntimeError(f"Baseline heat mosaic failed quality gate: {overall:.2f}%")

    with connection.cursor() as cursor:
        cursor.execute(
            """UPDATE dataset_version
               SET raw_row_count = %s, quality_pass_rate = %s,
                   quality_status = 'passed', integration_status = 'integrated',
                   publication_status = 'application_ready'
               WHERE dataset_version_id = %s""",
            (output_count, overall, output_id),
        )
        cursor.execute(
            """UPDATE transformation_run
               SET completed_at = CURRENT_TIMESTAMP, output_record_count = %s,
                   rejected_record_count = 0, run_status = 'completed'
               WHERE transformation_run_id = %s""",
            (output_count, run_id),
        )
        cursor.execute(
            """INSERT INTO integration_run (
                   dataset_version_id, target_table, completed_at, inserted_count,
                   updated_count, rejected_count, run_status, notes
               ) VALUES (%s, 'heat_baseline_cell', CURRENT_TIMESTAMP, %s, 0, 0,
                         'completed', %s)""",
            (output_id, output_count, BASELINE_METHOD),
        )
        cursor.execute(
            """INSERT INTO data_limitation (
                   dataset_version_id, limitation_type, description,
                   affected_area, analytical_impact, mitigation
               ) VALUES (%s, 'multi_date_satellite_mosaic', %s,
                         'Melbourne', %s, %s)""",
            (
                output_id,
                "The baseline uses the latest valid observation per cell and therefore combines acquisitions from 10 July and 2 August 2026.",
                "Spatial differences can partly reflect acquisition-date weather conditions, not only persistent urban form.",
                "Display observation date with each cell and replace with a same-day full-coverage mosaic when available.",
            ),
        )

    return {
        "status": "completed",
        "input_version_id": str(source["dataset_version_id"]),
        "output_version_id": str(output_id),
        "observations_in": input_count,
        "baseline_cells_written": output_count,
        "duplicates_resolved": input_count - output_count,
        "quality_pass_rate": overall,
        "method": BASELINE_METHOD,
        "quality_checks": checks,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-shared", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not db.is_local() and not args.confirm_shared:
        sys.exit("Refusing to write shared Aurora without --confirm-shared")
    connection = db.connect()
    try:
        result = build(connection)
        connection.commit()
        print(json.dumps(result, indent=2, default=str))
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()
