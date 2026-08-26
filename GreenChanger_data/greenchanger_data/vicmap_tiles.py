"""Build a Melbourne canopy proxy from the official Vicmap cached tile API."""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any, Sequence
from urllib.request import Request, urlopen

from greenchanger_data.canopy import DEFAULT_MELBOURNE_BBOX


SERVICE_URL = (
    "https://tiles-ap1.arcgis.com/P744lA0wf4LlBZ84/arcgis/rest/services/"
    "Vicmap_Vegetation_Tree_Extent/MapServer"
)
WEB_MERCATOR_HALF_WORLD = 20037508.342789244
TILE_SIZE = 256


def lonlat_to_tile(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    scale = 2**zoom
    x = int((lon + 180.0) / 360.0 * scale)
    latitude = math.radians(max(-85.05112878, min(85.05112878, lat)))
    y = int((1.0 - math.asinh(math.tan(latitude)) / math.pi) / 2.0 * scale)
    return x, y


def tile_range(bbox_wgs84: Sequence[float], zoom: int) -> tuple[int, int, int, int]:
    west, south, east, north = bbox_wgs84
    x_min, y_max = lonlat_to_tile(west, south, zoom)
    x_max, y_min = lonlat_to_tile(east, north, zoom)
    return x_min, x_max, y_min, y_max


def _download_tile(x: int, y: int, zoom: int) -> tuple[int, int, bytes]:
    url = f"{SERVICE_URL}/tile/{zoom}/{y}/{x}"
    request = Request(url, headers={"User-Agent": "GreenChanger/1.0"})
    last_error: Exception | None = None
    for _ in range(3):
        try:
            with urlopen(request, timeout=60) as response:
                content = response.read()
            if not content.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError(f"Vicmap tile {zoom}/{y}/{x} was not PNG")
            return x, y, content
        except Exception as error:  # retry transient API and network failures
            last_error = error
    raise RuntimeError(f"Failed to download Vicmap tile {zoom}/{y}/{x}") from last_error


def _rgba_from_png(content: bytes):
    """Decode ArcGIS RGBA, RGB and palette-encoded blank/cache tiles."""

    import numpy as np
    from rasterio.enums import ColorInterp
    from rasterio.io import MemoryFile

    with MemoryFile(content) as memory_file, memory_file.open() as source:
        pixels = source.read()
        colour_interpretation = source.colorinterp
        if source.count == 4:
            return pixels
        if source.count == 1 and colour_interpretation[0] == ColorInterp.palette:
            palette = source.colormap(1)
            lookup = np.zeros((256, 4), dtype="uint8")
            for index, rgba in palette.items():
                lookup[index] = rgba
            return np.moveaxis(lookup[pixels[0]], -1, 0)
        if source.count == 3:
            alpha = np.where(np.any(pixels != 0, axis=0), 255, 0).astype("uint8")
            return np.concatenate([pixels, alpha[np.newaxis, :, :]], axis=0)
    raise ValueError("Vicmap tile uses an unsupported PNG colour model")


def build_canopy_geotiff(
    output_path: Path,
    *,
    bbox_wgs84: Sequence[float] = DEFAULT_MELBOURNE_BBOX,
    zoom: int = 14,
    workers: int = 12,
) -> dict[str, Any]:
    """Mosaic cached PNG alpha into a single-band 0–255 GeoTIFF.

    Alpha 0 represents the transparent no-tree class. Alpha 255 represents the
    opaque tree class; intermediate values retain antialiased boundary coverage.
    This is an API-derived proxy and not the original analytical 20 cm raster.
    """

    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    if not 0 <= zoom <= 23:
        raise ValueError("zoom must be between 0 and 23")
    x_min, x_max, y_min, y_max = tile_range(bbox_wgs84, zoom)
    tile_columns = x_max - x_min + 1
    tile_rows = y_max - y_min + 1
    resolution = (2 * WEB_MERCATOR_HALF_WORLD) / (TILE_SIZE * 2**zoom)
    west = -WEB_MERCATOR_HALF_WORLD + x_min * TILE_SIZE * resolution
    north = WEB_MERCATOR_HALF_WORLD - y_min * TILE_SIZE * resolution
    transform = from_origin(west, north, resolution, resolution)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".part")
    colours: Counter[tuple[int, int, int]] = Counter()
    nontransparent_pixels = 0
    green_pixels = 0

    profile = {
        "driver": "GTiff",
        "width": tile_columns * TILE_SIZE,
        "height": tile_rows * TILE_SIZE,
        "count": 1,
        "dtype": "uint8",
        "crs": "EPSG:3857",
        "transform": transform,
        "tiled": True,
        "blockxsize": TILE_SIZE,
        "blockysize": TILE_SIZE,
        "compress": "DEFLATE",
        "predictor": 2,
    }
    with rasterio.open(temporary, "w", **profile) as target, ThreadPoolExecutor(
        max_workers=workers
    ) as executor:
        for row_number, y in enumerate(range(y_min, y_max + 1), start=1):
            tile_bytes = executor.map(
                lambda x: _download_tile(x, y, zoom), range(x_min, x_max + 1)
            )
            for x, tile_y, content in tile_bytes:
                rgba = _rgba_from_png(content)
                alpha = rgba[3]
                visible = alpha > 0
                if visible.any():
                    rgb = np.moveaxis(rgba[:3, visible], 0, 1)
                    nontransparent_pixels += int(rgb.shape[0])
                    green_pixels += int(((rgb[:, 1] > rgb[:, 0]) & (rgb[:, 1] > rgb[:, 2])).sum())
                    stride = max(1, rgb.shape[0] // 1024)
                    sample = rgb[::stride]
                    unique, counts = np.unique(sample, axis=0, return_counts=True)
                    colours.update(
                        {tuple(map(int, colour)): int(count) for colour, count in zip(unique, counts)}
                    )
                window = rasterio.windows.Window(
                    (x - x_min) * TILE_SIZE,
                    (tile_y - y_min) * TILE_SIZE,
                    TILE_SIZE,
                    TILE_SIZE,
                )
                target.write(alpha, 1, window=window)
            if row_number % 5 == 0 or row_number == tile_rows:
                print(f"Vicmap tiles: {row_number}/{tile_rows} rows", flush=True)

    green_class_rate = (
        round(green_pixels / nontransparent_pixels * 100, 4)
        if nontransparent_pixels
        else 0.0
    )
    if nontransparent_pixels == 0 or green_class_rate < 99.0:
        temporary.unlink(missing_ok=True)
        raise ValueError(
            "Vicmap tile symbology did not match the verified transparent/green classes"
        )
    temporary.replace(output_path)
    metadata = {
        "source_service": SERVICE_URL,
        "source_kind": "ArcGIS cached rendered PNG tiles",
        "analytical_status": "lower-resolution proxy; not original 20 cm GeoTIFF",
        "bbox_wgs84": list(bbox_wgs84),
        "zoom": zoom,
        "resolution_m": resolution,
        "tile_count": tile_columns * tile_rows,
        "tile_columns": tile_columns,
        "tile_rows": tile_rows,
        "tree_encoding": "PNG alpha: 0=no tree; 255=tree; intermediate=edge coverage",
        "visible_green_class_rate_pct": green_class_rate,
        "dominant_rgb": [[list(rgb), count] for rgb, count in colours.most_common(10)],
        "extracted_at": datetime.now(timezone.utc).isoformat(),
    }
    sidecar = output_path.with_suffix(output_path.suffix + ".json")
    sidecar.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {**metadata, "output_path": str(output_path), "metadata_path": str(sidecar)}
