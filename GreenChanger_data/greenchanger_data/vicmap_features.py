"""Extract and normalise Vicmap Address and Property ArcGIS features."""

from __future__ import annotations

from datetime import datetime, timezone
import gzip
import json
import math
from pathlib import Path
import time
from typing import Any, Callable, Iterable, Iterator, Sequence
from urllib import parse, request

from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.validation import make_valid

from greenchanger_data.canopy import DEFAULT_MELBOURNE_BBOX


ADDRESS_LAYER_URL = (
    "https://services-ap1.arcgis.com/P744lA0wf4LlBZ84/arcgis/rest/services/"
    "Vicmap_Address/FeatureServer/0"
)
PROPERTY_LAYER_URL = (
    "https://services-ap1.arcgis.com/P744lA0wf4LlBZ84/ArcGIS/rest/services/"
    "Vicmap_Property/FeatureServer/0"
)
TREE_URBAN_LAYER_URL = (
    "https://services-ap1.arcgis.com/P744lA0wf4LlBZ84/ArcGIS/rest/services/"
    "Vicmap_Vegetation_Tree_Urban/FeatureServer/0"
)

ADDRESS_FIELDS = (
    "OBJECTID,pfi,property_pfi,ezi_address,locality_name,postcode,lga_code,"
    "is_primary,address_class"
)
PROPERTY_FIELDS = (
    "OBJECTID,prop_pfi,prop_lga_code,prop_propnum,prop_property_type,"
    "prop_status,Shape__Area"
)
TREE_URBAN_FIELDS = (
    "OBJECTID,ufi,feature_type,feature_subtype,canopy_radius_m,height_m,"
    "dense_canopy,source_begin_date,source_end_date"
)


def _post_json(url: str, parameters: dict[str, Any], *, retries: int = 4) -> dict[str, Any]:
    """POST an ArcGIS query with retry/backoff and return decoded JSON."""

    payload = parse.urlencode(parameters).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            req = request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "GreenChanger-data/1.0",
                },
            )
            with request.urlopen(req, timeout=120) as response:
                result = json.load(response)
            if "error" in result:
                raise RuntimeError(f"ArcGIS error: {result['error']}")
            return result
        except Exception as error:  # network services can fail transiently
            last_error = error
            if attempt + 1 < retries:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Vicmap request failed after {retries} attempts") from last_error


def layer_metadata(layer_url: str) -> dict[str, Any]:
    return _post_json(layer_url, {"f": "json"})


def _tiles(
    bbox: Sequence[float], tile_degrees: float
) -> Iterator[tuple[float, float, float, float]]:
    west, south, east, north = map(float, bbox)
    x_count = math.ceil((east - west) / tile_degrees)
    y_count = math.ceil((north - south) / tile_degrees)
    for x_index in range(x_count):
        xmin = west + x_index * tile_degrees
        xmax = min(east, xmin + tile_degrees)
        for y_index in range(y_count):
            ymin = south + y_index * tile_degrees
            ymax = min(north, ymin + tile_degrees)
            yield xmin, ymin, xmax, ymax


def _subdivide(
    bbox: tuple[float, float, float, float]
) -> tuple[tuple[float, float, float, float], ...]:
    west, south, east, north = bbox
    middle_x = (west + east) / 2
    middle_y = (south + north) / 2
    return (
        (west, south, middle_x, middle_y),
        (middle_x, south, east, middle_y),
        (west, middle_y, middle_x, north),
        (middle_x, middle_y, east, north),
    )


def _query_tile(
    layer_url: str,
    fields: str,
    bbox: tuple[float, float, float, float],
    *,
    record_limit: int,
    offset: int | None = None,
) -> dict[str, Any]:
    parameters = {
            "where": "1=1",
            "geometry": ",".join(str(value) for value in bbox),
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": fields,
            "outSR": "4326",
            "returnGeometry": "true",
            "returnZ": "false",
            "returnM": "false",
            "resultRecordCount": str(record_limit),
            "f": "geojson",
    }
    if offset is not None:
        parameters["resultOffset"] = str(offset)
        parameters["orderByFields"] = "OBJECTID"
    return _post_json(f"{layer_url}/query", parameters)


