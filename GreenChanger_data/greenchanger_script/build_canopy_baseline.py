"""Build the versioned 500 m Greater Melbourne Vicmap canopy baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_data.canopy_baseline import (  # noqa: E402
    BASELINE_METHOD,
    TRANSFORMATION_NAME,
    source_type_for_asset_role,
)
from greenchanger_script import db  # noqa: E402

SCRIPT_VERSION = "1.0"


def input_version(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT dv.*
            FROM dataset_version AS dv
            JOIN dataset_source AS ds USING(source_id)
            JOIN analysis_area AS aa USING(analysis_area_id)
            WHERE ds.source_name = 'Vicmap Vegetation - Tree Extent'
              AND aa.source_area_code = '2GMEL' AND aa.source_year = 2026
              AND dv.integration_status = 'integrated'
              AND dv.publication_status = 'application_ready'
              AND dv.derivation_method LIKE 'clip_to_abs_gccsa_2GMEL_2026_v1:%'
              AND EXISTS (
                  SELECT 1 FROM vegetation_observation AS v
                  WHERE v.dataset_version_id = dv.dataset_version_id
              )
            ORDER BY dv.extracted_at DESC LIMIT 1
            """
        )
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError("No application-ready Greater Melbourne Tree Extent version found")
    return row


def source_asset(connection, source):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT sa.*
            FROM spatial_asset AS sa
            WHERE sa.dataset_version_id IN (%s, %s)
              AND sa.asset_role IN (
                  'canopy_api_tile_mosaic', 'canopy_source_raster',
                  'canopy_analytical_geotiff'
              )
            ORDER BY CASE WHEN sa.dataset_version_id = %s THEN 0 ELSE 1 END,
                     sa.created_at DESC
            LIMIT 1
            """,
            (source["dataset_version_id"], source["parent_version_id"], source["dataset_version_id"]),
        )
        asset = cursor.fetchone()
    if asset is None:
        raise RuntimeError("No registered Vicmap Tree Extent raster asset found")
    if asset["pixel_size_m"] is None:
        raise RuntimeError("Canopy source asset has no pixel-size provenance")
    return asset


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
                raw_row_count, checksum, quality_status, integration_status,
                publication_status, parent_version_id, analysis_area_id,
                derivation_method
            ) VALUES (
                %s, %s, %s, %s, 500, 100.00, 0, %s, 'pending', 'running',
                'internal', %s, %s, %s
            ) RETURNING dataset_version_id
            """,
            (
                source["source_id"], source["source_updated_at"],
                source["source_observed_from"], source["source_observed_to"],
                fingerprint, source["dataset_version_id"],
                source["analysis_area_id"], TRANSFORMATION_NAME,
            ),
        )
        return cursor.fetchone()["dataset_version_id"]


