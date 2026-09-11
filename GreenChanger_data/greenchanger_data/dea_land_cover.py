"""Extract Melbourne-ready summaries from the public DEA Land Cover COG."""

from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any, Iterator, Sequence

import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.windows import Window, from_bounds
from rasterio.warp import Resampling, reproject, transform_bounds


PRODUCT_ID = "ga_ls_landcover_class_cyear_3"
PRODUCT_VERSION = "2-0-0"
NODATA = 255
LEVEL3_CLASSES = {
    111: "Cultivated terrestrial vegetation",
    112: "Natural terrestrial vegetation",
    124: "Natural aquatic vegetation",
    215: "Artificial surface",
    216: "Natural bare surface",
    220: "Water",
}


def continental_cog_url(year: int, band: str = "level3") -> str:
    """Return the official public DEA continental COG URL."""

    if not 1988 <= year <= 2100:
        raise ValueError("DEA Land Cover year must be between 1988 and 2100")
    if band not in {"level3", "level4"}:
        raise ValueError("DEA Land Cover band must be level3 or level4")
    name = f"{PRODUCT_ID}_mosaic_{year}--P1Y_{band}.tif"
    return (
        "https://data.dea.ga.gov.au/derivative/"
        f"{PRODUCT_ID}/{PRODUCT_VERSION}/continental_mosaics/"
        f"{year}--P1Y/{name}"
    )


def request_checksum(source: str, year: int, bbox: Sequence[float], grid_size_m: float) -> str:
    """Hash the immutable source URL and processing parameters for provenance."""

    payload = {
        "source": source,
        "year": year,
        "bbox_wgs84": list(bbox),
        "grid_size_m": grid_size_m,
        "product_version": PRODUCT_VERSION,
    }
    return sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _bounded_window(dataset, bounds: Sequence[float]) -> Window:
    window = from_bounds(*bounds, transform=dataset.transform)
    full = Window(0, 0, dataset.width, dataset.height)
    return window.round_offsets().round_lengths().intersection(full)


def aggregate_land_cover(
    source: str | Path,
    *,
    year: int,
    bbox_wgs84: Sequence[float],
    grid_size_m: float = 500.0,
) -> Iterator[dict[str, Any]]:
    """Aggregate six official Level-3 classes to aligned EPSG:7855 cells.

    Percentages are calculated with average resampling of one binary mask per
    class. No-data pixels are excluded. Exact Melbourne-boundary filtering is
    performed by the database load, after this bounded raster extraction.
    """

    if len(bbox_wgs84) != 4:
        raise ValueError("bbox_wgs84 must be west, south, east, north")
    west, south, east, north = map(float, bbox_wgs84)
    if west >= east or south >= north:
        raise ValueError("bbox_wgs84 is invalid")
    if grid_size_m <= 0:
        raise ValueError("grid_size_m must be positive")

    source_name = str(source)
    environment = rasterio.Env(
        AWS_NO_SIGN_REQUEST="YES",
        GDAL_HTTP_MULTIRANGE="YES",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
    )
    with environment, rasterio.open(source_name) as dataset:
        if dataset.crs is None:
            raise ValueError("DEA raster has no coordinate reference system")
        source_bounds = transform_bounds(
            "EPSG:4326", dataset.crs, west, south, east, north, densify_pts=21
        )
        window = _bounded_window(dataset, source_bounds)
        source_values = dataset.read(1, window=window)
        source_transform = dataset.window_transform(window)

        target_bounds = transform_bounds(
            "EPSG:4326", "EPSG:7855", west, south, east, north, densify_pts=21
        )
        left = math.floor(target_bounds[0] / grid_size_m) * grid_size_m
        bottom = math.floor(target_bounds[1] / grid_size_m) * grid_size_m
        right = math.ceil(target_bounds[2] / grid_size_m) * grid_size_m
        top = math.ceil(target_bounds[3] / grid_size_m) * grid_size_m
        width = int(round((right - left) / grid_size_m))
        height = int(round((top - bottom) / grid_size_m))
        target_transform = from_origin(left, top, grid_size_m, grid_size_m)

        valid_source = source_values != NODATA
        valid_fraction = np.full((height, width), np.nan, dtype="float32")
        reproject(
            valid_source.astype("float32"), valid_fraction,
            src_transform=source_transform, src_crs=dataset.crs,
            dst_transform=target_transform, dst_crs="EPSG:7855",
            src_nodata=None, dst_nodata=np.nan, resampling=Resampling.average,
        )

        class_fractions: dict[int, np.ndarray] = {}
        for code in LEVEL3_CLASSES:
            binary = np.where(valid_source, source_values == code, np.nan).astype("float32")
            destination = np.full((height, width), np.nan, dtype="float32")
            reproject(
                binary, destination,
                src_transform=source_transform, src_crs=dataset.crs,
                dst_transform=target_transform, dst_crs="EPSG:7855",
                src_nodata=np.nan, dst_nodata=np.nan, resampling=Resampling.average,
            )
            class_fractions[code] = destination

    codes = list(LEVEL3_CLASSES)
    for row_index in range(height):
        for column_index in range(width):
            valid_pct = float(valid_fraction[row_index, column_index] * 100.0)
            if not math.isfinite(valid_pct) or valid_pct <= 0:
                continue
            percentages = {
                code: float(class_fractions[code][row_index, column_index] * 100.0)
                for code in codes
            }
            if not all(math.isfinite(value) for value in percentages.values()):
                continue
            dominant_code = max(codes, key=lambda code: percentages[code])
            x_min = left + column_index * grid_size_m
            x_max = x_min + grid_size_m
            y_max = top - row_index * grid_size_m
            y_min = y_max - grid_size_m
            cell_key = f"epsg7855:{int(x_min)}:{int(y_min)}:{int(grid_size_m)}"
            geometry_wkt = (
                f"POLYGON(({x_min} {y_min},{x_max} {y_min},{x_max} {y_max},"
                f"{x_min} {y_max},{x_min} {y_min}))"
            )
            yield {
                "cell_key": cell_key,
                "observed_year": year,
                "observed_on": f"{year}-12-31",
                "dominant_level3_code": dominant_code,
                "dominant_level3_name": LEVEL3_CLASSES[dominant_code],
                "cultivated_vegetation_pct": round(percentages[111], 4),
                "natural_terrestrial_vegetation_pct": round(percentages[112], 4),
                "natural_aquatic_vegetation_pct": round(percentages[124], 4),
                "artificial_surface_pct": round(percentages[215], 4),
                "natural_bare_surface_pct": round(percentages[216], 4),
                "water_pct": round(percentages[220], 4),
                "valid_data_pct": round(valid_pct, 4),
                "geometry_wkt": geometry_wkt,
                "source_srid": 7855,
            }
