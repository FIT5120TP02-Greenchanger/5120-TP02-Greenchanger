"""Download and normalise the official ABS Melbourne boundary."""

from __future__ import annotations

import json
from pathlib import Path
import time
from urllib import parse, request

from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.validation import make_valid


ABS_GCCSA_LAYER_URL = (
    "https://geo.abs.gov.au/arcgis/rest/services/ASGS2026/GCCSA/MapServer/0"
)
GREATER_MELBOURNE_CODE = "2GMEL"
# The ABS API's official GCCSA feature name. Keep this source value unchanged
# even though GreenChanger's user-facing scope is described as "Melbourne".
GREATER_MELBOURNE_NAME = "Greater Melbourne"
ASGS_EFFECTIVE_DATE = "2026-07-22"


def _polygonal_geometry(geometry: dict):
    value = make_valid(shape(geometry))
    if isinstance(value, Polygon):
        return MultiPolygon([value])
    if isinstance(value, MultiPolygon):
        return value
    polygons = [part for part in getattr(value, "geoms", ()) if isinstance(part, Polygon)]
    return MultiPolygon(polygons) if polygons else None


def fetch_greater_melbourne(*, retries: int = 4) -> dict:
    """Return the single official ASGS 2026 Melbourne feature."""

    parameters = {
        "where": f"GCCSA_CODE_2026='{GREATER_MELBOURNE_CODE}'",
        "outFields": "*",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    }
    url = f"{ABS_GCCSA_LAYER_URL}/query?{parse.urlencode(parameters)}"
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            req = request.Request(url, headers={"User-Agent": "GreenChanger-data/1.0"})
            with request.urlopen(req, timeout=120) as response:
                document = json.load(response)
            features = document.get("features", [])
            if len(features) != 1:
                raise ValueError(
                    f"Expected one {GREATER_MELBOURNE_CODE} feature, got {len(features)}"
                )
            return document
        except Exception as error:  # remote services can fail transiently
            last_error = error
            if attempt + 1 < retries:
                time.sleep(2**attempt)
    raise RuntimeError("ABS GCCSA request failed after retries") from last_error


def save_raw(document: dict, output_path: Path) -> None:
    """Atomically preserve the unmodified response from the ABS API."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial = output_path.with_suffix(output_path.suffix + ".partial")
    partial.write_text(json.dumps(document, indent=2), encoding="utf-8")
    partial.replace(output_path)


def normalise_greater_melbourne(document: dict) -> dict:
    """Convert the API feature to the project's analysis-area structure."""

    feature = document["features"][0]
    properties = feature.get("properties") or {}
    polygon = _polygonal_geometry(feature.get("geometry") or {})
    area_sqkm = properties.get("AREA_ALBERS_SQKM")
    return {
        "source_area_code": str(properties.get("GCCSA_CODE_2026") or "").strip() or None,
        "area_name": str(properties.get("GCCSA_NAME_2026") or "").strip() or None,
        "area_type": "ABS_GCCSA",
        "source_year": 2026,
        "source_area_sqkm": float(area_sqkm) if area_sqkm not in (None, "") else None,
        "area_m2": float(area_sqkm) * 1_000_000 if area_sqkm not in (None, "") else None,
        "geometry_wkt": polygon.wkt if polygon is not None and not polygon.is_empty else None,
        "source_srid": 4326,
        "change_flag": properties.get("CHANGE_FLAG_2026"),
        "change_label": properties.get("CHANGE_LABEL_2026"),
        "state_name": properties.get("STATE_NAME_2026"),
    }
