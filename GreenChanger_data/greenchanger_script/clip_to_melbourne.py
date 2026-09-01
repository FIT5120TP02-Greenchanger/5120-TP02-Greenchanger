"""Create audited Melbourne-only versions of spatial datasets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_script import db  # noqa: E402


TRANSFORMATION_NAME = "clip_to_abs_gccsa_2GMEL_2026_v1"
SCRIPT_VERSION = "1.0"

TARGETS: dict[str, dict[str, str]] = {
    "address": {
        "source_name": "Vicmap Address",
        "table": "address",
        "membership": "point_inside",
        "insert": """
            INSERT INTO address (
                dataset_version_id, source_address_id, source_property_id,
                full_address, locality_name, postcode, lga_code, is_primary,
                address_class, address_location
            )
            SELECT %(output_version)s, a.source_address_id, a.source_property_id,
                   a.full_address, a.locality_name, a.postcode, a.lga_code,
                   a.is_primary, a.address_class, a.address_location
            FROM address AS a
            WHERE a.dataset_version_id = %(input_version)s
              AND EXISTS (
                  SELECT 1 FROM analysis_area_tile AS t
                  WHERE t.analysis_area_id = %(analysis_area)s
                    AND a.address_location && t.tile_geometry
                    AND ST_Covers(t.tile_geometry, a.address_location)
              )
        """,
    },
    "property": {
        "source_name": "Vicmap Property",
        "table": "parcel",
        "membership": "polygon_intersects",
        "insert": """
            INSERT INTO parcel (
                dataset_version_id, source_parcel_id, property_number,
                property_type, property_status, lga_code, parcel_geometry,
                parcel_area_m2
            )
            SELECT %(output_version)s, p.source_parcel_id, p.property_number,
                   p.property_type, p.property_status, p.lga_code,
                   p.parcel_geometry, p.parcel_area_m2
            FROM parcel AS p
            WHERE p.dataset_version_id = %(input_version)s
              AND EXISTS (
                  SELECT 1 FROM analysis_area_tile AS t
                  WHERE t.analysis_area_id = %(analysis_area)s
                    AND p.parcel_geometry && t.tile_geometry
                    AND ST_Intersects(t.tile_geometry, p.parcel_geometry)
              )
        """,
    },
    "heat": {
        "source_name": "USGS Landsat Collection 2 Surface Temperature",
        "table": "heat_observation",
        "membership": "cell_centroid_inside",
        "insert": """
            INSERT INTO heat_observation (
                dataset_version_id, site_id, observation_geometry, observed_on,
                observed_at, heat_value, measurement_type, unit,
                source_scene_id, cloud_cover_pct, quality_status
            )
            SELECT %(output_version)s, h.site_id, h.observation_geometry,
                   h.observed_on, h.observed_at, h.heat_value,
                   h.measurement_type, h.unit, h.source_scene_id,
                   h.cloud_cover_pct, h.quality_status
            FROM heat_observation AS h
            WHERE h.dataset_version_id = %(input_version)s
              AND EXISTS (
                  SELECT 1 FROM analysis_area_tile AS t
                  WHERE t.analysis_area_id = %(analysis_area)s
                    AND h.observation_geometry && t.tile_geometry
                    AND ST_Covers(t.tile_geometry, ST_Centroid(h.observation_geometry))
              )
        """,
    },
    "canopy": {
        "source_name": "Vicmap Vegetation - Tree Extent",
        "table": "vegetation_observation",
        "membership": "cell_centroid_inside",
        "insert": """
            INSERT INTO vegetation_observation (
                dataset_version_id, site_id, observation_geometry, observed_on,
                vegetation_type, vegetation_percentage, vegetation_index_type,
                vegetation_index_value, calculation_method,
                spatial_resolution_m, confidence_score, quality_status
            )
            SELECT %(output_version)s, v.site_id, v.observation_geometry,
                   v.observed_on, v.vegetation_type, v.vegetation_percentage,
                   v.vegetation_index_type, v.vegetation_index_value,
                   v.calculation_method, v.spatial_resolution_m,
                   v.confidence_score, v.quality_status
            FROM vegetation_observation AS v
            WHERE v.dataset_version_id = %(input_version)s
              AND EXISTS (
                  SELECT 1 FROM analysis_area_tile AS t
                  WHERE t.analysis_area_id = %(analysis_area)s
                    AND v.observation_geometry && t.tile_geometry
                    AND ST_Covers(t.tile_geometry, ST_Centroid(v.observation_geometry))
              )
        """,
    },
}


def transformation_checksum(input_version: str, analysis_area: str, target: str) -> str:
    value = f"{TRANSFORMATION_NAME}|{input_version}|{analysis_area}|{target}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def analysis_area(connection) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT analysis_area_id, area_name, source_area_code, source_year
               FROM analysis_area
               WHERE source_area_code = '2GMEL' AND source_year = 2026"""
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Official Melbourne boundary 2GMEL is not loaded")
        cursor.execute(
            "SELECT COUNT(*) AS count FROM analysis_area_tile WHERE analysis_area_id = %s",
            (row["analysis_area_id"],),
        )
        tile_count = cursor.fetchone()["count"]
        if not tile_count:
            raise RuntimeError("Melbourne boundary tiles are missing; apply migration 007")
        row["tile_count"] = tile_count
        return row


