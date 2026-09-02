"""Build application-ready canopy summaries clipped to Melbourne parcels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_data.property_canopy import (  # noqa: E402
    REQUIRED_ASSET_ROLE,
    calculate_property_canopy,
    validate_property_canopy_source,
)
from greenchanger_data.sources import sha256_file  # noqa: E402
from greenchanger_script import db  # noqa: E402


METHOD = "property_canopy_raster_clip_v1"
SCRIPT_VERSION = "1.0"


def analytical_source(connection) -> tuple[dict, dict]:
    """Find the newest registered analytical Tree Extent asset for Melbourne."""

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT dv.*, sa.spatial_asset_id, sa.asset_role, sa.local_path,
                   sa.pixel_size_m AS asset_pixel_size_m, sa.checksum AS asset_checksum
            FROM dataset_version AS dv
            JOIN dataset_source AS ds USING (source_id)
            JOIN analysis_area AS aa USING (analysis_area_id)
            JOIN LATERAL (
                SELECT asset.*
                FROM spatial_asset AS asset
                WHERE asset.dataset_version_id IN (
                    dv.dataset_version_id, dv.parent_version_id
                )
                  AND asset.asset_role = %s
                ORDER BY
                    CASE WHEN asset.dataset_version_id = dv.dataset_version_id
                         THEN 0 ELSE 1 END,
                    asset.created_at DESC
                LIMIT 1
            ) AS sa ON TRUE
            WHERE ds.source_name = 'Vicmap Vegetation - Tree Extent'
              AND aa.source_area_code = '2GMEL' AND aa.source_year = 2026
              AND dv.integration_status = 'integrated'
              AND dv.publication_status = 'application_ready'
            ORDER BY dv.extracted_at DESC
            LIMIT 1
            """,
            (REQUIRED_ASSET_ROLE,),
        )
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError(
            "No application-ready canopy_analytical_geotiff is registered. "
            "The 19.1 m rendered API proxy cannot be used for property canopy."
        )
    version_keys = {
        "dataset_version_id", "source_id", "analysis_area_id", "source_updated_at",
        "source_observed_from", "source_observed_to", "checksum",
    }
    return ({key: row[key] for key in version_keys}, row)


def property_version(connection) -> dict:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT dv.*
            FROM dataset_version AS dv
            JOIN dataset_source AS ds USING (source_id)
            JOIN analysis_area AS aa USING (analysis_area_id)
            WHERE ds.source_name = 'Vicmap Property'
              AND aa.source_area_code = '2GMEL' AND aa.source_year = 2026
              AND dv.integration_status = 'integrated'
              AND dv.publication_status = 'application_ready'
              AND dv.derivation_method LIKE 'clip_to_abs_gccsa_2GMEL_2026_v1:%'
            ORDER BY dv.extracted_at DESC LIMIT 1
            """
        )
        row = cursor.fetchone()
    if row is None:
        raise RuntimeError("No application-ready Melbourne Vicmap Property version found")
    return row


def create_output(connection, source: dict, pixel_size_m: float) -> tuple[str, str]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO dataset_version (
                source_id, source_updated_at, source_observed_from, source_observed_to,
                spatial_resolution_m, checksum, quality_status, integration_status,
                publication_status, parent_version_id, analysis_area_id, derivation_method
            ) VALUES (%s, %s, %s, %s, %s, %s, 'pending', 'running', 'internal', %s, %s, %s)
            RETURNING dataset_version_id
            """,
            (
                source["source_id"], source["source_updated_at"],
                source["source_observed_from"], source["source_observed_to"],
                pixel_size_m, source["checksum"], source["dataset_version_id"],
                source["analysis_area_id"], METHOD,
            ),
        )
        output_id = cursor.fetchone()["dataset_version_id"]
        cursor.execute(
            """
            INSERT INTO transformation_run (
                input_version_id, output_version_id, transformation_name,
                script_version, run_status
            ) VALUES (%s, %s, %s, %s, 'running')
            RETURNING transformation_run_id
            """,
            (source["dataset_version_id"], output_id, METHOD, SCRIPT_VERSION),
        )
        run_id = cursor.fetchone()["transformation_run_id"]
    return output_id, run_id


def record_quality(connection, output_id: str, assessed: int, passed: int) -> float:
    pass_rate = round(passed * 100.0 / assessed, 2) if assessed else 0.0
    status = "passed" if pass_rate >= 95 else "failed"
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO data_quality_rule (
                rule_code, rule_name, quality_dimension, target_table,
                rule_description, failure_severity, minimum_pass_rate
            ) VALUES (
                'PROPERTY_CANOPY_COMPLETE_VALID', 'Property canopy complete and valid',
                'completeness', 'property_canopy_summary',
                'Parcel has at least 95 percent raster coverage and a 0-100 canopy percentage.',
                'high', 95
            ) ON CONFLICT (rule_code) DO UPDATE SET rule_description = EXCLUDED.rule_description
            RETURNING quality_rule_id
            """
        )
        rule_id = cursor.fetchone()["quality_rule_id"]
        cursor.execute(
            """
            INSERT INTO data_quality_run (
                dataset_version_id, completed_at, assessed_record_count,
                passing_record_count, failing_record_count, overall_pass_rate, run_status
            ) VALUES (%s, CURRENT_TIMESTAMP, %s, %s, %s, %s, %s)
            RETURNING quality_run_id
            """,
            (output_id, assessed, passed, assessed - passed, pass_rate, status),
        )
        quality_run_id = cursor.fetchone()["quality_run_id"]
        cursor.execute(
            """
            INSERT INTO data_quality_result (
                quality_run_id, quality_rule_id, assessed_count, passed_count,
                failed_count, pass_rate, result_status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (quality_run_id, rule_id, assessed, passed, assessed - passed, pass_rate, status),
        )
    return pass_rate


