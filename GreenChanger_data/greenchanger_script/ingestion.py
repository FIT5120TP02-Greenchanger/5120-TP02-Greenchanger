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
import gzip
import json
from pathlib import Path
import sys
from typing import Any, Callable, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_script import db  # noqa: E402
from greenchanger_data.bom import (
    DEFAULT_STATION_REGISTRY,
    extract_rows,
    extract_station_rows,
    fetch_observations,
    fetch_station_documents,
    load_station_registry,
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
from greenchanger_data.city_melbourne_trees import (
    fetch_records as fetch_named_tree_records,
    normalise_records as normalise_named_tree_records,
    read_raw as read_named_tree_raw,
    save_raw as save_named_tree_raw,
)
from greenchanger_data.city_canopy_history import (
    SOURCE_NAMES as CITY_CANOPY_SOURCE_NAMES,
    download as download_city_canopy,
    limited as limit_city_canopy_rows,
    normalised_rows as normalised_city_canopy_rows,
    read_raw as read_city_canopy_raw,
)
from greenchanger_data.council_tree_inventories import (
    SOURCES as COUNCIL_TREE_SOURCES,
    download as download_council_trees,
    feature_count as council_tree_feature_count,
    iter_normalised as iter_council_tree_rows,
)
from greenchanger_data.property_canopy import validate_property_canopy_source
from greenchanger_data.landsat import (
    aggregate_surface_temperature,
    asset_metadata,
    choose_scenes,
    download_asset,
    planetary_computer_token,
    search_surface_temperature,
    signed_asset_href,
)
from greenchanger_data.metropolitan_vegetation_change import (
    SOURCE_NAME as VEGETATION_CHANGE_SOURCE_NAME,
    feature_count as vegetation_change_feature_count,
    normalised_rows as normalised_vegetation_change_rows,
    source_checksum as vegetation_change_source_checksum,
)
from greenchanger_data.quality import QualityReport, validate_record_stream, validate_records
from greenchanger_data.research_tree_data import (
    AUSTRAITS_SOURCE_NAME,
    URBAN_GROWTH_SOURCE_NAME,
    austraits_counts,
    combined_checksum,
    download_austraits,
    download_urban_growth,
    iter_austraits_rows,
    normalise_climate_rows,
    normalise_growth_rows,
    read_urban_growth_workbook,
)
from greenchanger_data.sources import load_source_registry, sha256_file
from greenchanger_data.vicmap_features import extract_to_jsonl, read_jsonl


BATCH_SIZE = 2_000
TARGET_SRID = 7855
DATASETS_CONFIG = ROOT / "config" / "datasets.json"
QUALITY_CONFIG = ROOT / "config" / "quality_rules.json"
DEFAULT_COST_FILE = ROOT / "data" / "reference" / "cost_estimates_template.csv"


def analytical_canopy_manifest(raster_path: Path) -> dict[str, Any] | None:
    """Load and verify the manifest beside a prepared analytical VRT."""

    if raster_path.suffix.lower() != ".vrt":
        return None
    manifest_path = raster_path.parent / "melbourne_tree_extent_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Prepared analytical VRT requires its provenance manifest: {manifest_path}"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("dataset_uuid") != "f6800447-ef34-5f66-acaa-77a5f2936546":
        raise ValueError("Analytical canopy manifest has the wrong DataShare dataset UUID")
    mosaic = manifest.get("virtual_mosaic", {})
    if mosaic.get("sha256") != sha256_file(raster_path):
        raise ValueError("Analytical canopy VRT checksum does not match its manifest")
    bounds = manifest.get("boundary", {}).get("boundary_wgs84_bounds")
    if not isinstance(bounds, list) or len(bounds) != 4:
        raise ValueError("Analytical canopy manifest has no Melbourne boundary bounds")
    return {**manifest, "manifest_path": str(manifest_path.resolve())}


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
    """Save evidence for Data Quality & Preparation."""

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
            source.get("licence_status", "review_required"),
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
            source_name, publisher, source_url, licence, licence_status, source_category,
            geographic_coverage, access_method, update_frequency
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (source_name, publisher) DO UPDATE SET
            source_url = EXCLUDED.source_url,
            licence = EXCLUDED.licence,
            licence_status = EXCLUDED.licence_status,
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
    """Version and integrate the official ABS 2026 Melbourne GCCSA."""

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
            "message": "Melbourne boundary failed the quality gate; nothing integrated",
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
        "message": "Official ABS ASGS 2026 Melbourne boundary integrated",
    }