def latest_input_version(connection, target: str):
    specification = TARGETS[target]
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT dv.*
            FROM dataset_version AS dv
            JOIN dataset_source AS ds USING (source_id)
            WHERE ds.source_name = %s
              AND dv.integration_status = 'integrated'
              AND dv.parent_version_id IS NULL
              AND EXISTS (
                  SELECT 1 FROM {specification['table']} AS records
                  WHERE records.dataset_version_id = dv.dataset_version_id
              )
            ORDER BY dv.extracted_at DESC
            LIMIT 1
            """,
            (specification["source_name"],),
        )
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError(f"No integrated source version found for {target}")
    return row


def completed_output(connection, input_version):
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT output_version_id, output_record_count
               FROM transformation_run
               WHERE input_version_id = %s AND transformation_name = %s
                 AND run_status = 'completed'
               ORDER BY completed_at DESC LIMIT 1""",
            (input_version, TRANSFORMATION_NAME),
        )
        return cursor.fetchone()


def create_output_version(connection, source: dict[str, Any], area_id, target: str):
    checksum = transformation_checksum(str(source["dataset_version_id"]), str(area_id), target)
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
                %s, %s, %s, %s, %s, 100.00, %s, 0, %s, %s,
                'pending', 'running', 'internal', %s, %s, %s
            ) RETURNING dataset_version_id
            """,
            (
                source["source_id"], source["source_updated_at"],
                source["source_observed_from"], source["source_observed_to"],
                source["spatial_resolution_m"], source["cloud_cover_pct"],
                checksum, source["quality_pass_rate"], source["dataset_version_id"],
                area_id, f"{TRANSFORMATION_NAME}:{TARGETS[target]['membership']}",
            ),
        )
        return cursor.fetchone()["dataset_version_id"]


def record_quality(connection, version_id, target: str, record_count: int) -> None:
    rule_code = f"GREATER_MELBOURNE_MEMBERSHIP_{target.upper()}"
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO data_quality_rule (
                rule_code, rule_name, quality_dimension, target_table,
                rule_description, minimum_pass_rate
            ) VALUES (%s, %s, 'coverage', %s, %s, 100.00)
            ON CONFLICT (rule_code) DO UPDATE SET active = TRUE
            RETURNING quality_rule_id
            """,
            (
                rule_code, f"Melbourne membership: {target}",
                TARGETS[target]["table"],
                f"Every output record passes {TARGETS[target]['membership']} against ABS GCCSA 2GMEL (2026).",
            ),
        )
        rule_id = cursor.fetchone()["quality_rule_id"]
        cursor.execute(
            """
            INSERT INTO data_quality_run (
                dataset_version_id, completed_at, assessed_record_count,
                passing_record_count, failing_record_count, overall_pass_rate,
                run_status
            ) VALUES (%s, CURRENT_TIMESTAMP, %s, %s, 0, 100.00, 'passed')
            RETURNING quality_run_id
            """,
            (version_id, record_count, record_count),
        )
        run_id = cursor.fetchone()["quality_run_id"]
        cursor.execute(
            """
            INSERT INTO data_quality_result (
                quality_run_id, quality_rule_id, assessed_count, passed_count,
                failed_count, pass_rate, sample_failure, result_status
            ) VALUES (%s, %s, %s, %s, 0, 100.00, '{}'::jsonb, 'passed')
            """,
            (run_id, rule_id, record_count, record_count),
        )


