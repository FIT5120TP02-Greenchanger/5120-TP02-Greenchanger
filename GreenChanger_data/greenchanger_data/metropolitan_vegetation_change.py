"""Normalise the official metropolitan vegetation-change spatial download."""

from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
import re
from typing import Any, Iterator

from pyogrio import read_dataframe, read_info
from shapely import make_valid, normalize
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon


SOURCE_NAME = "Change in Vegetation Cover in Metropolitan Melbourne between 2014 and 2018"
SOURCE_URL = (
    "https://discover.data.vic.gov.au/dataset/"
    "change-in-vegetation-cover-in-metropolitan-melbourne-between-2014-and-2018"
)
TARGET_SRID = 7855
READ_BATCH_SIZE = 5_000

FIELD_ALIASES = {
    "mesh_block_code": (
        "mesh_block_code", "meshblock", "mb_code16", "mb_code_16", "mb_code",
    ),
    "tree_change_pct_points": (
        "pp_anytree",
        "tree_change", "tree_chg", "tree_pct_change", "tree_change_pct",
        "tree_cover_change", "treechange",
    ),
    "shrub_change_pct_points": (
        "pp_shrub",
        "shrub_change", "shrub_chg", "shrub_pct_change", "shrub_change_pct",
        "shrub_cover_change", "shrubchange",
    ),
    "grass_change_pct_points": (
        "pp_grass",
        "grass_change", "grass_chg", "grass_pct_change", "grass_change_pct",
        "grass_cover_change", "grasschange",
    ),
    "total_vegetation_change_pct_points": (
        "pp_anyveg",
        "vegetation_change", "veg_change", "total_change", "total_veg_change",
        "vegetation_change_pct", "vegchange",
    ),
}

SOURCE_FEATURE_KEY_ALIASES = ("mmb_code",)


def _key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _value(properties: dict[str, Any], aliases: tuple[str, ...]):
    indexed = {_key(name): value for name, value in properties.items()}
    for alias in aliases:
        if _key(alias) in indexed:
            return indexed[_key(alias)]
    return None


def _number(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _polygonal(geometry):
    if geometry is None or geometry.is_empty:
        return None, False
    repaired = not geometry.is_valid
    geometry = make_valid(geometry) if repaired else geometry
    if isinstance(geometry, Polygon):
        geometry = MultiPolygon([geometry])
    elif isinstance(geometry, GeometryCollection):
        polygons = [part for part in geometry.geoms if isinstance(part, Polygon)]
        groups = [part for part in geometry.geoms if isinstance(part, MultiPolygon)]
        flattened = polygons + [part for group in groups for part in group.geoms]
        geometry = MultiPolygon(flattened) if flattened else None
    if not isinstance(geometry, MultiPolygon) or geometry.is_empty:
        return None, repaired
    return normalize(geometry), repaired


def _json_value(value: Any):
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def normalise_feature(properties: dict[str, Any], geometry) -> dict[str, Any]:
    """Map one EPSG:7855 feature to a stable cross-source database contract."""

    geometry, repaired = _polygonal(geometry)
    mesh_block = _value(properties, FIELD_ALIASES["mesh_block_code"])
    modified_mesh_block = _value(properties, SOURCE_FEATURE_KEY_ALIASES)
    unique_id = _value(properties, ("uniqueid", "unique_id"))
    feature_key = (
        f"{str(modified_mesh_block).strip()}:{str(unique_id).strip()}"
        if modified_mesh_block not in (None, "")
        and unique_id not in (None, "") else None
    )
    if feature_key is None and geometry is not None:
        feature_key = sha256(geometry.wkb).hexdigest()
    row = {
        "source_feature_key": feature_key,
        "mesh_block_code": str(mesh_block).strip() if mesh_block not in (None, "") else None,
        "observed_from": "2014-01-01",
        "observed_to": "2018-12-31",
        "geometry_wkt": geometry.wkt if geometry is not None else None,
        "source_srid": TARGET_SRID,
        "geometry_repaired": repaired,
        "source_properties": {
            str(name): _json_value(value) for name, value in properties.items()
        },
    }
    for field in (
        "tree_change_pct_points", "shrub_change_pct_points",
        "grass_change_pct_points", "total_vegetation_change_pct_points",
    ):
        row[field] = _number(_value(properties, FIELD_ALIASES[field]))
    row["has_change_measure"] = any(
        row[field] is not None for field in (
            "tree_change_pct_points", "shrub_change_pct_points",
            "grass_change_pct_points", "total_vegetation_change_pct_points",
        )
    )
    return row


def feature_count(path: Path) -> int:
    """Return the vector feature count without loading all geometries."""

    return int(read_info(path)["features"])


def source_checksum(path: Path) -> str:
    """Checksum one vector file or all files in an extracted geodatabase."""

    digest = sha256()
    if path.is_file() and path.suffix.lower() == ".shp":
        paths = sorted(path.parent.glob(f"{path.stem}.*"))
    elif path.is_file():
        paths = [path]
    else:
        paths = sorted(
            item for item in path.rglob("*") if item.is_file()
        )
    if not paths:
        raise ValueError(f"No source files found at {path}")
    for item in paths:
        relative = item.name if path.is_file() else str(item.relative_to(path))
        digest.update(relative.encode("utf-8"))
        with item.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def normalised_rows(
    path: Path, *, batch_size: int = READ_BATCH_SIZE
) -> Iterator[dict[str, Any]]:
    """Read bounded vector batches and yield EPSG:7855 records."""

    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    total = feature_count(path)
    for offset in range(0, total, batch_size):
        frame = read_dataframe(
            path, skip_features=offset, max_features=batch_size,
        )
        if frame.crs is None:
            raise ValueError(
                "Vegetation-change source has no declared coordinate system"
            )
        frame = frame.to_crs(epsg=TARGET_SRID)
        geometry_name = frame.geometry.name
        for _, source_row in frame.iterrows():
            properties = {
                str(name): value for name, value in source_row.items()
                if name != geometry_name
            }
            yield normalise_feature(properties, source_row.geometry)