def ingest_bom(connection, args: argparse.Namespace) -> dict[str, Any]:
    """Fetch, preserve, validate, version and integrate BOM observations."""

    multi_station_run = not bool(args.bom_url)
    if args.bom_url:
        document = fetch_observations(args.bom_url)
        raw_rows = extract_rows(document)
        station_codes = sorted(
            {str(row.get("wmo") or row.get("history_product") or "") for row in raw_rows}
        )
        registry_version = "single-feed-override"
    else:
        registry = load_station_registry(args.bom_stations_file)
        document = fetch_station_documents(registry)
        raw_rows = extract_station_rows(document)
        station_codes = [
            str(feed["station"]["station_code"])
            for feed in document["station_feeds"]
        ]
        failed_stations = document.get("failed_station_feeds", [])
        requested_station_count = len(registry["stations"])
        registry_version = registry["registry_version"]
    if args.bom_url:
        failed_stations = []
        requested_station_count = len(station_codes)
    rows = normalise_rows(raw_rows)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = ROOT / "data" / "raw" / "bom" / f"greater_melbourne_{stamp}.json"
    save_raw(document, raw_path)

    registered_source_id = source_id(
        connection,
        "BOM Melbourne station observations",
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
    station_coverage_pct = round(
        len(station_codes) * 100.0 / requested_station_count, 2
    ) if requested_station_count else 0.0
    publish_weather = multi_station_run and station_coverage_pct >= 80.0
    with connection.cursor() as cursor:
        cursor.execute(
            """UPDATE dataset_version
               SET integration_status = 'integrated',
                   publication_status = %s,
                   coverage_pass_rate = %s,
                   quality_status = %s
               WHERE dataset_version_id = %s""",
            (
                "application_ready" if publish_weather else "internal",
                station_coverage_pct,
                "passed_with_limitations" if failed_stations else "passed",
                version_id,
            ),
        )
        if failed_stations:
            cursor.execute(
                """INSERT INTO data_limitation (
                       dataset_version_id, limitation_type, description,
                       affected_area, analytical_impact, mitigation
                   ) VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    version_id,
                    "partial_station_feed_availability",
                    f"{len(failed_stations)} of {requested_station_count} configured BOM station feeds failed during extraction.",
                    ", ".join(item["coverage_role"] for item in failed_stations),
                    "Some properties may use a more distant station or return Unavailable.",
                    "Retry ingestion and retain the distance, timestamp and context status in every property result.",
                ),
            )
    return {
        "rows_in": len(raw_rows),
        "rows_written": written,
        "rows_rejected": report.failing_records,
        "quality_pass_rate": report.pass_rate,
        "dataset_version_id": str(version_id),
        "station_count": len(station_codes),
        "requested_station_count": requested_station_count,
        "station_coverage_pct": station_coverage_pct,
        "station_codes": station_codes,
        "failed_stations": failed_stations,
        "registry_version": registry_version,
        "publication_status": (
            "application_ready" if publish_weather else "internal"
        ),
        "message": (
            f"{written} BOM observations from {len(station_codes)} stations "
            f"integrated from {raw_path.name}"
        ),
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
            row["tree_type"] or None, row["botanical_name"] or None,
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
            planting_method, stock_size, tree_type, botanical_name,
            minimum_cost, maximum_cost,
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
            %s, %s, %s, %s, %s
        FROM greening_option AS go
        WHERE go.option_code = %s
        ON CONFLICT (
            greening_option_id, cost_context, cost_basis, tree_type,
            source_name, valid_from, source_reference
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
            botanical_name = EXCLUDED.botanical_name,
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
        )
        SELECT %s, %s, %s, %s, %s, %s, prepared.geometry,
               ST_Area(prepared.geometry)
        FROM (
            SELECT ST_Transform(
                ST_GeomFromText(%s::text, %s::integer), {TARGET_SRID}
            ) AS geometry
        ) AS prepared
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
                "Official Melbourne boundary is missing; run the boundary job first"
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
                         'Melbourne', %s, %s)""",
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
                    f"{boundary_excluded} quality-passing API records outside the official ABS 2026 Melbourne boundary were excluded.",
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
        "message": f"{written} Vicmap Tree Urban points integrated inside Melbourne",
    }


def ingest_named_trees(connection, args: argparse.Namespace) -> dict[str, Any]:
    """Load source-labelled City of Melbourne tree names without inferring Vicmap names."""

    if args.city_tree_file:
        if not args.city_tree_file.exists():
            raise FileNotFoundError(args.city_tree_file)
        raw_path = args.city_tree_file
        raw_records = list(read_named_tree_raw(raw_path))
    else:
        raw_records = fetch_named_tree_records()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        raw_path = (
            ROOT / "data" / "raw" / "city_melbourne"
            / f"named_trees_{stamp}.jsonl.gz"
        )
        save_named_tree_raw(raw_records, raw_path)

    rows = normalise_named_tree_records(raw_records)
    rules, threshold = quality_configuration("named_tree_inventory")
    report = validate_records(
        "named_tree_inventory", rows, rules, threshold_pct=threshold
    )
    registered_source_id = source_id(
        connection,
        "Trees, with species and dimensions (Urban Forest)",
        "City of Melbourne",
    )
    version_id = create_dataset_version(
        connection,
        registered_source_id=registered_source_id,
        row_count=len(rows),
        checksum=sha256_file(raw_path),
    )
    record_quality_run(connection, version_id, report)
    if not report.passed_gate:
        connection.commit()
        return {
            "rows_in": len(rows),
            "rows_written": 0,
            "rows_rejected": report.failing_records,
            "quality_pass_rate": report.pass_rate,
            "dataset_version_id": str(version_id),
            "message": "Named-tree inventory failed the quality gate; nothing integrated",
        }

    rejected = set(report.failed_indices)
    accepted = [row for index, row in enumerate(rows) if index not in rejected]
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT analysis_area_id FROM analysis_area
               WHERE source_area_code = '2GMEL' AND source_year = 2026
               ORDER BY analysis_area_id DESC LIMIT 1"""
        )
        area = cursor.fetchone()
        if area is None:
            raise ValueError("Load the official Melbourne boundary before named trees")
        analysis_area_id = area["analysis_area_id"]

        species: dict[str, tuple[str | None, str | None, str | None]] = {}
        for row in accepted:
            if row["scientific_name"]:
                species.setdefault(
                    row["scientific_name"],
                    (row["common_name"], row["genus"], row["family"]),
                )
        cursor.executemany(
            """INSERT INTO species_profile (
                   scientific_name, common_name, genus, family, source_reference
               ) VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (scientific_name) DO UPDATE SET
                   common_name = COALESCE(species_profile.common_name, EXCLUDED.common_name),
                   genus = COALESCE(species_profile.genus, EXCLUDED.genus),
                   family = COALESCE(species_profile.family, EXCLUDED.family),
                   source_reference = COALESCE(
                       species_profile.source_reference, EXCLUDED.source_reference
                   )""",
            [
                (
                    scientific_name, values[0], values[1], values[2],
                    "City of Melbourne Trees, with species and dimensions (Urban Forest)",
                )
                for scientific_name, values in species.items()
            ],
        )

        cursor.execute(
            """CREATE TEMP TABLE named_tree_stage (
                   source_tree_id TEXT, common_name TEXT, scientific_name TEXT,
                   display_name TEXT, genus TEXT, family TEXT,
                   diameter_breast_height_cm NUMERIC, year_planted INTEGER,
                   date_planted DATE, age_description TEXT,
                   useful_life_expectancy TEXT,
                   useful_life_expectancy_years INTEGER, precinct TEXT,
                   located_in TEXT, geometry_wkt TEXT, source_srid INTEGER
               ) ON COMMIT DROP"""
        )
        with cursor.copy(
            """COPY named_tree_stage (
                   source_tree_id, common_name, scientific_name, display_name,
                   genus, family, diameter_breast_height_cm, year_planted,
                   date_planted, age_description, useful_life_expectancy,
                   useful_life_expectancy_years, precinct, located_in,
                   geometry_wkt, source_srid
               ) FROM STDIN"""
        ) as copy:
            for row in accepted:
                copy.write_row(
                    (
                        row["source_tree_id"], row["common_name"],
                        row["scientific_name"], row["display_name"],
                        row["genus"], row["family"],
                        row["diameter_breast_height_cm"], row["year_planted"],
                        row["date_planted"], row["age_description"],
                        row["useful_life_expectancy"],
                        row["useful_life_expectancy_years"], row["precinct"],
                        row["located_in"], row["geometry_wkt"], row["source_srid"],
                    )
                )

        cursor.execute(
            f"""WITH candidates AS MATERIALIZED (
                     SELECT stage.*,
                            ST_Transform(
                                ST_GeomFromText(stage.geometry_wkt, stage.source_srid),
                                {TARGET_SRID}
                            ) AS tree_location
                     FROM named_tree_stage AS stage
                 )
                 INSERT INTO named_tree_inventory (
                     dataset_version_id, source_tree_id, species_id,
                     inventory_source_key, municipality, taxonomic_precision,
                     common_name, scientific_name, display_name, genus, family,
                     diameter_breast_height_cm, year_planted, date_planted,
                     age_description, useful_life_expectancy,
                     useful_life_expectancy_years, precinct, located_in,
                     tree_location, quality_status
                 )
                 SELECT %s, candidate.source_tree_id, species.species_id,
                        'city_melbourne', 'City of Melbourne',
                        CASE
                            WHEN candidate.scientific_name IS NOT NULL THEN 'species'
                            WHEN candidate.common_name IS NOT NULL THEN 'common_name'
                            ELSE NULL
                        END,
                        candidate.common_name, candidate.scientific_name,
                        candidate.display_name, candidate.genus, candidate.family,
                        candidate.diameter_breast_height_cm,
                        candidate.year_planted, candidate.date_planted,
                        candidate.age_description,
                        candidate.useful_life_expectancy,
                        candidate.useful_life_expectancy_years,
                        candidate.precinct, candidate.located_in,
                        candidate.tree_location, 'passed'
                 FROM candidates AS candidate
                 LEFT JOIN species_profile AS species
                   ON species.scientific_name = candidate.scientific_name
                 WHERE EXISTS (
                     SELECT 1 FROM analysis_area_tile AS tile
                     WHERE tile.analysis_area_id = %s
                       AND tile.tile_geometry && candidate.tree_location
                       AND ST_Covers(tile.tile_geometry, candidate.tree_location)
                 )""",
            (version_id, analysis_area_id),
        )
        written = cursor.rowcount
        boundary_excluded = len(accepted) - written
        cursor.execute(
            """UPDATE dataset_version
               SET integration_status = 'integrated',
                   publication_status = 'application_ready',
                   analysis_area_id = %s,
                   derivation_method = 'city_inventory_filter_to_abs_2GMEL_2026_v1',
                   coverage_pass_rate = %s
               WHERE dataset_version_id = %s""",
            (
                analysis_area_id,
                round(100.0 * written / len(accepted), 6) if accepted else 0,
                version_id,
            ),
        )
        cursor.execute(
            """INSERT INTO data_limitation (
                   dataset_version_id, limitation_type, description,
                   affected_area, analytical_impact, mitigation
               ) VALUES (%s, 'city_melbourne_only', %s, %s, %s, %s)""",
            (
                version_id,
                "Tree names come from the City of Melbourne maintained-tree inventory.",
                "City of Melbourne municipality",
                "Named trees are unavailable elsewhere in metropolitan Melbourne and are not matched to Vicmap points.",
                "Return Unavailable outside inventory coverage and preserve the source label.",
            ),
        )

    return {
        "rows_in": len(rows),
        "rows_written": written,
        "rows_rejected": report.failing_records,
        "rows_outside_melbourne": boundary_excluded,
        "quality_pass_rate": report.pass_rate,
        "dataset_version_id": str(version_id),
        "raw_extract": str(raw_path),
        "message": f"{written} source-labelled City of Melbourne named trees integrated",
    }


def ingest_council_named_trees(
    connection, args: argparse.Namespace, council_key: str
) -> dict[str, Any]:
    """Load one council inventory while retaining its source-specific limitations."""

    source = COUNCIL_TREE_SOURCES[council_key]
    if args.council_tree_file:
        if not args.council_tree_file.exists():
            raise FileNotFoundError(args.council_tree_file)
        raw_path = args.council_tree_file
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        raw_path = download_council_trees(
            source, ROOT / "data" / "raw" / "council_trees" / council_key / stamp
        )

    raw_count = council_tree_feature_count(council_key, raw_path)
    inactive_count = 0
    unnamed_count = 0
    eligible_count = 0
    observed_dates: list[str] = []
    for row in iter_council_tree_rows(council_key, raw_path):
        if not row["active_record"]:
            inactive_count += 1
        elif not row["display_name"]:
            unnamed_count += 1
        else:
            eligible_count += 1
            if row["source_observed_on"]:
                observed_dates.append(row["source_observed_on"])

    def eligible_rows():
        for row in iter_council_tree_rows(council_key, raw_path):
            if row["active_record"] and row["display_name"]:
                yield row

    rules, threshold = quality_configuration("named_tree_inventory")
    report = validate_record_stream(
        "named_tree_inventory", eligible_rows, rules, threshold_pct=threshold
    )
    registered_source_id = source_id(connection, source.source_name, source.publisher)
    version_id = create_dataset_version(
        connection,
        registered_source_id=registered_source_id,
        row_count=raw_count,
        checksum=sha256_file(raw_path),
        observed_from=min(observed_dates) if observed_dates else None,
        observed_to=max(observed_dates) if observed_dates else None,
    )
    record_quality_run(connection, version_id, report)
    if not report.passed_gate:
        connection.commit()
        return {
            "rows_in": raw_count,
            "rows_eligible": eligible_count,
            "rows_written": 0,
            "rows_rejected": report.failing_records,
            "quality_pass_rate": report.pass_rate,
            "dataset_version_id": str(version_id),
            "message": f"{source.source_name} failed the quality gate; nothing integrated",
        }

    failed = set(report.failed_indices)

    def accepted_rows():
        for index, row in enumerate(eligible_rows()):
            if index not in failed:
                yield row

    species: dict[str, tuple[str | None, str | None, str | None]] = {}
    for row in accepted_rows():
        if row["scientific_name"]:
            species.setdefault(
                row["scientific_name"],
                (row["common_name"], row["genus"], row["family"]),
            )

    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT analysis_area_id FROM analysis_area
               WHERE source_area_code = '2GMEL' AND source_year = 2026
               ORDER BY analysis_area_id DESC LIMIT 1"""
        )
        area = cursor.fetchone()
        if area is None:
            raise ValueError("Load the official Melbourne boundary before council trees")
        analysis_area_id = area["analysis_area_id"]

        cursor.executemany(
            """INSERT INTO species_profile (
                   scientific_name, common_name, genus, family, source_reference
               ) VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (scientific_name) DO UPDATE SET
                   common_name = COALESCE(species_profile.common_name, EXCLUDED.common_name),
                   genus = COALESCE(species_profile.genus, EXCLUDED.genus),
                   family = COALESCE(species_profile.family, EXCLUDED.family),
                   source_reference = COALESCE(
                       species_profile.source_reference, EXCLUDED.source_reference
                   )""",
            [
                (name, values[0], values[1], values[2], source.source_name)
                for name, values in species.items()
            ],
        )

        cursor.execute(
            """CREATE TEMP TABLE council_named_tree_stage (
                   source_tree_id TEXT, inventory_source_key TEXT,
                   municipality TEXT, common_name TEXT, scientific_name TEXT,
                   display_name TEXT, genus TEXT, family TEXT,
                   taxonomic_precision TEXT, diameter_breast_height_cm NUMERIC,
                   dbh_min_cm NUMERIC, dbh_max_cm NUMERIC, height_m NUMERIC,
                   height_min_m NUMERIC, height_max_m NUMERIC,
                   canopy_width_m NUMERIC, canopy_width_min_m NUMERIC,
                   canopy_width_max_m NUMERIC, canopy_width_ew_m NUMERIC,
                   canopy_width_ns_m NUMERIC, year_planted INTEGER,
                   date_planted DATE, age_description TEXT,
                   useful_life_expectancy TEXT,
                   useful_life_expectancy_years INTEGER, health_status TEXT,
                   structure_status TEXT, precinct TEXT, located_in TEXT,
                   address TEXT, source_observed_on DATE,
                   geometry_wkt TEXT, source_srid INTEGER
               ) ON COMMIT DROP"""
        )
        copy_sql = """COPY council_named_tree_stage (
            source_tree_id, inventory_source_key, municipality, common_name,
            scientific_name, display_name, genus, family, taxonomic_precision,
            diameter_breast_height_cm, dbh_min_cm, dbh_max_cm, height_m,
            height_min_m, height_max_m, canopy_width_m, canopy_width_min_m,
            canopy_width_max_m, canopy_width_ew_m, canopy_width_ns_m,
            year_planted, date_planted, age_description,
            useful_life_expectancy, useful_life_expectancy_years,
            health_status, structure_status, precinct, located_in, address,
            source_observed_on, geometry_wkt, source_srid
        ) FROM STDIN"""
        stage_columns = (
            "source_tree_id", "inventory_source_key", "municipality",
            "common_name", "scientific_name", "display_name", "genus", "family",
            "taxonomic_precision", "diameter_breast_height_cm", "dbh_min_cm",
            "dbh_max_cm", "height_m", "height_min_m", "height_max_m",
            "canopy_width_m", "canopy_width_min_m", "canopy_width_max_m",
            "canopy_width_ew_m", "canopy_width_ns_m", "year_planted",
            "date_planted", "age_description", "useful_life_expectancy",
            "useful_life_expectancy_years", "health_status", "structure_status",
            "precinct", "located_in", "address", "source_observed_on",
            "geometry_wkt", "source_srid",
        )
        with cursor.copy(copy_sql) as copy:
            for row in accepted_rows():
                copy.write_row(tuple(row[column] for column in stage_columns))

        cursor.execute(
            f"""WITH candidates AS MATERIALIZED (
                     SELECT stage.*,
                            ST_Transform(
                                ST_GeomFromText(stage.geometry_wkt, stage.source_srid),
                                {TARGET_SRID}
                            ) AS tree_location
                     FROM council_named_tree_stage AS stage
                 )
                 INSERT INTO named_tree_inventory (
                     dataset_version_id, source_tree_id, species_id,
                     inventory_source_key, municipality, common_name,
                     scientific_name, display_name, genus, family,
                     taxonomic_precision, diameter_breast_height_cm,
                     dbh_min_cm, dbh_max_cm, height_m, height_min_m, height_max_m,
                     canopy_width_m, canopy_width_min_m, canopy_width_max_m,
                     canopy_width_ew_m, canopy_width_ns_m, year_planted,
                     date_planted, age_description, useful_life_expectancy,
                     useful_life_expectancy_years, health_status,
                     structure_status, precinct, located_in, address,
                     source_observed_on, tree_location, quality_status
                 )
                 SELECT %s, candidate.source_tree_id, species.species_id,
                        candidate.inventory_source_key, candidate.municipality,
                        candidate.common_name, candidate.scientific_name,
                        candidate.display_name, candidate.genus, candidate.family,
                        candidate.taxonomic_precision,
                        candidate.diameter_breast_height_cm, candidate.dbh_min_cm,
                        candidate.dbh_max_cm, candidate.height_m,
                        candidate.height_min_m, candidate.height_max_m,
                        candidate.canopy_width_m, candidate.canopy_width_min_m,
                        candidate.canopy_width_max_m, candidate.canopy_width_ew_m,
                        candidate.canopy_width_ns_m, candidate.year_planted,
                        candidate.date_planted, candidate.age_description,
                        candidate.useful_life_expectancy,
                        candidate.useful_life_expectancy_years,
                        candidate.health_status, candidate.structure_status,
                        candidate.precinct, candidate.located_in,
                        candidate.address, candidate.source_observed_on,
                        candidate.tree_location, 'passed'
                 FROM candidates AS candidate
                 LEFT JOIN species_profile AS species
                   ON species.scientific_name = candidate.scientific_name
                 WHERE EXISTS (
                     SELECT 1 FROM analysis_area_tile AS tile
                     WHERE tile.analysis_area_id = %s
                       AND tile.tile_geometry && candidate.tree_location
                       AND ST_Covers(tile.tile_geometry, candidate.tree_location)
                 )""",
            (version_id, analysis_area_id),
        )
        written = cursor.rowcount
        boundary_excluded = report.passing_records - written
        cursor.execute(
            """UPDATE dataset_version
               SET integration_status = 'integrated',
                   publication_status = 'application_ready',
                   analysis_area_id = %s,
                   derivation_method = %s,
                   coverage_pass_rate = %s
               WHERE dataset_version_id = %s""",
            (
                analysis_area_id,
                f"{council_key}_inventory_filter_to_abs_2GMEL_2026_v1",
                round(100.0 * written / report.passing_records, 2)
                if report.passing_records else 0,
                version_id,
            ),
        )
        cursor.execute(
            """INSERT INTO data_limitation (
                   dataset_version_id, limitation_type, description,
                   affected_area, analytical_impact, mitigation
               ) VALUES
               (%s, 'public_council_trees_only', %s, %s, %s, %s),
               (%s, 'source_name_coverage', %s, %s, %s, %s)""",
            (
                version_id,
                "The inventory describes council-managed public trees, not every private or backyard tree.",
                source.municipality,
                "Absence from this inventory is not evidence that no tree exists.",
                "Keep property canopy and Vicmap observations separate and retain this limitation in user-visible output.",
                version_id,
                f"{unnamed_count} active source rows without a usable common, botanical or genus-level name were excluded; {inactive_count} inactive rows were excluded.",
                source.municipality,
                "Named-tree coverage is incomplete and differs between councils.",
                "Return Unavailable for missing names and report source-specific coverage.",
            ),
        )

    return {
        "rows_in": raw_count,
        "rows_active": raw_count - inactive_count,
        "rows_eligible": eligible_count,
        "rows_written": written,
        "rows_inactive_excluded": inactive_count,
        "rows_without_name_excluded": unnamed_count,
        "rows_quality_rejected": report.failing_records,
        "rows_outside_melbourne": boundary_excluded,
        "eligible_quality_pass_rate": report.pass_rate,
        "source_name_coverage_pct": round(
            100.0 * eligible_count / (raw_count - inactive_count), 2
        ) if raw_count > inactive_count else 0,
        "dataset_version_id": str(version_id),
        "raw_extract": str(raw_path),
        "message": f"{written} source-labelled {source.municipality} trees integrated",
    }


