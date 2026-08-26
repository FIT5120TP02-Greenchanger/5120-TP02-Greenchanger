"""Unified GreenChanger ingestion jobs for PostgreSQL/PostGIS.

Examples:
    python greenchanger_script/ingestion.py sources
    python greenchanger_script/ingestion.py bom
    python greenchanger_script/ingestion.py costs --cost-file data/reference/cost_estimates.csv
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_script import db  # noqa: E402
from greenchanger_data.bom import (
    DEFAULT_BOM_URL,
    extract_rows,
    fetch_observations,
    normalise_rows,
    save_raw,
)
from greenchanger_data.boundary import (
    ABS_GCCSA_LAYER_URL,
    ASGS_EFFECTIVE_DATE,
    fetch_greater_melbourne,
    normalise_greater_melbourne,
    save_raw as save_boundary_raw,
)
from greenchanger_data.canopy import aggregate_canopy, profile_canopy_raster
from greenchanger_data.landsat import (
    aggregate_surface_temperature,
    asset_metadata,
    choose_scenes,
    download_asset,
    planetary_computer_token,
    search_surface_temperature,
    signed_asset_href,
)
from greenchanger_data.quality import QualityReport, validate_record_stream, validate_records
from greenchanger_data.sources import load_source_registry, sha256_file
from greenchanger_data.vicmap_features import extract_to_jsonl, read_jsonl


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


def write_record_stream(connection, sql: str, rows) -> int:
    """Write an iterator in bounded batches without retaining a full extract."""

    batch: list[Sequence[Any]] = []
    written = 0
    with connection.cursor() as cursor:
        for row in rows:
            batch.append(row)
            if len(batch) >= BATCH_SIZE:
                cursor.executemany(sql, batch)
                written += len(batch)
                batch.clear()
        if batch:
            cursor.executemany(sql, batch)
            written += len(batch)
    return written


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
            "Source not registered. Run "
            "`python greenchanger_script/ingestion.py sources` first."
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
    spatial_resolution_m=None,
    cloud_cover_pct=None,
):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO dataset_version (
                source_id, source_observed_from, source_observed_to,
                raw_row_count, checksum, spatial_resolution_m, cloud_cover_pct
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING dataset_version_id
            """,
            (
                registered_source_id,
                observed_from,
                observed_to,
                row_count,
                checksum,
                spatial_resolution_m,
                cloud_cover_pct,
            ),
        )
        return cursor.fetchone()["dataset_version_id"]


def register_spatial_assets(connection, dataset_version_id, assets: list[dict[str, Any]]) -> None:
    values = [
        (
            dataset_version_id, asset["asset_role"], asset.get("source_scene_id", ""),
            asset.get("source_href"), asset.get("local_path"), asset.get("media_type"),
            asset.get("source_crs"), asset.get("target_srid", TARGET_SRID),
            asset.get("pixel_size_m"), asset.get("checksum"), asset.get("acquired_at"),
            json.dumps(asset.get("metadata", {})),
        )
        for asset in assets
    ]
    write_batches(
        connection,
        """
        INSERT INTO spatial_asset (
            dataset_version_id, asset_role, source_scene_id, source_href,
            local_path, media_type, source_crs, target_srid, pixel_size_m,
            checksum, acquired_at, metadata
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (dataset_version_id, asset_role, source_scene_id) DO UPDATE SET
            source_href = EXCLUDED.source_href,
            local_path = EXCLUDED.local_path,
            media_type = EXCLUDED.media_type,
            source_crs = EXCLUDED.source_crs,
            target_srid = EXCLUDED.target_srid,
            pixel_size_m = EXCLUDED.pixel_size_m,
            checksum = EXCLUDED.checksum,
            acquired_at = EXCLUDED.acquired_at,
            metadata = EXCLUDED.metadata
        """,
        values,
    )


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