def cell_quality_checks(connection, output_id) -> list[dict]:
    checks = [
        ("CANOPY_BASELINE_REQUIRED", "completeness",
         "canopy percentage, date, geometry and source provenance are present",
         "canopy_percentage IS NOT NULL AND observed_on IS NOT NULL "
         "AND cell_geometry IS NOT NULL AND source_pixel_size_m IS NOT NULL"),
        ("CANOPY_BASELINE_PERCENTAGE_RANGE", "validity",
         "canopy percentage is between zero and 100", "canopy_percentage BETWEEN 0 AND 100"),
        ("CANOPY_BASELINE_GEOMETRY_VALID", "validity",
         "cell geometry is valid EPSG:7855 Polygon geometry",
         "ST_IsValid(cell_geometry) AND ST_SRID(cell_geometry) = 7855 "
         "AND GeometryType(cell_geometry) = 'POLYGON'"),
        ("CANOPY_BASELINE_CELL_UNIQUE", "uniqueness",
         "one canopy baseline record exists per grid-cell geometry", "TRUE"),
        ("CANOPY_BASELINE_MELBOURNE_CENTROID", "coverage",
         "cell centroid is covered by the official Greater Melbourne boundary",
         "EXISTS (SELECT 1 FROM analysis_area_tile t "
         "WHERE t.analysis_area_id = canopy_baseline_cell.analysis_area_id "
         "AND canopy_baseline_cell.cell_geometry && t.tile_geometry "
         "AND ST_Covers(t.tile_geometry, ST_Centroid(canopy_baseline_cell.cell_geometry)))"),
    ]
    results = []
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS count FROM canopy_baseline_cell WHERE dataset_version_id = %s",
            (output_id,),
        )
        assessed = cursor.fetchone()["count"]
        for code, dimension, description, condition in checks:
            if code == "CANOPY_BASELINE_CELL_UNIQUE":
                cursor.execute(
                    """SELECT COUNT(*) - COUNT(DISTINCT ST_AsEWKB(cell_geometry)) AS failed
                       FROM canopy_baseline_cell WHERE dataset_version_id = %s""",
                    (output_id,),
                )
            else:
                cursor.execute(
                    f"""SELECT COUNT(*) AS failed FROM canopy_baseline_cell
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


def heat_alignment_check(connection, output_id) -> dict:
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS count FROM latest_greater_melbourne_heat_baseline")
        assessed = cursor.fetchone()["count"]
        cursor.execute(
            """SELECT COUNT(*) AS count
               FROM latest_greater_melbourne_heat_baseline AS h
               WHERE EXISTS (
                   SELECT 1 FROM canopy_baseline_cell AS c
                   WHERE c.dataset_version_id = %s
                     AND ST_Equals(c.cell_geometry, h.cell_geometry)
               )""",
            (output_id,),
        )
        passed = cursor.fetchone()["count"]
    return {
        "code": "CANOPY_BASELINE_HEAT_GRID_ALIGNMENT", "dimension": "consistency",
        "description": "every current heat-baseline cell has an exactly matching canopy cell",
        "assessed": assessed, "passed": passed, "failed": assessed - passed,
        "pass_rate": passed * 100 / assessed if assessed else 0,
    }


def record_quality(connection, output_id, checks: list[dict]) -> float:
    overall = min(check["pass_rate"] for check in checks) if checks else 0.0
    status = "passed" if overall >= 95 else "failed"
    assessed = max(check["assessed"] for check in checks) if checks else 0
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
                   ) VALUES (%s, %s, %s, 'canopy_baseline_cell', %s, 95.00)
                   ON CONFLICT (rule_code) DO UPDATE SET active = TRUE
                   RETURNING quality_rule_id""",
                (check["code"], check["code"].replace("_", " ").title(),
                 check["dimension"], check["description"]),
            )
            rule_id = cursor.fetchone()["quality_rule_id"]
            cursor.execute(
                """INSERT INTO data_quality_result (
                       quality_run_id, quality_rule_id, assessed_count,
                       passed_count, failed_count, pass_rate, result_status
                   ) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (run_id, rule_id, check["assessed"], check["passed"], check["failed"],
                 check["pass_rate"], "passed" if check["pass_rate"] >= 95 else "failed"),
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

    asset = source_asset(connection, source)
    source_type, source_is_proxy = source_type_for_asset_role(asset["asset_role"])
    output_id = create_output_version(connection, source)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS count FROM vegetation_observation WHERE dataset_version_id = %s",
            (source["dataset_version_id"],),
        )
        input_count = cursor.fetchone()["count"]
        cursor.execute(
            """INSERT INTO transformation_run (
                   input_version_id, output_version_id, transformation_name,
                   script_version, input_record_count, run_status, notes
               ) VALUES (%s, %s, %s, %s, %s, 'running', %s)
               RETURNING transformation_run_id""",
            (source["dataset_version_id"], output_id, TRANSFORMATION_NAME,
             SCRIPT_VERSION, input_count, json.dumps({
                 "baseline_method": BASELINE_METHOD,
                 "source_type": source_type,
                 "source_asset_role": asset["asset_role"],
                 "coverage_confidence_definition": "complete source-raster coverage, not classification accuracy",
             })),
        )
        run_id = cursor.fetchone()["transformation_run_id"]
        cursor.execute(
            """
            INSERT INTO canopy_baseline_cell (
                dataset_version_id, analysis_area_id, cell_geometry,
                canopy_percentage, observed_on, source_type,
                source_pixel_size_m, grid_size_m, source_is_proxy,
                coverage_confidence_pct, baseline_method, quality_status
            )
            SELECT %s, %s, observation_geometry::geometry(Polygon, 7855),
                   vegetation_percentage, observed_on, %s, %s,
                   spatial_resolution_m, %s, confidence_score, %s, 'passed'
            FROM vegetation_observation
            WHERE dataset_version_id = %s
              AND vegetation_type = 'tree_canopy'
            """,
            (output_id, source["analysis_area_id"], source_type, asset["pixel_size_m"],
             source_is_proxy, BASELINE_METHOD, source["dataset_version_id"]),
        )
        output_count = cursor.rowcount

    checks = cell_quality_checks(connection, output_id)
    checks.append(heat_alignment_check(connection, output_id))
    overall = record_quality(connection, output_id, checks)
    if overall < 95:
        raise RuntimeError(f"Canopy baseline failed quality gate: {overall:.2f}%")

    with connection.cursor() as cursor:
        cursor.execute(
            """UPDATE dataset_version
               SET raw_row_count = %s, quality_pass_rate = %s,
                   quality_status = 'passed_with_limitations',
                   integration_status = 'integrated',
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
               ) VALUES (%s, 'canopy_baseline_cell', CURRENT_TIMESTAMP, %s, 0, 0,
                         'completed', %s)""",
            (output_id, output_count, BASELINE_METHOD),
        )
        if source_is_proxy:
            cursor.execute(
                """INSERT INTO data_limitation (
                       dataset_version_id, limitation_type, description,
                       affected_area, analytical_impact, mitigation
                   ) VALUES (%s, 'rendered_tile_proxy', %s, 'Greater Melbourne', %s, %s)""",
                (output_id,
                 "The current baseline was reconstructed from official rendered API tiles at approximately 19.1 m, not the original approximately 20 cm analytical GeoTIFF.",
                 "Suitable for 500 m area summaries, but not individual-property or tree-crown decisions.",
                 "Replace the registered source asset and rebuild after the official analytical GeoTIFF is obtained through the DataVic order workflow."),
            )
        cursor.execute(
            """INSERT INTO data_limitation (
                   dataset_version_id, limitation_type, description,
                   affected_area, analytical_impact, mitigation
               ) VALUES (%s, 'multi_year_imagery_period', %s, 'Greater Melbourne', %s, %s)""",
            (output_id,
             "Vicmap Tree Extent source imagery spans 7 December 2013 to 2 November 2020; observed_on stores the published period end, not a uniform capture date.",
             "Canopy comparisons can include temporal differences between locations.",
             "Show the source period in outputs and avoid describing the baseline as a single-date 2020 survey."),
        )

    return {
        "status": "completed",
        "input_version_id": str(source["dataset_version_id"]),
        "output_version_id": str(output_id),
        "observations_in": input_count,
        "baseline_cells_written": output_count,
        "quality_pass_rate": overall,
        "source_type": source_type,
        "source_pixel_size_m": float(asset["pixel_size_m"]),
        "method": BASELINE_METHOD,
        "quality_checks": checks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-shared", action="store_true")
    args = parser.parse_args()
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
