"""Prepare official Vicmap Tree Extent rasters for database ingestion."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Sequence


DEFAULT_MELBOURNE_BBOX = (144.4, -38.5, 146.0, -37.4)


def profile_canopy_raster(path: Path, *, sample_blocks: int = 24) -> dict[str, Any]:
    """Inspect class values and spatial metadata without loading the whole raster."""

    import numpy as np
    import rasterio

    with rasterio.open(path) as source:
        if source.crs is None:
            raise ValueError("Canopy raster has no CRS")
        values: set[float] = set()
        for number, (_, window) in enumerate(source.block_windows(1)):
            block = source.read(1, window=window, masked=True)
            values.update(float(value) for value in np.unique(block.compressed()))
            if number + 1 >= sample_blocks:
                break
        return {
            "crs": source.crs.to_string(),
            "width": source.width,
            "height": source.height,
            "band_count": source.count,
            "pixel_size": [abs(source.transform.a), abs(source.transform.e)],
            "nodata": source.nodata,
            "sample_values": sorted(values)[:32],
        }


def _tree_value(profile: dict[str, Any], requested: float | None) -> float:
    if requested is not None:
        if requested <= 0:
            raise ValueError("tree_value must be greater than zero")
        return float(requested)
    values = [value for value in profile["sample_values"] if value != profile["nodata"]]
    if set(values) in ({0.0, 1.0}, {1.0}):
        return 1.0
    raise ValueError(
        "Could not safely infer the canopy class. Inspect --profile-canopy and "
        "pass --tree-value only after confirming the official raster legend."
    )


def aggregate_canopy(
    path: Path,
    *,
    observed_on: date,
    bbox_wgs84: Sequence[float] = DEFAULT_MELBOURNE_BBOX,
    target_srid: int = 7855,
    grid_size_m: float = 500.0,
    tree_value: float | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Aggregate a binary official canopy raster into projected grid cells.

    The source raster remains the system of record. Database rows are compact,
    application-ready percentages rather than millions of source pixels.
    """

    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    from rasterio.warp import reproject, transform_bounds
    from shapely.geometry import box

    if grid_size_m <= 0:
        raise ValueError("grid_size_m must be greater than zero")
    profile = profile_canopy_raster(path)
    if profile["band_count"] != 1:
        raise ValueError(
            "Canopy ingestion requires the single-band analytical GeoTIFF, "
            "not an RGB map-service image"
        )
    canopy_value = _tree_value(profile, tree_value)

    with rasterio.open(path) as source:
        west, south, east, north = transform_bounds(
            "EPSG:4326", f"EPSG:{target_srid}", *bbox_wgs84, densify_pts=21
        )
        width = max(1, int(np.ceil((east - west) / grid_size_m)))
        height = max(1, int(np.ceil((north - south) / grid_size_m)))
        transform = from_origin(west, north, grid_size_m, grid_size_m)
        destination = np.full((height, width), np.nan, dtype="float32")
        reproject(
            source=rasterio.band(source, 1),
            destination=destination,
            src_transform=source.transform,
            src_crs=source.crs,
            src_nodata=source.nodata,
            dst_transform=transform,
            dst_crs=f"EPSG:{target_srid}",
            dst_nodata=np.nan,
            resampling=Resampling.average,
        )

    rows: list[dict[str, Any]] = []
    for row_index, column_index in np.argwhere(np.isfinite(destination)):
        raw_fraction = float(destination[row_index, column_index]) / canopy_value
        percentage = max(0.0, min(100.0, raw_fraction * 100.0))
        left, top = transform * (int(column_index), int(row_index))
        right, bottom = transform * (int(column_index) + 1, int(row_index) + 1)
        rows.append(
            {
                "observed_on": observed_on.isoformat(),
                "vegetation_type": "tree_canopy",
                "vegetation_percentage": round(percentage, 2),
                "calculation_method": "area-weighted mean of Vicmap Tree Extent pixels",
                "spatial_resolution_m": grid_size_m,
                "confidence_score": 100.0,
                "geometry_wkt": box(left, bottom, right, top).wkt,
                "source_srid": target_srid,
            }
        )

    metadata = {
        **profile,
        "tree_value": canopy_value,
        "target_srid": target_srid,
        "grid_size_m": grid_size_m,
        "bbox_wgs84": list(bbox_wgs84),
        "output_cells": len(rows),
    }
    return rows, metadata
