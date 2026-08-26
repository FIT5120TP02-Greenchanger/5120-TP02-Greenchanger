"""Official USGS Landsat surface-temperature discovery and processing."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Sequence
from urllib.request import Request, urlopen

from greenchanger_data.canopy import DEFAULT_MELBOURNE_BBOX


STAC_SEARCH_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
STAC_COLLECTION = "landsat-c2-l2"
SAS_TOKEN_URL = (
    "https://planetarycomputer.microsoft.com/api/sas/v1/token/landsat-c2-l2"
)
ST_SCALE = 0.00341802
ST_OFFSET_K = 149.0


def search_surface_temperature(
    *,
    bbox_wgs84: Sequence[float] = DEFAULT_MELBOURNE_BBOX,
    start: date | None = None,
    end: date | None = None,
    max_cloud_pct: float = 30.0,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Find recent official Landsat Collection 2 Level-2 ST scenes."""

    end = end or datetime.now(timezone.utc).date()
    start = start or end - timedelta(days=365)
    body = {
        "collections": [STAC_COLLECTION],
        "bbox": list(bbox_wgs84),
        "datetime": f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
        "limit": limit,
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }
    request = Request(
        STAC_SEARCH_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "GreenChanger/1.0"},
        method="POST",
    )
    with urlopen(request, timeout=60) as response:
        features = json.load(response).get("features", [])
    usable = [
        item
        for item in features
        if float(item.get("properties", {}).get("eo:cloud_cover", 101)) <= max_cloud_pct
        and "lwir11" in item.get("assets", {})
        and "qa_pixel" in item.get("assets", {})
    ]
    return usable


def planetary_computer_token() -> str:
    """Return a short-lived read token for the public Landsat mirror."""

    request = Request(SAS_TOKEN_URL, headers={"User-Agent": "GreenChanger/1.0"})
    with urlopen(request, timeout=60) as response:
        token = json.load(response).get("token")
    if not token:
        raise RuntimeError("Planetary Computer did not return a Landsat access token")
    return token


def signed_asset_href(href: str, token: str) -> str:
    """Attach a short-lived token without changing stored provenance URLs."""

    return f"{href}{'&' if '?' in href else '?'}{token}"


def choose_scenes(items: list[dict[str, Any]], *, max_scenes: int = 2) -> list[dict[str, Any]]:
    """Prefer newest Tier-1 scenes from distinct WRS footprints."""

    tier_one = [
        item for item in items
        if item.get("properties", {}).get("landsat:collection_category") == "T1"
    ]
    candidates = tier_one or items
    candidates.sort(
        key=lambda item: (
            item.get("properties", {}).get("datetime", ""),
            -float(item.get("properties", {}).get("eo:cloud_cover", 101)),
        ),
        reverse=True,
    )
    selected: list[dict[str, Any]] = []
    footprints: set[tuple[str, str]] = set()
    for item in candidates:
        properties = item.get("properties", {})
        footprint = (
            str(properties.get("landsat:wrs_path") or item["id"]),
            str(properties.get("landsat:wrs_row") or item["id"]),
        )
        if footprint in footprints:
            continue
        selected.append(item)
        footprints.add(footprint)
        if len(selected) >= max_scenes:
            break
    return selected