def ingest_boundary(connection, _args: argparse.Namespace) -> dict[str, Any]:
    """Version and integrate the official ABS 2026 Greater Melbourne GCCSA."""

    document = fetch_greater_melbourne()
    row = normalise_greater_melbourne(document)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = ROOT / "data" / "raw" / "abs" / f"greater_melbourne_gccsa_2026_{stamp}.geojson"
    save_boundary_raw(document, raw_path)

    registered_source_id = source_id(
        connection,
        "ABS ASGS Edition 4 Greater Capital City Statistical Areas 2026",
        "Australian Bureau of Statistics",
    )
    version_id = create_dataset_version(
        connection,
        registered_source_id=registered_source_id,
        row_count=1,
        checksum=sha256_file(raw_path),
        observed_from=ASGS_EFFECTIVE_DATE,
        observed_to=ASGS_EFFECTIVE_DATE,
    )
    register_spatial_assets(
        connection,
        version_id,
        [{
            "asset_role": "analysis_boundary",
            "source_scene_id": "ASGS2026_GCCSA_2GMEL",
            "source_href": f"{ABS_GCCSA_LAYER_URL}/query",
            "local_path": str(raw_path.resolve()),
            "media_type": "application/geo+json",
            "source_crs": "EPSG:4326 (GDA2020-compatible API output)",
            "checksum": sha256_file(raw_path),
            "acquired_at": datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "gccsa_code": row["source_area_code"],
                "gccsa_name": row["area_name"],
                "asgs_edition": 4,
                "asgs_year": 2026,
                "effective_date": ASGS_EFFECTIVE_DATE,
            },
        }],
    )

    rules, threshold = quality_configuration("analysis_area")
    report = validate_records("analysis_area", [row], rules, threshold_pct=threshold)
    record_quality_run(connection, version_id, report)
    if not report.passed_gate:
        connection.commit()
        return {
            "rows_in": 1,
            "rows_written": 0,
            "rows_rejected": report.failing_records,
            "quality_pass_rate": report.pass_rate,
            "dataset_version_id": str(version_id),
            "message": "Greater Melbourne boundary failed the quality gate; nothing integrated",
        }

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO analysis_area (
                dataset_version_id, area_name, area_type, boundary_geometry,
                area_m2, support_status, supported_from, source_area_code,
                source_year, source_area_sqkm, source_metadata
            ) VALUES (
                %s, %s, %s,
                ST_Multi(ST_Transform(ST_GeomFromText(%s::text, %s::integer), {TARGET_SRID})),
                %s, 'supported', %s, %s, %s, %s, %s::jsonb
            )
            ON CONFLICT (area_name, area_type) DO UPDATE SET
                dataset_version_id = EXCLUDED.dataset_version_id,
                boundary_geometry = EXCLUDED.boundary_geometry,
                area_m2 = EXCLUDED.area_m2,
                support_status = EXCLUDED.support_status,
                supported_from = EXCLUDED.supported_from,
                source_area_code = EXCLUDED.source_area_code,
                source_year = EXCLUDED.source_year,
                source_area_sqkm = EXCLUDED.source_area_sqkm,
                source_metadata = EXCLUDED.source_metadata
            RETURNING analysis_area_id
            """,
            (
                version_id, row["area_name"], row["area_type"], row["geometry_wkt"],
                row["source_srid"], row["area_m2"], ASGS_EFFECTIVE_DATE,
                row["source_area_code"], row["source_year"], row["source_area_sqkm"],
                json.dumps({
                    "change_flag": row["change_flag"],
                    "change_label": row["change_label"],
                    "state_name": row["state_name"],
                }),
            ),
        )
        analysis_area_id = cursor.fetchone()["analysis_area_id"]
        cursor.execute(
            """UPDATE dataset_version
               SET integration_status = 'integrated', publication_status = 'application_ready'
               WHERE dataset_version_id = %s""",
            (version_id,),
        )
    return {
        "rows_in": 1,
        "rows_written": 1,
        "rows_rejected": 0,
        "quality_pass_rate": report.pass_rate,
        "dataset_version_id": str(version_id),
        "analysis_area_id": str(analysis_area_id),
        "gccsa_code": row["source_area_code"],
        "area_sqkm": row["source_area_sqkm"],
        "raw_extract": str(raw_path),
        "message": "Official ABS ASGS 2026 Greater Melbourne boundary integrated",
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
            CASE WHEN %s::text IS NULL THEN NULL
                 ELSE ST_Transform(
                     ST_GeomFromText(%s::text, %s::integer),
                     {TARGET_SRID}
                 )
            END,
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
    accepted_rows = [
        row for index, row in enumerate(rows) if index not in report.failed_indices
    ]
    values = [
        (
            version_id,
            row["station_code"], row["station_name"], row["observed_at"],
            row["air_temperature_c"], row["apparent_temperature_c"],
            row["humidity_pct"], row["wind_speed_ms"],
            row["rainfall_since_9am_mm"], row["geometry_wkt"],
            row["geometry_wkt"], row["source_srid"],
        )
        for row in accepted_rows
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
    if normalised not in {"true", "false", "1", "0", "yes", "no", "y", "n"}:
        raise ValueError(f"Invalid Boolean value: {value}")
    return normalised in {"true", "1", "yes", "y"}


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

    accepted_rows = [
        row for index, row in enumerate(rows) if index not in report.failed_indices
    ]
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
        for row in accepted_rows
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
        ON CONFLICT (
            greening_option_id, cost_context, cost_basis, source_name,
            valid_from, source_reference
        ) DO UPDATE SET
            minimum_cost = EXCLUDED.minimum_cost,
            maximum_cost = EXCLUDED.maximum_cost,
            material_min_cost = EXCLUDED.material_min_cost,
            material_max_cost = EXCLUDED.material_max_cost,
            installation_min_cost = EXCLUDED.installation_min_cost,
            installation_max_cost = EXCLUDED.installation_max_cost,
            delivery_min_cost = EXCLUDED.delivery_min_cost,
            delivery_max_cost = EXCLUDED.delivery_max_cost,
            setup_min_cost = EXCLUDED.setup_min_cost,
            setup_max_cost = EXCLUDED.setup_max_cost,
            valid_to = EXCLUDED.valid_to,
            last_verified_at = EXCLUDED.last_verified_at,
            confidence_level = EXCLUDED.confidence_level
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


def _vicmap_extract(dataset_name: str, supplied_file: Path | None, args: argparse.Namespace):
    if supplied_file:
        if not supplied_file.exists():
            raise FileNotFoundError(supplied_file)
        return supplied_file, {
            "dataset": dataset_name,
            "source_service": "previously extracted Vicmap ArcGIS Feature Service file",
            "source_last_edited_at": None,
            "bbox_wgs84": list(args.vicmap_bbox),
            "record_count": sum(1 for _ in read_jsonl(supplied_file)),
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "output_path": str(supplied_file.resolve()),
        }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = ROOT / "data" / "raw" / "vicmap" / f"{dataset_name}_{stamp}.jsonl.gz"

    def progress(queries: int, records: int) -> None:
        print(f"  Vicmap {dataset_name}: {queries} spatial tiles queried, {records} records")

    metadata = extract_to_jsonl(
        dataset_name,
        path,
        bbox=args.vicmap_bbox,
        tile_degrees=args.vicmap_tile_degrees,
        minimum_tile_degrees=args.vicmap_minimum_tile_degrees,
        progress=progress,
    )
    manifest = path.with_suffix(path.suffix + ".manifest.json")
    manifest.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return path, metadata


def _vicmap_version_and_quality(
    connection,
    *,
    dataset_key: str,
    source_name: str,
    raw_path: Path,
    metadata: dict[str, Any],
    observed_from=None,
    observed_to=None,
):
    last_edited = metadata.get("source_last_edited_at")
    observed_on = datetime.fromisoformat(last_edited).date() if last_edited else None
    version_id = create_dataset_version(
        connection,
        registered_source_id=source_id(connection, source_name, "Victorian Government"),
        row_count=int(metadata["record_count"]),
        checksum=sha256_file(raw_path),
        observed_from=observed_from or observed_on,
        observed_to=observed_to or observed_on,
    )
    register_spatial_assets(
        connection,
        version_id,
        [{
            "asset_role": f"vicmap_{dataset_key}_feature_extract",
            "source_scene_id": raw_path.stem,
            "source_href": metadata["source_service"],
            "local_path": str(raw_path.resolve()),
            "media_type": "application/x-ndjson+gzip",
            "source_crs": "EPSG:4326",
            "checksum": sha256_file(raw_path),
            "acquired_at": metadata["extracted_at"],
            "metadata": metadata,
        }],
    )
    rules, threshold = quality_configuration(dataset_key)
    report = validate_record_stream(
        dataset_key,
        lambda: read_jsonl(raw_path),
        rules,
        threshold_pct=threshold,
    )
    record_quality_run(connection, version_id, report)
    return version_id, report


def ingest_address(connection, args: argparse.Namespace) -> dict[str, Any]:
    """Extract current Vicmap Address points for Melbourne and integrate them."""

    raw_path, metadata = _vicmap_extract("address", args.address_file, args)
    version_id, report = _vicmap_version_and_quality(
        connection,
        dataset_key="address",
        source_name="Vicmap Address",
        raw_path=raw_path,
        metadata=metadata,
    )
    if not report.passed_gate:
        connection.commit()
        return {
            "rows_in": report.total_records,
            "rows_written": 0,
            "rows_rejected": report.failing_records,
            "quality_pass_rate": report.pass_rate,
            "dataset_version_id": str(version_id),
            "message": "Vicmap Address failed the quality gate; nothing integrated",
        }

    rejected = set(report.failed_indices)
    values = (
        (
            version_id,
            row["source_address_id"],
            row["source_property_id"],
            row["full_address"],
            row["locality_name"],
            row["postcode"],
            row["lga_code"],
            row["is_primary"],
            row["address_class"],
            row["geometry_wkt"],
            row["source_srid"],
        )
        for index, row in enumerate(read_jsonl(raw_path))
        if index not in rejected
    )
    written = write_record_stream(
        connection,
        f"""
        INSERT INTO address (
            dataset_version_id, source_address_id, source_property_id,
            full_address, locality_name, postcode, lga_code, is_primary,
            address_class, address_location
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s,
            ST_Transform(ST_GeomFromText(%s::text, %s::integer), {TARGET_SRID})
        )
        """,
        values,
    )
    with connection.cursor() as cursor:
        cursor.execute(
            """UPDATE dataset_version SET integration_status = 'integrated',
               publication_status = 'application_ready' WHERE dataset_version_id = %s""",
            (version_id,),
        )
    return {
        "rows_in": report.total_records,
        "rows_written": written,
        "rows_rejected": report.failing_records,
        "quality_pass_rate": report.pass_rate,
        "dataset_version_id": str(version_id),
        "raw_extract": str(raw_path),
        "message": f"{written} Vicmap Address points integrated for Melbourne",
    }


def ingest_property(connection, args: argparse.Namespace) -> dict[str, Any]:
    """Extract current Vicmap Property polygons into the parcel entity."""

    raw_path, metadata = _vicmap_extract("property", args.property_file, args)
    version_id, report = _vicmap_version_and_quality(
        connection,
        dataset_key="parcel",
        source_name="Vicmap Property",
        raw_path=raw_path,
        metadata=metadata,
    )
    if not report.passed_gate:
        connection.commit()
        return {
            "rows_in": report.total_records,
            "rows_written": 0,
            "rows_rejected": report.failing_records,
            "quality_pass_rate": report.pass_rate,
            "dataset_version_id": str(version_id),
            "message": "Vicmap Property failed the quality gate; nothing integrated",
        }

    rejected = set(report.failed_indices)
    values = (
        (
            version_id,
            row["source_parcel_id"],
            row["property_number"],
            row["property_type"],
            row["property_status"],
            row["lga_code"],
            row["geometry_wkt"],
            row["source_srid"],
            row["parcel_area_m2"],
        )
        for index, row in enumerate(read_jsonl(raw_path))
        if index not in rejected
    )
    written = write_record_stream(
        connection,
        f"""
        INSERT INTO parcel (
            dataset_version_id, source_parcel_id, property_number,
            property_type, property_status, lga_code, parcel_geometry,
            parcel_area_m2
        ) VALUES (
            %s, %s, %s, %s, %s, %s,
            ST_Transform(ST_GeomFromText(%s::text, %s::integer), {TARGET_SRID}), %s
        )
        """,
        values,
    )
    with connection.cursor() as cursor:
        cursor.execute(
            """UPDATE dataset_version SET integration_status = 'integrated',
               publication_status = 'application_ready' WHERE dataset_version_id = %s""",
            (version_id,),
        )
    return {
        "rows_in": report.total_records,
        "rows_written": written,
        "rows_rejected": report.failing_records,
        "quality_pass_rate": report.pass_rate,
        "dataset_version_id": str(version_id),
        "raw_extract": str(raw_path),
        "message": f"{written} Vicmap Property polygons integrated for Melbourne",
    }


def ingest_trees(connection, args: argparse.Namespace) -> dict[str, Any]:
    """Extract mapped Vicmap Tree Urban points for property-level context."""

    raw_path, metadata = _vicmap_extract("urban_tree", args.urban_tree_file, args)
    version_id, report = _vicmap_version_and_quality(
        connection,
        dataset_key="urban_tree",
        source_name="Vicmap Vegetation - Tree Urban Point",
        raw_path=raw_path,
        metadata=metadata,
        observed_from="2018-12-07",
        observed_to="2020-11-02",
    )
    if not report.passed_gate:
        connection.commit()
        return {
            "rows_in": report.total_records,
            "rows_written": 0,
            "rows_rejected": report.failing_records,
            "quality_pass_rate": report.pass_rate,
            "dataset_version_id": str(version_id),
            "message": "Vicmap Tree Urban failed the quality gate; nothing integrated",
        }

    rejected = set(report.failed_indices)
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT analysis_area_id
               FROM analysis_area
               WHERE source_area_code = '2GMEL' AND source_year = 2026"""
        )
        area = cursor.fetchone()
        if area is None:
            raise RuntimeError(
                "Official Greater Melbourne boundary is missing; run the boundary job first"
            )
        analysis_area_id = area["analysis_area_id"]

        # COPY is substantially faster than millions of individual INSERTs.
        # The temporary table also lets PostGIS perform the official-boundary
        # filter as one audited, set-based operation.
        cursor.execute(
            """CREATE TEMP TABLE urban_tree_stage (
                   source_tree_id TEXT,
                   feature_type TEXT,
                   feature_subtype TEXT,
                   dense_canopy BOOLEAN,
                   geometry_wkt TEXT NOT NULL,
                   source_srid INTEGER NOT NULL,
                   canopy_radius_m NUMERIC,
                   height_m NUMERIC,
                   source_observed_from DATE,
                   source_observed_to DATE
               ) ON COMMIT DROP"""
        )
        staged = 0
        with cursor.copy(
            """COPY urban_tree_stage (
                   source_tree_id, feature_type, feature_subtype, dense_canopy,
                   geometry_wkt, source_srid, canopy_radius_m, height_m,
                   source_observed_from, source_observed_to
               ) FROM STDIN"""
        ) as copy:
            for index, row in enumerate(read_jsonl(raw_path)):
                if index in rejected:
                    continue
                copy.write_row(
                    (
                        row["source_tree_id"],
                        row["feature_type"],
                        row["feature_subtype"],
                        optional_bool(row["dense_canopy"]),
                        row["geometry_wkt"],
                        row["source_srid"],
                        row["canopy_radius_m"],
                        row["height_m"],
                        row["source_observed_from"],
                        row["source_observed_to"],
                    )
                )
                staged += 1

        cursor.execute(
            f"""WITH candidates AS MATERIALIZED (
                     SELECT stage.*,
                            ST_Transform(
                                ST_GeomFromText(stage.geometry_wkt, stage.source_srid),
                                {TARGET_SRID}
                            ) AS tree_location
                     FROM urban_tree_stage AS stage
                 )
                 INSERT INTO urban_tree (
                     dataset_version_id, source_tree_id, feature_type,
                     feature_subtype, dense_canopy, tree_location,
                     canopy_radius_m, height_m, source_observed_from,
                     source_observed_to, quality_status
                 )
                 SELECT %s, candidate.source_tree_id, candidate.feature_type,
                        candidate.feature_subtype, candidate.dense_canopy,
                        candidate.tree_location,
                        CASE WHEN candidate.canopy_radius_m BETWEEN 0.25 AND 50
                             THEN candidate.canopy_radius_m END,
                        CASE WHEN candidate.height_m BETWEEN 0.5 AND 100
                             THEN candidate.height_m END,
                        candidate.source_observed_from,
                        candidate.source_observed_to, 'passed'
                 FROM candidates AS candidate
                 WHERE EXISTS (
                     SELECT 1
                     FROM analysis_area_tile AS tile
                     WHERE tile.analysis_area_id = %s
                       AND tile.tile_geometry && candidate.tree_location
                       AND ST_Covers(tile.tile_geometry, candidate.tree_location)
                 )""",
            (version_id, analysis_area_id),
        )
        cursor.execute(
            "SELECT COUNT(*) AS row_count FROM urban_tree WHERE dataset_version_id = %s",
            (version_id,),
        )
        written = cursor.fetchone()["row_count"]
        boundary_excluded = staged - written
        cursor.execute(
            """UPDATE dataset_version
               SET integration_status = 'integrated',
                   publication_status = 'application_ready',
                   analysis_area_id = %s,
                   derivation_method = 'filter_to_abs_gccsa_2GMEL_2026_v1:point_covered',
                   coverage_pass_rate = 100
               WHERE dataset_version_id = %s""",
            (analysis_area_id, version_id),
        )
        cursor.execute(
            """INSERT INTO data_limitation (
                   dataset_version_id, limitation_type, description,
                   affected_area, analytical_impact, mitigation
               ) VALUES (%s, 'mapped_tree_points_not_field_inventory', %s,
                         'Greater Melbourne', %s, %s)""",
            (
                version_id,
                "Tree Urban points were machine-extracted from high-resolution aerial photography and assigned height using a LiDAR-derived canopy-height model.",
                "Points improve individual-tree context but do not prove current tree presence, ownership, health or exact crown extent.",
                "Label them as mapped tree points, retain source dates, and do not replace site inspection.",
            ),
        )
        if boundary_excluded:
            cursor.execute(
                """INSERT INTO data_limitation (
                       dataset_version_id, limitation_type, description,
                       affected_area, analytical_impact, mitigation
                   ) VALUES (%s, 'source_bbox_clipped_to_official_boundary', %s,
                             'Vicmap extraction bounding box', %s, %s)""",
                (
                    version_id,
                    f"{boundary_excluded} quality-passing API records outside the official ABS 2026 Greater Melbourne boundary were excluded.",
                    "The application-ready tree version contains only points covered by 2GMEL.",
                    "Retain the raw extract and boundary-filter derivation metadata for reproducibility.",
                ),
            )
    return {
        "rows_in": report.total_records,
        "rows_written": written,
        "rows_rejected": report.failing_records,
        "rows_outside_greater_melbourne": boundary_excluded,
        "quality_pass_rate": report.pass_rate,
        "boundary_membership_pass_rate": 100.0,
        "dataset_version_id": str(version_id),
        "raw_extract": str(raw_path),
        "message": f"{written} Vicmap Tree Urban points integrated inside Greater Melbourne",
    }