def iter_melbourne_features(
    layer_url: str,
    fields: str,
    *,
    bbox: Sequence[float] = DEFAULT_MELBOURNE_BBOX,
    tile_degrees: float = 0.1,
    minimum_tile_degrees: float = 0.0015625,
    record_limit: int = 2_000,
    progress: Callable[[int, int], None] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield complete, deduplicated features using adaptive spatial tiles.

    ArcGIS caps responses at 2,000 records. Any tile that reaches that cap is
    recursively divided, avoiding offset pagination over a changing weekly
    source. Polygon features crossing tile edges are deduplicated by OBJECTID.
    """

    pending = list(reversed(list(_tiles(bbox, tile_degrees))))
    seen_object_ids: set[Any] = set()
    queried = 0
    yielded = 0
    while pending:
        tile = pending.pop()
        result = _query_tile(layer_url, fields, tile, record_limit=record_limit)
        queried += 1
        features = result.get("features", [])
        exceeded = bool(result.get("properties", {}).get("exceededTransferLimit"))
        width = tile[2] - tile[0]
        height = tile[3] - tile[1]
        if exceeded:
            if min(width, height) <= minimum_tile_degrees:
                # Thousands of apartment/unit addresses can share effectively
                # one coordinate, so spatial subdivision eventually cannot
                # reduce a tile. Use stable OBJECTID pagination only here.
                offset = 0
                while True:
                    page = _query_tile(
                        layer_url, fields, tile,
                        record_limit=record_limit, offset=offset,
                    )
                    queried += 1
                    page_features = page.get("features", [])
                    for feature in page_features:
                        properties = feature.get("properties") or {}
                        object_id = properties.get("OBJECTID", feature.get("id"))
                        if object_id in seen_object_ids:
                            continue
                        seen_object_ids.add(object_id)
                        yielded += 1
                        yield feature
                    if not page.get("properties", {}).get("exceededTransferLimit"):
                        break
                    if not page_features:
                        raise RuntimeError(f"Vicmap pagination made no progress for {tile}")
                    offset += len(page_features)
                continue
            pending.extend(reversed(_subdivide(tile)))
            continue

        for feature in features:
            properties = feature.get("properties") or {}
            object_id = properties.get("OBJECTID", feature.get("id"))
            if object_id in seen_object_ids:
                continue
            seen_object_ids.add(object_id)
            yielded += 1
            yield feature
        if progress and queried % 50 == 0:
            progress(queried, yielded)


def _polygonal_geometry(geometry: dict[str, Any]):
    value = make_valid(shape(geometry))
    if isinstance(value, Polygon):
        return MultiPolygon([value])
    if isinstance(value, MultiPolygon):
        return value
    polygons = [part for part in getattr(value, "geoms", ()) if isinstance(part, Polygon)]
    if not polygons:
        return None
    return MultiPolygon(polygons)


def normalise_address(feature: dict[str, Any]) -> dict[str, Any]:
    properties = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates") or []
    geometry_wkt = None
    if geometry.get("type") == "Point" and len(coordinates) >= 2:
        geometry_wkt = f"POINT ({float(coordinates[0])} {float(coordinates[1])})"
    return {
        "source_address_id": str(properties.get("pfi") or "").strip() or None,
        "source_property_id": str(properties.get("property_pfi") or "").strip() or None,
        "full_address": str(properties.get("ezi_address") or "").strip() or None,
        "locality_name": str(properties.get("locality_name") or "").strip() or None,
        "postcode": str(properties.get("postcode") or "").strip() or None,
        "lga_code": str(properties.get("lga_code") or "").strip() or None,
        "is_primary": str(properties.get("is_primary") or "").strip() or None,
        "address_class": str(properties.get("address_class") or "").strip() or None,
        "geometry_wkt": geometry_wkt,
        "source_srid": 4326,
    }


def normalise_property(feature: dict[str, Any]) -> dict[str, Any]:
    properties = feature.get("properties") or {}
    geometry = feature.get("geometry")
    polygon = _polygonal_geometry(geometry) if geometry else None
    raw_area = properties.get("Shape__Area")
    return {
        "source_parcel_id": str(properties.get("prop_pfi") or "").strip() or None,
        "property_number": str(properties.get("prop_propnum") or "").strip() or None,
        "property_type": str(properties.get("prop_property_type") or "").strip() or None,
        "property_status": str(properties.get("prop_status") or "").strip() or None,
        "lga_code": str(properties.get("prop_lga_code") or "").strip() or None,
        "parcel_area_m2": float(raw_area) if raw_area not in (None, "") else None,
        "geometry_wkt": polygon.wkt if polygon is not None and not polygon.is_empty else None,
        "source_srid": 4326,
    }


def normalise_urban_tree(feature: dict[str, Any]) -> dict[str, Any]:
    """Normalise one official mapped-tree point without inventing accuracy."""

    properties = feature.get("properties") or {}
    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates") or []
    geometry_wkt = None
    if geometry.get("type") == "Point" and len(coordinates) >= 2:
        geometry_wkt = f"POINT ({float(coordinates[0])} {float(coordinates[1])})"

    def plausible_number(name: str, minimum: float, maximum: float) -> float | None:
        value = properties.get(name)
        if value in (None, ""):
            return None
        number = float(value)
        return number if minimum <= number <= maximum else None

    return {
        "source_tree_id": str(properties.get("ufi") or "").strip() or None,
        "feature_type": str(properties.get("feature_type") or "").strip() or None,
        "feature_subtype": str(properties.get("feature_subtype") or "").strip() or None,
        # Optional machine-derived dimensions outside conservative physical
        # plausibility bounds are suppressed, while the mapped point remains.
        "canopy_radius_m": plausible_number("canopy_radius_m", 0.25, 50.0),
        "height_m": plausible_number("height_m", 0.5, 100.0),
        "dense_canopy": str(properties.get("dense_canopy") or "").strip() or None,
        "source_observed_from": properties.get("source_begin_date") or None,
        "source_observed_to": properties.get("source_end_date") or None,
        "geometry_wkt": geometry_wkt,
        "source_srid": 4326,
    }


def extract_to_jsonl(
    dataset_name: str,
    output_path: Path,
    *,
    bbox: Sequence[float] = DEFAULT_MELBOURNE_BBOX,
    tile_degrees: float = 0.1,
    minimum_tile_degrees: float = 0.0015625,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Extract one source into a reproducible gzip JSON Lines file."""

    configuration = {
        "address": (ADDRESS_LAYER_URL, ADDRESS_FIELDS, normalise_address),
        "property": (PROPERTY_LAYER_URL, PROPERTY_FIELDS, normalise_property),
        "urban_tree": (TREE_URBAN_LAYER_URL, TREE_URBAN_FIELDS, normalise_urban_tree),
    }
    try:
        layer_url, fields, normaliser = configuration[dataset_name]
    except KeyError as error:
        raise ValueError(f"Unsupported Vicmap dataset: {dataset_name}") from error

    metadata = layer_metadata(layer_url)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = output_path.with_suffix(output_path.suffix + ".partial")
    count = 0
    with gzip.open(partial_path, "wt", encoding="utf-8") as output:
        for feature in iter_melbourne_features(
            layer_url,
            fields,
            bbox=bbox,
            tile_degrees=tile_degrees,
            minimum_tile_degrees=minimum_tile_degrees,
            progress=progress,
        ):
            output.write(json.dumps(normaliser(feature), separators=(",", ":")) + "\n")
            count += 1
    partial_path.replace(output_path)

    last_edit_ms = (metadata.get("editingInfo") or {}).get("lastEditDate")
    last_edit = (
        datetime.fromtimestamp(last_edit_ms / 1000, timezone.utc).isoformat()
        if last_edit_ms else None
    )
    return {
        "dataset": dataset_name,
        "source_service": layer_url,
        "source_last_edited_at": last_edit,
        "bbox_wgs84": list(map(float, bbox)),
        "record_count": count,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "output_path": str(output_path.resolve()),
    }


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as source:
        for line in source:
            if line.strip():
                yield json.loads(line)