def _council_job(council_key: str) -> Job:
    return lambda connection, args: ingest_council_named_trees(
        connection, args, council_key
    )


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
    analytical_manifest = None
    if args.canopy_analytical:
        import rasterio

        if api_metadata:
            raise ValueError(
                "A rendered API extraction cannot be registered as an analytical GeoTIFF"
            )
        with rasterio.open(args.canopy_file) as analytical_source:
            validate_property_canopy_source(
                analytical_source, asset_role="canopy_analytical_geotiff"
            )
        analytical_manifest = analytical_canopy_manifest(args.canopy_file)
    aggregate_manifest = None
    if args.canopy_aggregate_file:
        aggregate_manifest_path = args.canopy_aggregate_file.with_suffix(
            args.canopy_aggregate_file.suffix + ".manifest.json"
        )
        if not aggregate_manifest_path.exists():
            raise FileNotFoundError(
                f"Prepared canopy aggregate requires manifest: {aggregate_manifest_path}"
            )
        aggregate_manifest = json.loads(
            aggregate_manifest_path.read_text(encoding="utf-8")
        )
        if not aggregate_manifest.get("complete"):
            raise ValueError("Prepared canopy aggregate is not complete")
        if aggregate_manifest.get("output_sha256") != sha256_file(args.canopy_aggregate_file):
            raise ValueError("Prepared canopy aggregate checksum does not match its manifest")
        if analytical_manifest and (
            aggregate_manifest.get("source_manifest_sha256")
            != sha256_file(Path(analytical_manifest["manifest_path"]))
        ):
            raise ValueError("Canopy aggregate was not produced from this analytical manifest")
        with gzip.open(args.canopy_aggregate_file, "rt", encoding="utf-8") as source:
            rows = [json.loads(line) for line in source if line.strip()]
        metadata = {
            **profile_canopy_raster(args.canopy_file),
            **aggregate_manifest,
        }
        if len(rows) != aggregate_manifest.get("output_rows"):
            raise ValueError("Prepared canopy aggregate row count does not match its manifest")
    else:
        rows, metadata = aggregate_canopy(
            args.canopy_file,
            observed_on=observed_on,
            bbox_wgs84=(
                analytical_manifest["boundary"]["boundary_wgs84_bounds"]
                if analytical_manifest else (144.4, -38.5, 146.0, -37.4)
            ),
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
        checksum=(sha256_file(args.canopy_aggregate_file)
                  if args.canopy_aggregate_file else
                  sha256_file(Path(analytical_manifest["manifest_path"]))
                  if analytical_manifest else sha256_file(args.canopy_file)),
        observed_from=observed_from,
        observed_to=observed_on,
        spatial_resolution_m=args.grid_size_m,
    )
    canopy_assets = [
        {
            "asset_role": (
                "canopy_api_tile_mosaic" if api_metadata
                else "canopy_analytical_geotiff" if args.canopy_analytical
                else "canopy_source_raster"
            ),
            "source_scene_id": args.canopy_file.stem,
            "source_href": (
                api_metadata.get("source_service") if api_metadata
                else analytical_manifest.get("datashare_url") if analytical_manifest
                else None
            ),
            "local_path": str(args.canopy_file.resolve()),
            "media_type": (
                "application/xml; subtype=gdal-vrt"
                if args.canopy_file.suffix.lower() == ".vrt"
                else "image/tiff; application=geotiff"
            ),
            "source_crs": metadata["crs"],
            "pixel_size_m": max(metadata["pixel_size"]),
            "checksum": sha256_file(args.canopy_file),
            "acquired_at": f"{observed_on.isoformat()}T00:00:00Z",
            "metadata": (
                {**metadata, "api_extraction": api_metadata} if api_metadata
                else {
                    **metadata,
                    "analytical_manifest": {
                        "path": analytical_manifest["manifest_path"],
                        "dataset_uuid": analytical_manifest["dataset_uuid"],
                        "selected_tile_count": len(analytical_manifest["selected_tiles"]),
                        "package_sha256": {
                            package["name"]: package["sha256"]
                            for package in analytical_manifest["packages"]
                        },
                    },
                } if analytical_manifest else metadata
            ),
        }
    ]
    if args.canopy_aggregate_file:
        canopy_assets.append({
            "asset_role": "canopy_500m_tilewise_aggregate",
            "source_scene_id": args.canopy_aggregate_file.stem,
            "source_href": analytical_manifest.get("datashare_url"),
            "local_path": str(args.canopy_aggregate_file.resolve()),
            "media_type": "application/x-ndjson+gzip",
            "source_crs": f"EPSG:{aggregate_manifest['target_srid']}",
            "pixel_size_m": aggregate_manifest["grid_size_m"],
            "checksum": sha256_file(args.canopy_aggregate_file),
            "acquired_at": aggregate_manifest["prepared_at"],
            "metadata": aggregate_manifest,
        })
    register_spatial_assets(
        connection,
        version_id,
        canopy_assets,
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


def ingest_city_canopy_history(connection, args: argparse.Namespace) -> dict[str, Any]:
    """Load one normalised City of Melbourne historical canopy snapshot."""

    year = args.city_canopy_year
    if year is None:
        raise ValueError(
            "city-canopy requires --city-canopy-year 2008, 2015, 2016 or 2021"
        )
    if args.city_canopy_file:
        if not args.city_canopy_file.exists():
            raise FileNotFoundError(args.city_canopy_file)
        raw_path = args.city_canopy_file
        raw_count = sum(
            1 for _ in limit_city_canopy_rows(
                read_city_canopy_raw(raw_path), args.max_city_canopy_records
            )
        )
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        raw_path = (
            ROOT / "data" / "raw" / "city_canopy" / str(year)
            / f"canopy_{year}_{stamp}.jsonl.gz"
        )
        downloaded_count = download_city_canopy(year, raw_path)
        raw_count = min(downloaded_count, args.max_city_canopy_records) \
            if args.max_city_canopy_records else downloaded_count

    def rows():
        return limit_city_canopy_rows(
            normalised_city_canopy_rows(raw_path, year),
            args.max_city_canopy_records,
        )

    rules, threshold = quality_configuration("canopy_snapshot_feature")
    report = validate_record_stream(
        "canopy_snapshot_feature", rows, rules, threshold_pct=threshold
    )
    registered_source_id = source_id(
        connection, CITY_CANOPY_SOURCE_NAMES[year], "City of Melbourne"
    )
    version_id = create_dataset_version(
        connection,
        registered_source_id=registered_source_id,
        row_count=raw_count,
        checksum=sha256_file(raw_path),
        observed_from=f"{year}-01-01",
        observed_to=f"{year}-12-31",
    )
    record_quality_run(connection, version_id, report)
    if not report.passed_gate:
        connection.commit()
        return {
            "rows_in": raw_count,
            "rows_written": 0,
            "rows_rejected": report.failing_records,
            "quality_pass_rate": report.pass_rate,
            "dataset_version_id": str(version_id),
            "message": "Historical canopy failed the 95% quality gate",
        }

    failed = set(report.failed_indices)
    with connection.cursor() as cursor:
        cursor.execute(
            """CREATE TEMP TABLE city_canopy_stage (
                   source_feature_key TEXT, observed_year SMALLINT,
                   observed_on DATE, geometry_wkt TEXT, source_srid INTEGER,
                   source_area_m2 NUMERIC, calculated_area_m2 NUMERIC,
                   source_area_difference_pct NUMERIC,
                   geometry_repaired BOOLEAN
               ) ON COMMIT DROP"""
        )
        with cursor.copy(
            """COPY city_canopy_stage (
                   source_feature_key, observed_year, observed_on, geometry_wkt,
                   source_srid, source_area_m2, calculated_area_m2,
                   source_area_difference_pct,
                   geometry_repaired
               ) FROM STDIN"""
        ) as copy:
            for index, row in enumerate(rows()):
                if index in failed:
                    continue
                copy.write_row(
                    (
                        row["source_feature_key"], row["observed_year"],
                        row["observed_on"], row["geometry_wkt"],
                        row["source_srid"], row["source_area_m2"],
                        row["calculated_area_m2"],
                        row["source_area_difference_pct"],
                        row["geometry_repaired"],
                    )
                )
        cursor.execute(
            f"""INSERT INTO canopy_snapshot_feature (
                    dataset_version_id, source_feature_key, observed_year,
                    observed_on, canopy_geometry, source_area_m2,
                    calculated_area_m2, source_area_difference_pct,
                    geometry_repaired, quality_status
                )
                SELECT %s, source_feature_key, observed_year, observed_on,
                       ST_Multi(ST_Transform(
                           ST_GeomFromText(geometry_wkt, source_srid),
                           {TARGET_SRID}
                       )),
                       source_area_m2, calculated_area_m2,
                       source_area_difference_pct,
                       geometry_repaired, 'passed'
                FROM city_canopy_stage""",
            (version_id,),
        )
        written = cursor.rowcount
        cursor.execute(
            """UPDATE dataset_version
               SET integration_status = 'integrated',
                   publication_status = 'internal',
                   quality_status = 'passed_with_limitations',
                   derivation_method = 'city_canopy_polygon_normalisation_v1'
               WHERE dataset_version_id = %s""",
            (version_id,),
        )
        cursor.execute(
            """INSERT INTO data_limitation (
                   dataset_version_id, limitation_type, description,
                   affected_area, analytical_impact, mitigation
               ) VALUES (%s, 'cross_year_method_difference', %s, %s, %s, %s)""",
            (
                version_id,
                "The City canopy snapshots do not all use the same capture and "
                "classification method: 2008, 2015 and 2016 use aerial imagery "
                "and LiDAR, while 2021 uses high-resolution multispectral imagery.",
                "City of Melbourne municipality",
                "Apparent cross-year canopy change can include mapping-method differences.",
                "Align both snapshots to one grid and complete temporal/spatial validation before creating ML labels.",
            ),
        )
        cursor.execute(
            """INSERT INTO data_limitation (
                   dataset_version_id, limitation_type, description,
                   affected_area, analytical_impact, mitigation
               ) VALUES (%s, 'year_only_observation_date', %s, %s, %s, %s)""",
            (
                version_id,
                f"The source identifies observation year {year}, not an exact acquisition day; 31 December is stored as a period-end convention.",
                "All snapshot features",
                "Do not interpret observed_on as an exact image acquisition date.",
                "Use observed_year for modelling and disclose the year-level temporal precision.",
            ),
        )

    return {
        "year": year,
        "rows_in": raw_count,
        "rows_written": written,
        "rows_rejected": report.failing_records,
        "geometry_repaired": sum(1 for row in rows() if row["geometry_repaired"]),
        "quality_pass_rate": report.pass_rate,
        "dataset_version_id": str(version_id),
        "raw_extract": str(raw_path),
        "publication_status": "internal",
        "message": "Snapshot loaded; cross-year training labels are not yet validated",
    }


def ingest_metropolitan_vegetation_change(
    connection, args: argparse.Namespace
) -> dict[str, Any]:
    """Load a DataShare SHP/GDB download of 2014-2018 vegetation change."""

    path = args.vegetation_change_file
    if path is None:
        raise ValueError(
            "vegetation-change requires --vegetation-change-file pointing to the "
            "SHP or GDB downloaded from the official DataShare order page"
        )
    if not path.exists():
        raise FileNotFoundError(path)
    raw_count = vegetation_change_feature_count(path)

    def rows():
        return normalised_vegetation_change_rows(path)

    rules, threshold = quality_configuration("metropolitan_vegetation_change_feature")
    report = validate_record_stream(
        "metropolitan_vegetation_change_feature", rows, rules,
        threshold_pct=threshold,
    )
    registered_source_id = source_id(
        connection, VEGETATION_CHANGE_SOURCE_NAME,
        "Victorian Government Department of Transport and Planning",
    )
    version_id = create_dataset_version(
        connection,
        registered_source_id=registered_source_id,
        row_count=raw_count,
        checksum=vegetation_change_source_checksum(path),
        observed_from="2014-01-01",
        observed_to="2018-12-31",
    )
    record_quality_run(connection, version_id, report)
    if not report.passed_gate:
        connection.commit()
        return {
            "rows_in": raw_count,
            "rows_written": 0,
            "rows_rejected": report.failing_records,
            "quality_pass_rate": report.pass_rate,
            "dataset_version_id": str(version_id),
            "message": "Vegetation change failed the 95% quality gate",
        }

    failed = set(report.failed_indices)
    with connection.cursor() as cursor:
        cursor.execute(
            """CREATE TEMP TABLE vegetation_change_stage (
                   source_feature_key TEXT, mesh_block_code TEXT,
                   observed_from DATE, observed_to DATE,
                   tree_change_pct_points NUMERIC,
                   shrub_change_pct_points NUMERIC,
                   grass_change_pct_points NUMERIC,
                   total_vegetation_change_pct_points NUMERIC,
                   geometry_wkt TEXT, source_srid INTEGER,
                   source_properties JSONB
               ) ON COMMIT DROP"""
        )
        with cursor.copy(
            """COPY vegetation_change_stage (
                   source_feature_key, mesh_block_code, observed_from, observed_to,
                   tree_change_pct_points, shrub_change_pct_points,
                   grass_change_pct_points, total_vegetation_change_pct_points,
                   geometry_wkt, source_srid, source_properties
               ) FROM STDIN"""
        ) as copy:
            for index, row in enumerate(rows()):
                if index in failed:
                    continue
                copy.write_row((
                    row["source_feature_key"], row["mesh_block_code"],
                    row["observed_from"], row["observed_to"],
                    row["tree_change_pct_points"], row["shrub_change_pct_points"],
                    row["grass_change_pct_points"],
                    row["total_vegetation_change_pct_points"],
                    row["geometry_wkt"], row["source_srid"],
                    json.dumps(row["source_properties"]),
                ))
        cursor.execute(
            f"""INSERT INTO metropolitan_vegetation_change_feature (
                    dataset_version_id, source_feature_key, mesh_block_code,
                    observed_from, observed_to, tree_change_pct_points,
                    shrub_change_pct_points, grass_change_pct_points,
                    total_vegetation_change_pct_points, change_geometry,
                    source_properties, quality_status
                )
                SELECT %s, source_feature_key, mesh_block_code, observed_from,
                       observed_to, tree_change_pct_points, shrub_change_pct_points,
                       grass_change_pct_points,
                       total_vegetation_change_pct_points,
                       ST_Multi(ST_Transform(
                           ST_GeomFromText(geometry_wkt, source_srid), {TARGET_SRID}
                       )), source_properties, 'passed'
                FROM vegetation_change_stage""",
            (version_id,),
        )
        written = cursor.rowcount
        cursor.execute(
            """UPDATE dataset_version
               SET integration_status = 'integrated', publication_status = 'internal',
                   quality_status = 'passed_with_limitations',
                   derivation_method = 'datavic_vegetation_change_normalisation_v1'
               WHERE dataset_version_id = %s""",
            (version_id,),
        )
        cursor.execute(
            """INSERT INTO data_limitation (
                   dataset_version_id, limitation_type, description,
                   affected_area, analytical_impact, mitigation
               ) VALUES (%s, 'source_download_and_grain', %s, %s, %s, %s)""",
            (
                version_id,
                "DataShare supplies an ordered spatial download rather than a direct feature API; polygons are based on 2016 ABS Mesh Blocks.",
                "Metropolitan Melbourne comparison extent",
                "Values describe area-level percentage-point change and cannot be treated as individual-tree or parcel observations.",
                "Keep the raw download checksum and align features to a common modelling grid before joining other years.",
            ),
        )
    return {
        "rows_in": raw_count,
        "rows_written": written,
        "rows_rejected": report.failing_records,
        "quality_pass_rate": report.pass_rate,
        "dataset_version_id": str(version_id),
        "message": f"{written} metropolitan vegetation-change features integrated",
    }


def ingest_austraits(connection, args: argparse.Namespace) -> dict[str, Any]:
    """Load the prototype-relevant subset of the versioned AusTraits release."""

    archive = args.austraits_file or (
        ROOT / "data" / "raw" / "austraits" / "austraits-7.0.0.zip"
    )
    if args.austraits_file is None:
        download_austraits(archive)
    elif not archive.exists():
        raise FileNotFoundError(archive)

    raw_count, selected_count = austraits_counts(archive)
    maximum = args.max_austraits_records

    def rows():
        return iter_austraits_rows(archive, maximum=maximum)

    rules, threshold = quality_configuration("plant_trait_observation")
    report = validate_record_stream(
        "plant_trait_observation", rows, rules, threshold_pct=threshold
    )
    registered_source_id = source_id(
        connection, AUSTRAITS_SOURCE_NAME, "AusTraits collaboration"
    )
    version_id = create_dataset_version(
        connection,
        registered_source_id=registered_source_id,
        row_count=raw_count,
        checksum=sha256_file(archive),
    )
    record_quality_run(connection, version_id, report)
    if not report.passed_gate:
        connection.commit()
        return {
            "rows_in": raw_count,
            "rows_selected": report.total_records,
            "rows_written": 0,
            "rows_rejected": report.failing_records,
            "quality_pass_rate": report.pass_rate,
            "dataset_version_id": str(version_id),
            "message": "AusTraits selected observations failed the 95% quality gate",
        }

    failed = set(report.failed_indices)
    with connection.cursor() as cursor:
        with cursor.copy(
            """COPY plant_trait_observation (
                   dataset_version_id, source_row_number, dataset_id,
                   observation_id, taxon_name, original_name, trait_name,
                   value_text, value_numeric, unit, entity_type, value_type,
                   basis_of_value, replicates, basis_of_record, life_stage,
                   location_id, collection_date, source_dataset_id,
                   measurement_remarks, quality_status
               ) FROM STDIN"""
        ) as copy:
            for index, row in enumerate(rows()):
                if index in failed:
                    continue
                copy.write_row((
                    version_id, row["source_row_number"], row["dataset_id"],
                    row["observation_id"], row["taxon_name"], row["original_name"],
                    row["trait_name"], row["value_text"], row["value_numeric"],
                    row["unit"], row["entity_type"], row["value_type"],
                    row["basis_of_value"], row["replicates"],
                    row["basis_of_record"], row["life_stage"], row["location_id"],
                    row["collection_date"], row["source_dataset_id"],
                    row["measurement_remarks"], "passed",
                ))
        written = report.passing_records
        cursor.execute(
            """UPDATE dataset_version
               SET integration_status = 'integrated', publication_status = 'internal',
                   quality_status = 'passed_with_limitations',
                   derivation_method = 'prototype_relevant_trait_filter_v1'
               WHERE dataset_version_id = %s""",
            (version_id,),
        )
        cursor.execute(
            """INSERT INTO data_limitation (
                   dataset_version_id, limitation_type, description,
                   affected_area, analytical_impact, mitigation
               ) VALUES (%s, 'trait_semantics', %s, %s, %s, %s)""",
            (
                version_id,
                "Only explicitly selected prototype-relevant traits are loaded from the full release.",
                "All AusTraits records used by GreenChanger",
                "Observed plant height and physiological water-use traits are not guaranteed mature dimensions, horticultural water-needs classes, root-risk ratings or allergen ratings.",
                "Retain source context and use traits only as optional research features until a horticultural contract and held-out model validation exist.",
            ),
        )
    return {
        "rows_in": raw_count,
        "rows_available_in_selected_traits": selected_count,
        "rows_assessed": report.total_records,
        "rows_written": written,
        "rows_rejected": report.failing_records,
        "quality_pass_rate": report.pass_rate,
        "dataset_version_id": str(version_id),
        "publication_status": "internal",
        "message": f"{written} AusTraits research observations integrated",
    }


def ingest_urban_growth(connection, args: argparse.Namespace) -> dict[str, Any]:
    """Load the seven-city tree-ring study and its separately usable climate data."""

    directory = args.urban_growth_directory or (
        ROOT / "data" / "raw" / "urban_tree_growth" / "figshare_28970981_v2"
    )
    if args.urban_growth_directory is None:
        paths = download_urban_growth(directory)
    else:
        paths = {
            name: directory / name
            for name in ("Raw_data_GCB.xlsx", "Climate_data_GCB.xlsx")
        }
        missing = [str(path) for path in paths.values() if not path.exists()]
        if missing:
            raise FileNotFoundError("Missing urban-growth workbook(s): " + ", ".join(missing))

    raw_growth = read_urban_growth_workbook(paths["Raw_data_GCB.xlsx"])
    raw_climate = read_urban_growth_workbook(paths["Climate_data_GCB.xlsx"])
    growth_rows = normalise_growth_rows(raw_growth)
    climate_rows = normalise_climate_rows(raw_climate)
    growth_rules, threshold = quality_configuration("urban_tree_growth_observation")
    climate_rules, _ = quality_configuration("urban_tree_growth_climate")
    growth_report = validate_records(
        "urban_tree_growth_observation", growth_rows, growth_rules,
        threshold_pct=threshold,
    )
    climate_report = validate_records(
        "urban_tree_growth_climate", climate_rows, climate_rules,
        threshold_pct=threshold,
    )
    registered_source_id = source_id(
        connection, URBAN_GROWTH_SOURCE_NAME, "Esperon-Rodriguez et al."
    )
    version_id = create_dataset_version(
        connection,
        registered_source_id=registered_source_id,
        row_count=len(raw_growth) + len(raw_climate),
        checksum=combined_checksum(paths.values()),
    )
    record_quality_run(connection, version_id, growth_report)
    record_quality_run(connection, version_id, climate_report)
    passed_gate = growth_report.passed_gate and climate_report.passed_gate
    if not passed_gate:
        with connection.cursor() as cursor:
            cursor.execute(
                """UPDATE dataset_version
                   SET quality_status = 'failed', integration_status = 'failed'
                   WHERE dataset_version_id = %s""",
                (version_id,),
            )
        connection.commit()
        return {
            "rows_in": len(raw_growth) + len(raw_climate),
            "rows_written": 0,
            "rows_rejected": growth_report.failing_records + climate_report.failing_records,
            "dataset_version_id": str(version_id),
            "message": "Urban tree growth evidence failed the 95% quality gate",
        }

    growth_failed = set(growth_report.failed_indices)
    climate_failed = set(climate_report.failed_indices)
    with connection.cursor() as cursor:
        with cursor.copy(
            """COPY urban_tree_growth_observation (
                   dataset_version_id, source_row_number, city,
                   species_name_original, species_name, tree_number,
                   ring_sequence, tree_ring_width_mm,
                   basal_area_increment_cm2_year, quality_status
               ) FROM STDIN"""
        ) as copy:
            for index, row in enumerate(growth_rows):
                if index not in growth_failed:
                    copy.write_row((
                        version_id, row["source_row_number"], row["city"],
                        row["species_name_original"], row["species_name"],
                        row["tree_number"], row["ring_sequence"],
                        row["tree_ring_width_mm"],
                        row["basal_area_increment_cm2_year"], "passed",
                    ))
        with cursor.copy(
            """COPY urban_tree_growth_climate (
                   dataset_version_id, source_row_number, city, observation_year,
                   variant_number, source_occurrence_count, city_year_ambiguous,
                   annual_precipitation_mm, precipitation_driest_month_mm,
                   precipitation_wettest_month_mm,
                   precipitation_driest_quarter_mm,
                   mean_temperature_warmest_month_c,
                   mean_annual_temperature_c,
                   mean_temperature_coldest_month_c,
                   isothermality_divided_by_100, precipitation_index,
                   quality_status
               ) FROM STDIN"""
        ) as copy:
            for index, row in enumerate(climate_rows):
                if index not in climate_failed:
                    copy.write_row((
                        version_id, row["source_row_number"], row["city"], row["year"],
                        row["variant_number"], row["source_occurrence_count"],
                        row["city_year_ambiguous"], row["AP"], row["PDM"], row["PWM"],
                        row["PDQ"], row["MTWM"], row["MAT"], row["MTCM"],
                        row["IDM"], row["IP"], "passed",
                    ))
        combined_total = growth_report.total_records + climate_report.total_records
        combined_passed = growth_report.passing_records + climate_report.passing_records
        combined_rate = round(combined_passed / combined_total * 100, 2)
        cursor.execute(
            """UPDATE dataset_version
               SET integration_status = 'integrated', publication_status = 'internal',
                   quality_status = 'passed_with_limitations', quality_pass_rate = %s,
                   derivation_method = 'figshare_v2_tree_ring_and_climate_normalisation_v1'
               WHERE dataset_version_id = %s""",
            (combined_rate, version_id),
        )
        limitations = [
            (
                "temporal_linkage",
                "The growth workbook has no calendar-year column; ring_sequence is source order within each tree, not tree age or year.",
                "Direct growth-to-climate joins",
                "Growth rings cannot be safely joined to the climate workbook by year.",
                "Obtain and validate ring calendar-year metadata before any temporal join.",
            ),
            (
                "source_conflict",
                "Exact climate duplicates are collapsed with occurrence counts; conflicting city-year variants are retained and flagged.",
                "Mildura climate records",
                "Ambiguous city-years are excluded from usable_urban_tree_growth_climate.",
                "Resolve conflicts against the study authors or source publication before use.",
            ),
            (
                "target_mismatch",
                "Tree-ring width and basal-area increment measure stem growth, not canopy area.",
                "Tree canopy growth modelling",
                "The source cannot directly produce 5- or 10-year canopy predictions.",
                "Fit and validate a separate species-aware allometric link with canopy observations.",
            ),
        ]
        cursor.executemany(
            """INSERT INTO data_limitation (
                   dataset_version_id, limitation_type, description,
                   affected_area, analytical_impact, mitigation
               ) VALUES (%s, %s, %s, %s, %s, %s)""",
            [(version_id, *row) for row in limitations],
        )

    ambiguous = sum(row["city_year_ambiguous"] for row in climate_rows)
    return {
        "rows_in": len(raw_growth) + len(raw_climate),
        "growth_rows_written": growth_report.passing_records,
        "climate_rows_written": climate_report.passing_records,
        "rows_written": growth_report.passing_records + climate_report.passing_records,
        "rows_rejected": growth_report.failing_records + climate_report.failing_records,
        "ambiguous_climate_variants_retained": ambiguous,
        "quality_pass_rate": combined_rate,
        "dataset_version_id": str(version_id),
        "publication_status": "internal",
        "message": "Australian urban-tree growth research evidence integrated",
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
    "city-canopy": ingest_city_canopy_history,
    "vegetation-change": ingest_metropolitan_vegetation_change,
    "austraits": ingest_austraits,
    "urban-growth": ingest_urban_growth,
    "heat": ingest_heat,
    "address": ingest_address,
    "property": ingest_property,
    "trees": ingest_trees,
    "named-trees": ingest_named_trees,
    "brimbank-trees": _council_job("brimbank"),
    "yarra-trees": _council_job("yarra"),
    "casey-trees": _council_job("casey"),
    "hobsons-bay-trees": _council_job("hobsons_bay"),
    "wyndham-trees": _council_job("wyndham"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jobs", nargs="*", choices=JOBS, default=["sources"])
    parser.add_argument(
        "--bom-url",
        help="Optional single official BOM feed override for diagnostics.",
    )
    parser.add_argument(
        "--bom-stations-file",
        type=Path,
        default=DEFAULT_STATION_REGISTRY,
        help="Versioned Melbourne BOM station registry.",
    )
    parser.add_argument("--cost-file", type=Path, default=DEFAULT_COST_FILE)
    parser.add_argument("--canopy-file", type=Path)
    parser.add_argument(
        "--city-canopy-year", type=int, choices=(2008, 2015, 2016, 2021),
        help="City of Melbourne historical canopy snapshot year.",
    )
    parser.add_argument(
        "--city-canopy-file", type=Path,
        help="Reuse a .jsonl or .jsonl.gz City of Melbourne canopy extract.",
    )
    parser.add_argument(
        "--max-city-canopy-records", type=int,
        help="Diagnostic record limit; omit for a complete production extract.",
    )
    parser.add_argument(
        "--vegetation-change-file", type=Path,
        help="Official DataShare SHP/GDB for metropolitan 2014-2018 vegetation change.",
    )
    parser.add_argument(
        "--austraits-file", type=Path,
        help="Reuse the official austraits-7.0.0.zip release archive.",
    )
    parser.add_argument(
        "--max-austraits-records", type=int,
        help="Diagnostic limit after relevant-trait filtering; omit in production.",
    )
    parser.add_argument(
        "--urban-growth-directory", type=Path,
        help="Directory containing Raw_data_GCB.xlsx and Climate_data_GCB.xlsx.",
    )
    parser.add_argument(
        "--canopy-aggregate-file", type=Path,
        help="Completed .jsonl.gz from aggregate_vicmap_tree_extent.py.",
    )
    parser.add_argument(
        "--canopy-analytical", action="store_true",
        help="Register a verified <=2 m single-band analytical GeoTIFF for property canopy.",
    )
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
        "--city-tree-file", type=Path,
        help="Reuse a gzip City of Melbourne named-tree JSONL extract.",
    )
    parser.add_argument(
        "--council-tree-file", type=Path,
        help="Reuse one downloaded council spatial file; use with one council-tree job.",
    )
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