def ingest_canopy(connection, args: argparse.Namespace) -> dict[str, Any]:
    """Aggregate an official Vicmap Tree Extent GeoTIFF and integrate it."""

    if args.canopy_file is None or args.canopy_observed_on is None:
        raise ValueError("canopy requires --canopy-file and --canopy-observed-on")
    if not args.canopy_file.exists():
        raise FileNotFoundError(args.canopy_file)
    observed_on = datetime.strptime(args.canopy_observed_on, "%Y-%m-%d").date()
    observed_from = (
        datetime.strptime(args.canopy_observed_from, "%Y-%m-%d").date()
        if args.canopy_observed_from else observed_on
    )
    sidecar_path = args.canopy_file.with_suffix(args.canopy_file.suffix + ".json")
    api_metadata = (
        json.loads(sidecar_path.read_text(encoding="utf-8"))
        if sidecar_path.exists() else None
    )
    rows, metadata = aggregate_canopy(
        args.canopy_file,
        observed_on=observed_on,
        grid_size_m=args.grid_size_m,
        tree_value=args.tree_value,
    )
    registered_source_id = source_id(
        connection, "Vicmap Vegetation - Tree Extent", "Victorian Government"
    )
    version_id = create_dataset_version(
        connection,
        registered_source_id=registered_source_id,
        row_count=int(metadata["width"]) * int(metadata["height"]),
        checksum=sha256_file(args.canopy_file),
        observed_from=observed_from,
        observed_to=observed_on,
        spatial_resolution_m=args.grid_size_m,
    )
    register_spatial_assets(
        connection,
        version_id,
        [{
            "asset_role": "canopy_api_tile_mosaic" if api_metadata else "canopy_source_raster",
            "source_scene_id": args.canopy_file.stem,
            "source_href": api_metadata.get("source_service") if api_metadata else None,
            "local_path": str(args.canopy_file.resolve()),
            "media_type": "image/tiff; application=geotiff",
            "source_crs": metadata["crs"],
            "pixel_size_m": max(metadata["pixel_size"]),
            "checksum": sha256_file(args.canopy_file),
            "acquired_at": f"{observed_on.isoformat()}T00:00:00Z",
            "metadata": {**metadata, "api_extraction": api_metadata} if api_metadata else metadata,
        }],
    )
    if api_metadata:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO data_limitation (
                       dataset_version_id, limitation_type, description,
                       affected_area, analytical_impact, mitigation
                   ) VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    version_id,
                    "rendered_tile_proxy",
                    "Canopy was reconstructed from official cached PNG tiles, not the original analytical GeoTIFF.",
                    "Melbourne extraction bbox",
                    f"Source proxy resolution is approximately {api_metadata['resolution_m']:.2f} m; small crowns and edges may be generalised.",
                    "Use 500 m summaries only and replace this version when the original analytical GeoTIFF becomes available.",
                ),
            )
    rules, threshold = quality_configuration("vegetation_observation")
    report = validate_records("vegetation_observation", rows, rules, threshold_pct=threshold)
    record_quality_run(connection, version_id, report)
    if not report.passed_gate:
        connection.commit()
        return {
            "rows_in": len(rows), "rows_written": 0,
            "rows_rejected": report.failing_records,
            "quality_pass_rate": report.pass_rate,
            "message": "Canopy extract failed the quality gate; nothing integrated",
        }
    accepted = [row for i, row in enumerate(rows) if i not in report.failed_indices]
    values = [
        (
            version_id, row["geometry_wkt"], row["source_srid"], row["observed_on"],
            row["vegetation_type"], row["vegetation_percentage"],
            row["calculation_method"], row["spatial_resolution_m"],
            row["confidence_score"],
        )
        for row in accepted
    ]
    written = write_batches(
        connection,
        f"""
        INSERT INTO vegetation_observation (
            dataset_version_id, observation_geometry, observed_on,
            vegetation_type, vegetation_percentage, calculation_method,
            spatial_resolution_m, confidence_score, quality_status
        )
        VALUES (
            %s, ST_Transform(ST_GeomFromText(%s::text, %s::integer), {TARGET_SRID}),
            %s, %s, %s, %s, %s, %s, 'passed'
        )
        """,
        values,
    )
    with connection.cursor() as cursor:
        cursor.execute(
            """UPDATE dataset_version SET integration_status = 'integrated',
               publication_status = 'application_ready' WHERE dataset_version_id = %s""",
            (version_id,),
        )
    return {
        "rows_in": len(rows), "rows_written": written,
        "rows_rejected": report.failing_records,
        "quality_pass_rate": report.pass_rate,
        "dataset_version_id": str(version_id),
        "source_profile": metadata,
        "message": f"{written} Melbourne canopy grid cells integrated",
    }


