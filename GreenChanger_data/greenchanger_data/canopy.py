"""Prepare official Vicmap Tree Extent rasters for database ingestion."""

from __future__ import annotations

from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Sequence


DEFAULT_MELBOURNE_BBOX = (144.4, -38.5, 146.0, -37.4)


def _warp_canopy_tile(task):
    """Process one native tile in a bounded worker."""

    record, target_srid, transform, width, height, tree_value = task
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.vrt import WarpedVRT

    with rasterio.Env(GDAL_CACHEMAX=64_000_000):
        with rasterio.open(record["path"]) as source:
            with WarpedVRT(
                source, crs=f"EPSG:{target_srid}", transform=transform,
                width=width, height=height, resampling=Resampling.average,
                src_nodata=source.nodata, nodata=np.nan, dtype="float32",
            ) as warped:
                tile = warped.read(1, masked=True)
    finite = ~np.ma.getmaskarray(tile) & np.isfinite(tile.data)
    return (
        f'{record["filename"]}:{record["sha256"]}',
        tile.data / tree_value,
        finite.astype("float32"),
    )


def _aggregation_fingerprint(
    records: Sequence[dict[str, Any]], bbox_wgs84: Sequence[float],
    target_srid: int, grid_size_m: float, tree_value: float,
) -> str:
    payload = {
        "tiles": [(record["filename"], record["sha256"]) for record in records],
        "bbox_wgs84": list(bbox_wgs84), "target_srid": target_srid,
        "grid_size_m": grid_size_m, "tree_value": tree_value,
        "method": "tilewise_valid_area_weighted_v1",
    }
    return sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def aggregate_canopy_tiles_resumable(
    records: Sequence[dict[str, Any]], *, observed_on: date,
    bbox_wgs84: Sequence[float], checkpoint_path: Path,
    target_srid: int = 7855, grid_size_m: float = 500.0,
    tree_value: float = 1.0, stop_after_tiles: int | None = None,
    workers: int = 1,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Aggregate native analytical tiles with an atomic per-tile checkpoint.

    Each source tile is warped independently onto one stable output grid. Tree
    and valid-data fractions are accumulated by covered area, so nodata is not
    interpreted as zero canopy. The checkpoint contains the accumulators and
    processed tile checksums; an interrupted run resumes at the next tile.
    """

    import numpy as np
    from rasterio.transform import from_origin
    from rasterio.warp import transform_bounds
    from shapely.geometry import box

    if not records:
        raise ValueError("At least one analytical canopy tile is required")
    if grid_size_m <= 0:
        raise ValueError("grid_size_m must be greater than zero")
    if tree_value <= 0:
        raise ValueError("tree_value must be greater than zero")
    if workers < 1:
        raise ValueError("workers must be at least one")

    west, south, east, north = transform_bounds(
        "EPSG:4326", f"EPSG:{target_srid}", *bbox_wgs84, densify_pts=21
    )
    width = max(1, int(np.ceil((east - west) / grid_size_m)))
    height = max(1, int(np.ceil((north - south) / grid_size_m)))
    transform = from_origin(west, north, grid_size_m, grid_size_m)
    fingerprint = _aggregation_fingerprint(
        records, bbox_wgs84, target_srid, grid_size_m, tree_value
    )

    tree_area_fraction = np.zeros((height, width), dtype="float64")
    valid_area_fraction = np.zeros((height, width), dtype="float64")
    processed: set[str] = set()
    if checkpoint_path.exists():
        with np.load(checkpoint_path, allow_pickle=False) as state:
            saved_fingerprint = str(state["fingerprint"].item())
            if saved_fingerprint != fingerprint:
                raise ValueError(
                    "Canopy checkpoint configuration/source changed; use a new "
                    "checkpoint or remove the stale one"
                )
            tree_area_fraction = state["tree_area_fraction"]
            valid_area_fraction = state["valid_area_fraction"]
            processed = set(json.loads(str(state["processed"].item())))
            if tree_area_fraction.shape != (height, width):
                raise ValueError("Canopy checkpoint grid shape does not match configuration")

    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    pending = [
        record for record in sorted(records, key=lambda item: item["filename"])
        if f'{record["filename"]}:{record["sha256"]}' not in processed
    ]
    if stop_after_tiles is not None:
        pending = pending[:stop_after_tiles]
    tasks = [
        (record, target_srid, transform, width, height, tree_value)
        for record in pending
    ]
    if workers == 1:
        results = map(_warp_canopy_tile, tasks)
    else:
        # GDAL performs the warp outside Python's interpreter lock. Threads
        # avoid platform semaphore restrictions while still overlapping tile IO.
        from concurrent.futures import ThreadPoolExecutor
        executor = ThreadPoolExecutor(max_workers=workers)
        futures = [executor.submit(_warp_canopy_tile, task) for task in tasks]
        from concurrent.futures import as_completed
        results = (future.result() for future in as_completed(futures))
    try:
        for tile_key, tile_tree, tile_valid in results:
            finite = tile_valid > 0
            tree_area_fraction[finite] += tile_tree[finite] * tile_valid[finite]
            valid_area_fraction[finite] += tile_valid[finite]
            processed.add(tile_key)

            temporary = checkpoint_path.with_suffix(checkpoint_path.suffix + ".tmp")
            with temporary.open("wb") as output:
                np.savez_compressed(
                    output, fingerprint=np.array(fingerprint),
                    processed=np.array(json.dumps(sorted(processed))),
                    tree_area_fraction=tree_area_fraction,
                    valid_area_fraction=valid_area_fraction,
                )
            temporary.replace(checkpoint_path)
    finally:
        if workers != 1:
            executor.shutdown()

    rows: list[dict[str, Any]] = []
    complete = len(processed) == len(records)
    if complete:
        for row_index, column_index in np.argwhere(valid_area_fraction > 0):
            coverage = min(1.0, float(valid_area_fraction[row_index, column_index]))
            fraction = float(tree_area_fraction[row_index, column_index]) / float(
                valid_area_fraction[row_index, column_index]
            )
            left, top = transform * (int(column_index), int(row_index))
            right, bottom = transform * (int(column_index) + 1, int(row_index) + 1)
            rows.append({
                "observed_on": observed_on.isoformat(),
                "vegetation_type": "tree_canopy",
                "vegetation_percentage": round(max(0.0, min(1.0, fraction)) * 100, 2),
                "calculation_method": "tile-wise valid-area-weighted mean of native Vicmap Tree Extent pixels",
                "spatial_resolution_m": grid_size_m,
                "confidence_score": round(coverage * 100, 2),
                "geometry_wkt": box(left, bottom, right, top).wkt,
                "source_srid": target_srid,
            })
    metadata = {
        "aggregation_method": "tilewise_valid_area_weighted_v1",
        "fingerprint": fingerprint, "target_srid": target_srid,
        "grid_size_m": grid_size_m, "bbox_wgs84": list(bbox_wgs84),
        "width": width, "height": height, "tree_value": tree_value,
        "source_tile_count": len(records), "processed_tile_count": len(processed),
        "complete": complete, "output_cells": len(rows),
        "checkpoint_path": str(checkpoint_path.resolve()),
    }
    return rows, metadata


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