def is_tiff(path: Path) -> bool:
    """Check classic TIFF and BigTIFF byte signatures."""

    if not path.exists() or path.stat().st_size < 8:
        return False
    with path.open("rb") as source:
        signature = source.read(4)
    return signature in {b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"}


def download_asset(url: str, destination: Path) -> Path:
    """Download an immutable STAC asset unless it is already present."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    if is_tiff(destination):
        return destination
    request = Request(url, headers={"User-Agent": "GreenChanger/1.0"})
    temporary = destination.with_suffix(destination.suffix + ".part")
    with urlopen(request, timeout=180) as response, temporary.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
    if not is_tiff(temporary):
        preview = temporary.read_text(encoding="utf-8", errors="ignore")[:200]
        temporary.unlink(missing_ok=True)
        raise RuntimeError(
            "Raster download did not return a GeoTIFF. Response began: "
            f"{preview!r}"
        )
    temporary.replace(destination)
    return destination


def aggregate_surface_temperature(
    temperature_path: Path,
    qa_path: Path,
    *,
    item: dict[str, Any],
    bbox_wgs84: Sequence[float] = DEFAULT_MELBOURNE_BBOX,
    target_srid: int = 7855,
    grid_size_m: float = 500.0,
) -> list[dict[str, Any]]:
    """Cloud-mask, scale to Celsius and aggregate one Landsat scene."""

    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    from rasterio.windows import Window, from_bounds
    from rasterio.warp import reproject, transform_bounds
    from shapely.geometry import box

    properties = item["properties"]
    observed_at = properties["datetime"]
    observed_on = observed_at[:10]
    scene_id = item["id"]
    cloud_cover = float(properties.get("eo:cloud_cover", 0))

    with rasterio.open(temperature_path) as temperature_source, rasterio.open(qa_path) as qa_source:
        if temperature_source.crs is None or qa_source.crs is None:
            raise ValueError(f"Landsat scene {scene_id} has an asset with no CRS")
        if temperature_source.shape != qa_source.shape:
            raise ValueError(f"Landsat scene {scene_id} ST and QA dimensions differ")
        source_bounds = transform_bounds(
            "EPSG:4326", temperature_source.crs, *bbox_wgs84, densify_pts=21
        )
        requested_window = from_bounds(*source_bounds, transform=temperature_source.transform)
        full_window = Window(0, 0, temperature_source.width, temperature_source.height)
        window = requested_window.intersection(full_window).round_offsets().round_lengths()
        dn = temperature_source.read(1, window=window)
        qa = qa_source.read(1, window=window)
        source_window_transform = temperature_source.window_transform(window)
        invalid_bits = sum(1 << bit for bit in (0, 1, 2, 3, 4, 5, 7))
        valid = (dn > 0) & ((qa & invalid_bits) == 0)
        celsius = dn.astype("float32") * ST_SCALE + ST_OFFSET_K - 273.15
        valid &= (celsius >= -50.0) & (celsius <= 80.0)
        celsius[~valid] = np.nan

        west, south, east, north = transform_bounds(
            "EPSG:4326", f"EPSG:{target_srid}", *bbox_wgs84, densify_pts=21
        )
        width = max(1, int(np.ceil((east - west) / grid_size_m)))
        height = max(1, int(np.ceil((north - south) / grid_size_m)))
        destination = np.full((height, width), np.nan, dtype="float32")
        transform = from_origin(west, north, grid_size_m, grid_size_m)
        reproject(
            source=celsius,
            destination=destination,
            src_transform=source_window_transform,
            src_crs=temperature_source.crs,
            src_nodata=np.nan,
            dst_transform=transform,
            dst_crs=f"EPSG:{target_srid}",
            dst_nodata=np.nan,
            resampling=Resampling.average,
        )

    rows: list[dict[str, Any]] = []
    for row_index, column_index in np.argwhere(np.isfinite(destination)):
        left, top = transform * (int(column_index), int(row_index))
        right, bottom = transform * (int(column_index) + 1, int(row_index) + 1)
        rows.append(
            {
                "observed_on": observed_on,
                "observed_at": observed_at,
                "heat_value": round(float(destination[row_index, column_index]), 3),
                "measurement_type": "land_surface_temperature",
                "unit": "degC",
                "source_scene_id": scene_id,
                "cloud_cover_pct": cloud_cover,
                "geometry_wkt": box(left, bottom, right, top).wkt,
                "source_srid": target_srid,
            }
        )
    return rows


def asset_metadata(item: dict[str, Any], key: str, local_path: Path) -> dict[str, Any]:
    asset = item["assets"][key]
    properties = item["properties"]
    return {
        "asset_role": "surface_temperature_raster" if key == "lwir11" else "quality_mask_raster",
        "source_scene_id": item["id"],
        "source_href": asset["href"],
        "local_path": str(local_path),
        "media_type": asset.get("type"),
        "source_crs": f"EPSG:{properties.get('proj:epsg')}" if properties.get("proj:epsg") else None,
        "pixel_size_m": (
            asset.get("gsd")
            or (asset.get("raster:bands") or [{}])[0].get("spatial_resolution")
            or (asset.get("eo:bands") or [{}])[0].get("gsd")
        ),
        "checksum": asset.get("file:checksum"),
        "acquired_at": properties.get("datetime"),
        "metadata": {"asset_key": key, "cloud_cover_pct": properties.get("eo:cloud_cover")},
    }