def build(connection, *, raster_override: Path | None, tree_value: float, batch_size: int) -> dict:
    import rasterio

    source_version, asset = analytical_source(connection)
    properties = property_version(connection)
    raster_path = raster_override or (Path(asset["local_path"]) if asset["local_path"] else None)
    if raster_path is None or not raster_path.exists():
        raise FileNotFoundError(
            "The registered analytical GeoTIFF is not available locally; pass --canopy-file"
        )
    if asset["asset_checksum"] and sha256_file(raster_path) != asset["asset_checksum"]:
        raise ValueError(
            "The local analytical GeoTIFF checksum does not match its registered asset"
        )
    if source_version["source_observed_to"] is None:
        raise ValueError("Analytical canopy version has no recorded observation date")

    with rasterio.open(raster_path) as raster:
        validate_property_canopy_source(raster, asset_role=asset["asset_role"])
        source_epsg = raster.crs.to_epsg()
        if source_epsg is None:
            raise ValueError("Analytical raster CRS must have an EPSG code")
        pixel_size_m = max(abs(raster.transform.a), abs(raster.transform.e))
        output_id, run_id = create_output(connection, source_version, pixel_size_m)

        assessed = passed = written = 0
        read_cursor = connection.cursor(name="property_canopy_parcels")
        read_cursor.execute(
            """
            SELECT parcel_id, COALESCE(parcel_area_m2, ST_Area(parcel_geometry)) AS parcel_area_m2,
                   ST_AsGeoJSON(ST_Transform(parcel_geometry, %s), 9) AS geometry_geojson
            FROM parcel
            WHERE dataset_version_id = %s
            ORDER BY parcel_id
            """,
            (source_epsg, properties["dataset_version_id"]),
        )
        try:
            while True:
                parcels = read_cursor.fetchmany(batch_size)
                if not parcels:
                    break
                values = []
                for parcel in parcels:
                    result = calculate_property_canopy(
                        raster,
                        json.loads(parcel["geometry_geojson"]),
                        parcel_area_m2=float(parcel["parcel_area_m2"]),
                        tree_value=tree_value,
                    )
                    assessed += 1
                    passed += result.quality_status == "passed"
                    values.append((
                        output_id, source_version["dataset_version_id"], parcel["parcel_id"],
                        source_version["source_observed_to"],
                        result.canopy_area_m2, result.parcel_area_m2,
                        result.raster_covered_area_m2, result.canopy_percentage,
                        result.coverage_percentage, pixel_size_m, METHOD,
                        result.quality_status, result.failure_reason,
                    ))
                with connection.cursor() as write_cursor:
                    write_cursor.executemany(
                        """
                        INSERT INTO property_canopy_summary (
                            dataset_version_id, source_canopy_version_id, parcel_id,
                            observed_on, canopy_area_m2, parcel_area_m2,
                            raster_covered_area_m2, canopy_percentage,
                            coverage_percentage, source_pixel_size_m,
                            calculation_method, quality_status, failure_reason
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        values,
                    )
                written += len(values)
        finally:
            read_cursor.close()

    pass_rate = record_quality(connection, output_id, assessed, passed)
    ready = pass_rate >= 95 and assessed > 0
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE dataset_version
            SET raw_row_count = %s, quality_pass_rate = %s,
                coverage_pass_rate = %s, quality_status = %s,
                integration_status = %s, publication_status = %s
            WHERE dataset_version_id = %s
            """,
            (
                assessed, pass_rate, pass_rate,
                "passed" if ready else "failed",
                "integrated" if ready else "failed",
                "application_ready" if ready else "internal", output_id,
            ),
        )
        cursor.execute(
            """
            UPDATE transformation_run
            SET completed_at = CURRENT_TIMESTAMP, input_record_count = %s,
                output_record_count = %s, rejected_record_count = %s,
                run_status = %s
            WHERE transformation_run_id = %s
            """,
            (assessed, passed, assessed - passed, "completed" if ready else "failed", run_id),
        )
    return {
        "dataset_version_id": str(output_id), "rows_assessed": assessed,
        "rows_written": written, "rows_passed": passed,
        "quality_pass_rate": pass_rate, "application_ready": ready,
        "source_pixel_size_m": pixel_size_m,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canopy-file", type=Path)
    parser.add_argument("--tree-value", type=float, required=True)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--confirm-shared", action="store_true")
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be at least 1")
    if not db.is_local() and not args.confirm_shared:
        sys.exit("Refusing to write to shared Aurora without --confirm-shared")
    connection = db.connect()
    try:
        result = build(
            connection, raster_override=args.canopy_file,
            tree_value=args.tree_value, batch_size=args.batch_size,
        )
        connection.commit()
        print(json.dumps(result, indent=2))
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()