def clip_target(connection, target: str, area: dict[str, Any]) -> dict[str, Any]:
    source = latest_input_version(connection, target)
    input_id = source["dataset_version_id"]
    existing = completed_output(connection, input_id)
    if existing:
        return {
            "target": target,
            "status": "already_completed",
            "input_version_id": str(input_id),
            "output_version_id": str(existing["output_version_id"]),
            "rows_written": existing["output_record_count"],
        }

    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT COUNT(*) AS count FROM {TARGETS[target]['table']} WHERE dataset_version_id = %s",
            (input_id,),
        )
        input_count = cursor.fetchone()["count"]
        output_id = create_output_version(connection, source, area["analysis_area_id"], target)
        cursor.execute(
            """
            INSERT INTO transformation_run (
                input_version_id, output_version_id, transformation_name,
                script_version, input_record_count, run_status, notes
            ) VALUES (%s, %s, %s, %s, %s, 'running', %s)
            RETURNING transformation_run_id
            """,
            (
                input_id, output_id, TRANSFORMATION_NAME, SCRIPT_VERSION, input_count,
                json.dumps({
                    "analysis_area_id": str(area["analysis_area_id"]),
                    "source_area_code": "2GMEL", "source_year": 2026,
                    "membership_method": TARGETS[target]["membership"],
                }),
            ),
        )
        run_id = cursor.fetchone()["transformation_run_id"]
        cursor.execute(
            TARGETS[target]["insert"],
            {
                "output_version": output_id,
                "input_version": input_id,
                "analysis_area": area["analysis_area_id"],
            },
        )
        output_count = cursor.rowcount
        excluded_count = input_count - output_count
        record_quality(connection, output_id, target, output_count)
        cursor.execute(
            """
            UPDATE dataset_version
            SET raw_row_count = %s, quality_status = 'passed',
                integration_status = 'integrated',
                publication_status = 'application_ready'
            WHERE dataset_version_id = %s
            """,
            (output_count, output_id),
        )
        cursor.execute(
            """
            UPDATE transformation_run
            SET completed_at = CURRENT_TIMESTAMP, output_record_count = %s,
                rejected_record_count = %s, run_status = 'completed'
            WHERE transformation_run_id = %s
            """,
            (output_count, excluded_count, run_id),
        )
        cursor.execute(
            """
            INSERT INTO integration_run (
                dataset_version_id, target_table, completed_at, inserted_count,
                updated_count, rejected_count, run_status, notes
            ) VALUES (%s, %s, CURRENT_TIMESTAMP, %s, 0, %s, 'completed', %s)
            """,
            (
                output_id, TARGETS[target]["table"], output_count, excluded_count,
                "Melbourne-only derived version; excluded records remain in the parent version.",
            ),
        )
    return {
        "target": target,
        "status": "completed",
        "input_version_id": str(input_id),
        "output_version_id": str(output_id),
        "rows_in": input_count,
        "rows_written": output_count,
        "rows_outside_boundary": excluded_count,
        "retention_pct": round(output_count * 100 / input_count, 4) if input_count else 0,
        "quality_pass_rate": 100.0,
        "membership_method": TARGETS[target]["membership"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "targets", nargs="*", choices=TARGETS,
        help="Datasets to filter; defaults to address property heat canopy.",
    )
    parser.add_argument("--confirm-shared", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not db.is_local() and not args.confirm_shared:
        sys.exit("Refusing to write shared Aurora without --confirm-shared")
    connection = db.connect()
    try:
        area = analysis_area(connection)
        print(json.dumps({
            "analysis_area_id": str(area["analysis_area_id"]),
            "area_name": area["area_name"], "tile_count": area["tile_count"],
        }, indent=2))
        for target in (args.targets or list(TARGETS)):
            print(f"--- {target}", flush=True)
            try:
                result = clip_target(connection, target, area)
                connection.commit()
                print(json.dumps(result, indent=2), flush=True)
            except Exception:
                connection.rollback()
                raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()
