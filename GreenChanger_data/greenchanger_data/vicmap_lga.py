"""Acquire and normalise authoritative Vicmap LGA polygons."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import time
from typing import Any, Iterator
from urllib import parse, request

from pyogrio import read_dataframe, read_info
from shapely import make_valid, normalize
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, shape


LGA_LAYER_URL = (
    "https://services-ap1.arcgis.com/P744lA0wf4LlBZ84/arcgis/rest/services/"
    "Vicmap_Admin/FeatureServer/9"
)
SOURCE_NAME = "Vicmap Admin - Local Government Area Polygon Aligned to Property"
PUBLISHER = "Department of Transport and Planning"
TARGET_SRID = 7855


def _polygonal(value):
    if value is None or value.is_empty:
        return None, False
    repaired = not value.is_valid
    value = make_valid(value) if repaired else value
    if isinstance(value, Polygon):
        value = MultiPolygon([value])
    elif isinstance(value, GeometryCollection):
        polygons = [part for part in value.geoms if isinstance(part, Polygon)]
        groups = [part for part in value.geoms if isinstance(part, MultiPolygon)]
        flattened = polygons + [part for group in groups for part in group.geoms]
        value = MultiPolygon(flattened) if flattened else None
    if not isinstance(value, MultiPolygon) or value.is_empty:
        return None, repaired
    return normalize(value), repaired


def _property(properties: dict[str, Any], name: str):
    wanted = name.casefold()
    return next(
        (value for key, value in properties.items() if str(key).casefold() == wanted),
        None,
    )


def normalise_feature(properties: dict[str, Any], geometry, source_srid: int) -> dict[str, Any]:
    """Map one LGA feature to the GreenChanger boundary contract."""

    geometry, repaired = _polygonal(geometry)
    lga_code = str(_property(properties, "lga_code") or "").strip() or None
    lga_name = str(_property(properties, "lga_name") or "").strip() or None
    official_name = str(_property(properties, "lga_official_name") or "").strip() or lga_name
    abs_code = str(_property(properties, "abs_lga_code") or "").strip() or None
    return {
        "source_feature_id": str(_property(properties, "ufi") or lga_code or "").strip() or None,
        "lga_code": lga_code,
        "lga_name": lga_name,
        "lga_official_name": official_name,
        "abs_lga_code": abs_code,
        "gazettal_registration": str(
            _property(properties, "gazettal_registration") or ""
        ).strip() or None,
        "geometry_wkt": geometry.wkt if geometry is not None else None,
        "source_srid": source_srid,
        "geometry_repaired": repaired,
    }


def fetch_document(*, retries: int = 4) -> dict[str, Any]:
    """Download every current LGA feature from the official ArcGIS layer."""

    parameters = {
        "where": "1=1",
        "outFields": (
            "OBJECTID,ufi,lga_code,lga_name,lga_official_name,"
            "gazettal_registration,abs_lga_code"
        ),
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    }
    url = f"{LGA_LAYER_URL}/query?{parse.urlencode(parameters)}"
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            req = request.Request(url, headers={"User-Agent": "GreenChanger-data/1.0"})
            with request.urlopen(req, timeout=180) as response:
                document = json.load(response)
            if not document.get("features"):
                raise ValueError("Vicmap LGA service returned no features")
            return document
        except Exception as error:
            last_error = error
            if attempt + 1 < retries:
                time.sleep(2**attempt)
    raise RuntimeError("Vicmap LGA request failed after retries") from last_error


def save_raw(document: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial = output_path.with_suffix(output_path.suffix + ".partial")
    partial.write_text(json.dumps(document, indent=2), encoding="utf-8")
    partial.replace(output_path)


def rows_from_document(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        normalise_feature(
            feature.get("properties") or {},
            shape(feature.get("geometry") or {}),
            4326,
        )
        for feature in document.get("features", [])
    ]


def rows_from_file(path: Path) -> Iterator[dict[str, Any]]:
    """Read an official SHP/GDB/GeoPackage download in bounded batches."""

    total = int(read_info(path)["features"])
    for offset in range(0, total, 500):
        frame = read_dataframe(path, skip_features=offset, max_features=500)
        if frame.crs is None:
            raise ValueError("Vicmap LGA source has no declared coordinate system")
        frame = frame.to_crs(epsg=TARGET_SRID)
        geometry_name = frame.geometry.name
        for _, source_row in frame.iterrows():
            properties = {
                str(name): value
                for name, value in source_row.items()
                if name != geometry_name
            }
            yield normalise_feature(properties, source_row.geometry, TARGET_SRID)


def source_checksum(path: Path) -> str:
    """Hash a file, shapefile sidecars, or every file in a geodatabase."""

    if path.is_file() and path.suffix.lower() == ".shp":
        paths = sorted(path.parent.glob(f"{path.stem}.*"))
    elif path.is_file():
        paths = [path]
    else:
        paths = sorted(item for item in path.rglob("*") if item.is_file())
    if not paths:
        raise ValueError(f"No source files found at {path}")
    digest = sha256()
    for item in paths:
        digest.update(str(item.relative_to(path) if path.is_dir() else item.name).encode())
        with item.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()
