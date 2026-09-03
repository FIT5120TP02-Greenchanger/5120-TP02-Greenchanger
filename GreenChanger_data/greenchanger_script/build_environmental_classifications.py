"""Activate Melbourne canopy thresholds and fixed temperature display bands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_script import db  # noqa: E402


def current_status(connection, scheme_id=None) -> dict:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT classification_scheme_id, metric_code,
                   source_dataset_version_id, lower_threshold,
                   upper_threshold, unit, sample_count, version_label,
                   classification_scope, explanation
            FROM current_environmental_classification_threshold
            WHERE (%s::UUID IS NULL OR classification_scheme_id = %s::UUID)
            ORDER BY metric_code
            """,
            (scheme_id, scheme_id),
        )
        thresholds = cursor.fetchall()
        cursor.execute(
            """
            SELECT 'heat' AS metric_code,
                   classify_environmental_value(
                       'heat', baseline_surface_temperature_c
                   ) AS classification,
                   COUNT(*) AS cell_count
            FROM latest_greater_melbourne_heat_baseline
            GROUP BY classification
            UNION ALL
            SELECT 'canopy' AS metric_code,
                   classify_environmental_value(
                       'canopy', canopy_percentage
                   ) AS classification,
                   COUNT(*) AS cell_count
            FROM latest_greater_melbourne_canopy_baseline
            GROUP BY classification
            ORDER BY metric_code, classification
            """
        )
        distribution = cursor.fetchall()
    if {row["metric_code"] for row in thresholds} != {"heat", "canopy"}:
        raise RuntimeError("active scheme does not contain both heat and canopy")
    return {
        "classification_scheme_id": str(thresholds[0]["classification_scheme_id"]),
        "version_label": thresholds[0]["version_label"],
        "method": "fixed_temperature_bands_with_canopy_terciles",
        "missing_value_label": "Unavailable",
        "thresholds": [dict(row) for row in thresholds],
        "classification_distribution": [dict(row) for row in distribution],
    }


def build(
    connection, version_label: str, *, require_analytical_canopy: bool = False
) -> dict:
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT source_type, source_is_proxy, dataset_version_id
               FROM latest_greater_melbourne_canopy_baseline LIMIT 1"""
        )
        canopy_source = cursor.fetchone()
        if canopy_source is None:
            raise RuntimeError("No application-ready Melbourne canopy baseline exists")
        if require_analytical_canopy and (
            canopy_source["source_type"] != "analytical_geotiff"
            or canopy_source["source_is_proxy"]
        ):
            raise RuntimeError(
                "Refusing to publish the requested scheme from the rendered canopy proxy"
            )
        cursor.execute(
            "SELECT refresh_environmental_classifications(%s) AS scheme_id",
            (version_label,),
        )
        scheme_id = cursor.fetchone()["scheme_id"]
        if canopy_source["source_type"] == "analytical_geotiff":
            cursor.execute(
                """UPDATE environmental_classification_threshold
                   SET explanation = %s
                   WHERE classification_scheme_id = %s AND metric_code = 'canopy'""",
                (
                    "Relative to application-ready Melbourne 500 m neighbourhood "
                    "canopy cells aggregated tile-wise from the official native "
                    "analytical Vicmap Tree Extent raster; source imagery spans "
                    "2013-2020 and is not a current field survey.",
                    scheme_id,
                ),
            )
    return current_status(connection, scheme_id)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print the active thresholds and classification distribution without writing.",
    )
    parser.add_argument(
        "--version-label",
        default="melbourne-terciles-v1",
        help="Unique label for this source-version-specific threshold scheme.",
    )
    parser.add_argument(
        "--require-analytical-canopy", action="store_true",
        help="Refuse to create the scheme while the rendered canopy proxy is current.",
    )
    parser.add_argument("--confirm-shared", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.status and not db.is_local() and not args.confirm_shared:
        sys.exit("Refusing to write shared Aurora without --confirm-shared")
    connection = db.connect()
    try:
        if args.status:
            result = current_status(connection)
            connection.rollback()
        else:
            result = build(
                connection, args.version_label,
                require_analytical_canopy=args.require_analytical_canopy,
            )
            connection.commit()
        print(json.dumps(result, indent=2, default=str))
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()