def ingest_heat(connection, args: argparse.Namespace) -> dict[str, Any]:
    """Discover, download and integrate official Landsat surface temperature."""

    start = datetime.strptime(args.heat_start, "%Y-%m-%d").date() if args.heat_start else None
    end = datetime.strptime(args.heat_end, "%Y-%m-%d").date() if args.heat_end else None
    items = search_surface_temperature(
        start=start, end=end, max_cloud_pct=args.max_cloud_pct
    )
    selected = choose_scenes(items, max_scenes=args.max_heat_scenes)
    if not selected:
        raise RuntimeError("No usable Landsat surface-temperature scenes met the cloud threshold")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest_path = ROOT / "data" / "raw" / "landsat" / f"stac_{stamp}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({"features": selected}, indent=2), encoding="utf-8")

    rows: list[dict[str, Any]] = []
    assets: list[dict[str, Any]] = []
    access_token = planetary_computer_token()
    for item in selected:
        scene_directory = ROOT / "data" / "raw" / "landsat" / item["id"]
        temperature_path = download_asset(
            signed_asset_href(item["assets"]["lwir11"]["href"], access_token),
            scene_directory / "surface_temperature.tif",
        )
        qa_path = download_asset(
            signed_asset_href(item["assets"]["qa_pixel"]["href"], access_token),
            scene_directory / "qa_pixel.tif",
        )
        rows.extend(
            aggregate_surface_temperature(
                temperature_path, qa_path, item=item, grid_size_m=args.grid_size_m
            )
        )
        temperature_asset = asset_metadata(item, "lwir11", temperature_path)
        qa_asset = asset_metadata(item, "qa_pixel", qa_path)
        temperature_asset["checksum"] = sha256_file(temperature_path)
        qa_asset["checksum"] = sha256_file(qa_path)
        assets.extend([temperature_asset, qa_asset])

    dates = sorted({row["observed_on"] for row in rows})
    mean_cloud = sum(float(i["properties"].get("eo:cloud_cover", 0)) for i in selected) / len(selected)
    registered_source_id = source_id(
        connection,
        "USGS Landsat Collection 2 Surface Temperature",
        "United States Geological Survey",
    )
    version_id = create_dataset_version(
        connection,
        registered_source_id=registered_source_id,
        row_count=len(rows),
        checksum=sha256_file(manifest_path),
        observed_from=dates[0] if dates else None,
        observed_to=dates[-1] if dates else None,
        spatial_resolution_m=args.grid_size_m,
        cloud_cover_pct=round(mean_cloud, 2),
    )
    for asset in assets:
        asset["target_srid"] = TARGET_SRID
    register_spatial_assets(connection, version_id, assets)
    rules, threshold = quality_configuration("heat_observation")
    report = validate_records("heat_observation", rows, rules, threshold_pct=threshold)
    record_quality_run(connection, version_id, report)
    if not report.passed_gate:
        connection.commit()
        return {
            "rows_in": len(rows), "rows_written": 0,
            "rows_rejected": report.failing_records,
            "quality_pass_rate": report.pass_rate,
            "message": "Landsat extract failed the quality gate; nothing integrated",
        }
    accepted = [row for i, row in enumerate(rows) if i not in report.failed_indices]
    values = [
        (
            version_id, row["geometry_wkt"], row["source_srid"], row["observed_on"],
            row["observed_at"], row["heat_value"], row["measurement_type"],
            row["unit"], row["source_scene_id"], row["cloud_cover_pct"],
        )
        for row in accepted
    ]
    written = write_batches(
        connection,
        f"""
        INSERT INTO heat_observation (
            dataset_version_id, observation_geometry, observed_on, observed_at,
            heat_value, measurement_type, unit, source_scene_id,
            cloud_cover_pct, quality_status
        )
        VALUES (
            %s, ST_Transform(ST_GeomFromText(%s::text, %s::integer), {TARGET_SRID}),
            %s, %s, %s, %s, %s, %s, %s, 'passed'
        )
        """,
        values,
    )
    with connection.cursor() as cursor:
        cursor.execute(
            """UPDATE dataset_version SET integration_status = 'integrated',
               publication_status = 'application_ready' WHERE dataset_version_id = %s""",
            (version_id,),
        )
    return {
        "rows_in": len(rows), "rows_written": written,
        "rows_rejected": report.failing_records,
        "quality_pass_rate": report.pass_rate,
        "dataset_version_id": str(version_id),
        "scenes": [item["id"] for item in selected],
        "message": f"{written} Landsat heat grid cells integrated",
    }


