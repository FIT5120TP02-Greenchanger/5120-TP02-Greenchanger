"""Download and normalise City of Melbourne historical canopy polygons."""

from __future__ import annotations

import gzip
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable, Iterator
from urllib.request import urlopen

from pyproj import Transformer
from shapely import make_valid, normalize, transform
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, shape


SUPPORTED_YEARS = (2008, 2015, 2016, 2021)
DATASET_IDS = {
    2008: "tree-canopies-2008-urban-forest",
    2015: "tree-canopies-2015-urban-forest",
    2016: "tree-canopies-2016-urban-forest",
    2021: "tree-canopies-2021-urban-forest",
}
SOURCE_NAMES = {
    year: f"Tree Canopies {year} (Urban Forest)" for year in SUPPORTED_YEARS
}
EXPORT_URL = (
    "https://data.melbourne.vic.gov.au/api/explore/v2.1/catalog/datasets/"
    "{dataset_id}/exports/jsonl"
)
WGS84_TO_GDA2020_MGA55 = Transformer.from_crs(4326, 7855, always_xy=True)


def download(year: int, output_path: Path) -> int:
    """Stream an official JSON-lines export to a reproducible gzip raw file."""

    if year not in DATASET_IDS:
        raise ValueError(f"Unsupported canopy year: {year}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    url = EXPORT_URL.format(dataset_id=DATASET_IDS[year])
    with urlopen(url, timeout=120) as response, gzip.open(
        output_path, "wt", encoding="utf-8", newline="\n"
    ) as output:
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line:
                continue
            # Parse before saving so an HTML/error response cannot become raw data.
            json.loads(line)
            output.write(line)
            output.write("\n")
            count += 1
    if count == 0:
        raise ValueError(f"City of Melbourne canopy {year} API returned no rows")
    return count


def read_raw(path: Path) -> Iterator[dict[str, Any]]:
    """Read either a gzip JSON-lines extract or an uncompressed JSON-lines file."""

    opener = gzip.open if path.suffix.lower() == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as source:
        for line in source:
            if line.strip():
                yield json.loads(line)


def _polygonal_geometry(value: Any):
    if not isinstance(value, dict):
        return None, False
    geometry_value = value.get("geometry", value)
    try:
        original = shape(geometry_value)
    except (TypeError, ValueError):
        return None, False
    if original.is_empty:
        return None, False
    repaired = not original.is_valid
    geometry = make_valid(original) if repaired else original
    if isinstance(geometry, Polygon):
        geometry = MultiPolygon([geometry])
    elif isinstance(geometry, GeometryCollection):
        polygons = [part for part in geometry.geoms if isinstance(part, Polygon)]
        multipolygons = [part for part in geometry.geoms if isinstance(part, MultiPolygon)]
        flattened = polygons + [p for group in multipolygons for p in group.geoms]
        geometry = MultiPolygon(flattened) if flattened else None
    if not isinstance(geometry, MultiPolygon) or geometry.is_empty:
        return None, repaired
    return normalize(geometry), repaired


def normalise_record(record: dict[str, Any], year: int) -> dict[str, Any]:
    """Create one common record contract for all supported snapshot schemas."""

    if year not in SUPPORTED_YEARS:
        raise ValueError(f"Unsupported canopy year: {year}")
    geometry, repaired = _polygonal_geometry(record.get("geo_shape"))
    source_area = next(
        (record.get(field) for field in ("area", "shape_area", "shape__area")
         if record.get(field) not in (None, "")),
        None,
    )
    try:
        source_area = float(source_area) if source_area not in (None, "") else None
    except (TypeError, ValueError):
        source_area = None
    if geometry is None:
        return {
            "source_feature_key": None,
            "observed_year": year,
            "observed_on": f"{year}-12-31",
            "geometry_wkt": None,
            "source_srid": 4326,
            "calculated_area_m2": None,
            "source_area_m2": source_area,
            "source_area_difference_pct": None,
            "geometry_repaired": repaired,
        }
    metric_geometry = transform(
        geometry, WGS84_TO_GDA2020_MGA55.transform, interleaved=False
    )
    calculated_area = float(metric_geometry.area)
    area_difference_pct = (
        abs(source_area - calculated_area) / calculated_area * 100
        if source_area is not None and calculated_area > 0 else None
    )
    return {
        # Neither source exposes a durable polygon ID, so use canonical geometry.
        "source_feature_key": sha256(geometry.wkb).hexdigest(),
        "observed_year": year,
        "observed_on": f"{year}-12-31",
        "geometry_wkt": geometry.wkt,
        "source_srid": 4326,
        "calculated_area_m2": calculated_area,
        "source_area_m2": source_area,
        "source_area_difference_pct": area_difference_pct,
        "geometry_repaired": repaired,
    }


def normalised_rows(path: Path, year: int) -> Iterator[dict[str, Any]]:
    for record in read_raw(path):
        yield normalise_record(record, year)


def limited(records: Iterable[dict[str, Any]], maximum: int | None):
    """Limit records for diagnostics without changing the production default."""

    for index, record in enumerate(records):
        if maximum is not None and index >= maximum:
            break
        yield record