Job = Callable[[Any, argparse.Namespace], dict[str, Any]]
JOBS: dict[str, Job] = {
    "sources": sync_sources,
    "boundary": ingest_boundary,
    "bom": ingest_bom,
    "costs": ingest_costs,
    "canopy": ingest_canopy,
    "heat": ingest_heat,
    "address": ingest_address,
    "property": ingest_property,
    "trees": ingest_trees,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jobs", nargs="*", choices=JOBS, default=["sources"])
    parser.add_argument("--bom-url", default=DEFAULT_BOM_URL)
    parser.add_argument("--cost-file", type=Path, default=DEFAULT_COST_FILE)
    parser.add_argument("--canopy-file", type=Path)
    parser.add_argument("--canopy-observed-on", help="Source imagery date: YYYY-MM-DD")
    parser.add_argument("--canopy-observed-from", help="Earliest source imagery date: YYYY-MM-DD")
    parser.add_argument("--tree-value", type=float)
    parser.add_argument("--grid-size-m", type=float, default=500.0)
    parser.add_argument("--heat-start", help="Landsat search start: YYYY-MM-DD")
    parser.add_argument("--heat-end", help="Landsat search end: YYYY-MM-DD")
    parser.add_argument("--max-cloud-pct", type=float, default=30.0)
    parser.add_argument("--max-heat-scenes", type=int, default=4)
    parser.add_argument("--address-file", type=Path, help="Reuse a gzip address JSONL extract")
    parser.add_argument("--property-file", type=Path, help="Reuse a gzip property JSONL extract")
    parser.add_argument("--urban-tree-file", type=Path, help="Reuse a gzip Tree Urban JSONL extract")
    parser.add_argument(
        "--vicmap-bbox", nargs=4, type=float,
        default=(144.4, -38.5, 146.0, -37.4),
        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
        help="EPSG:4326 extraction extent; defaults to the Melbourne project extent.",
    )
    parser.add_argument("--vicmap-tile-degrees", type=float, default=0.1)
    parser.add_argument("--vicmap-minimum-tile-degrees", type=float, default=0.0015625)
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
