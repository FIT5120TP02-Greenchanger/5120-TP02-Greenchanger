"""Calculate parcel-level canopy from a fine-resolution analytical raster."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping


MAX_PROPERTY_PIXEL_SIZE_M = 2.0
REQUIRED_ASSET_ROLE = "canopy_analytical_geotiff"
MAX_PROPERTY_WINDOW_PIXELS = 1_048_576
MAX_PROPERTY_SCAN_PIXELS = 25_000_000


@dataclass(frozen=True)
class PropertyCanopyResult:
    """A canopy result and its raster-coverage quality evidence."""

    canopy_area_m2: float | None
    parcel_area_m2: float
    canopy_percentage: float | None
    raster_covered_area_m2: float
    coverage_percentage: float
    quality_status: str
    failure_reason: str | None = None


def validate_property_canopy_source(
    source: Any, *, asset_role: str, maximum_pixel_size_m: float = MAX_PROPERTY_PIXEL_SIZE_M
) -> float:
    """Reject rendered/coarse rasters before they can produce property claims."""

    if asset_role != REQUIRED_ASSET_ROLE:
        raise ValueError(
            "Property canopy requires asset_role=canopy_analytical_geotiff; "
            "rendered API mosaics are neighbourhood-only"
        )
    if source.count != 1:
        raise ValueError("Property canopy requires a single-band analytical raster")
    if source.crs is None or not source.crs.is_projected:
        raise ValueError("Property canopy raster must use a projected CRS")
    pixel_width = abs(float(source.transform.a))
    pixel_height = abs(float(source.transform.e))
    pixel_size = max(pixel_width, pixel_height)
    if pixel_size > maximum_pixel_size_m:
        raise ValueError(
            f"Property canopy requires pixels <= {maximum_pixel_size_m:g} m; "
            f"source pixels are {pixel_size:.3f} m"
        )
    return pixel_width * pixel_height


def calculate_property_canopy(
    source: Any,
    parcel_geometry: Mapping[str, Any],
    *,
    parcel_area_m2: float,
    tree_value: float,
    minimum_coverage_percentage: float = 95.0,
    maximum_window_pixels: int = MAX_PROPERTY_WINDOW_PIXELS,
    maximum_scan_pixels: int = MAX_PROPERTY_SCAN_PIXELS,
) -> PropertyCanopyResult:
    """Clip one parcel and calculate canopy using pixel-centre inclusion.

    ``parcel_geometry`` must already be expressed in the raster CRS. Nodata is
    excluded and reported as coverage, so missing raster data is never treated
    as zero canopy.
    """

    import numpy as np
    from rasterio.errors import WindowError
    from rasterio.features import geometry_mask, geometry_window
    from rasterio.windows import Window, transform as window_transform

    if parcel_area_m2 <= 0:
        raise ValueError("parcel_area_m2 must be greater than zero")
    if tree_value <= 0:
        raise ValueError("tree_value must be greater than zero")
    if maximum_window_pixels < 1:
        raise ValueError("maximum_window_pixels must be at least one")
    if maximum_scan_pixels < 1:
        raise ValueError("maximum_scan_pixels must be at least one")
    pixel_area_m2 = abs(float(source.transform.a) * float(source.transform.e))

    geometry_type = parcel_geometry.get("type")
    if geometry_type == "MultiPolygon":
        geometry_parts = [
            {"type": "Polygon", "coordinates": coordinates}
            for coordinates in parcel_geometry.get("coordinates", [])
        ]
    else:
        geometry_parts = [parcel_geometry]

    chunk_side = max(1, math.isqrt(maximum_window_pixels))
    part_windows = []
    for geometry_part in geometry_parts:
        try:
            part_window = geometry_window(source, [geometry_part], boundless=False)
        except WindowError:
            continue
        part_windows.append((geometry_part, part_window))

    if not part_windows:
        return PropertyCanopyResult(
            None, parcel_area_m2, None, 0.0, 0.0, "failed",
            "parcel_outside_canopy_raster",
        )
    scan_pixels = sum(
        int(window.width) * int(window.height) for _, window in part_windows
    )
    if scan_pixels > maximum_scan_pixels:
        return PropertyCanopyResult(
            None, parcel_area_m2, None, 0.0, 0.0, "failed",
            "parcel_window_exceeds_processing_limit",
        )

    covered_pixels = 0
    canopy_pixels = 0
    for geometry_part, part_window in part_windows:
        column_start = int(part_window.col_off)
        column_stop = int(part_window.col_off + part_window.width)
        row_start = int(part_window.row_off)
        row_stop = int(part_window.row_off + part_window.height)
        for row_offset in range(row_start, row_stop, chunk_side):
            height = min(chunk_side, row_stop - row_offset)
            for column_offset in range(column_start, column_stop, chunk_side):
                width = min(chunk_side, column_stop - column_offset)
                window = Window(column_offset, row_offset, width, height)
                band = source.read(1, window=window, masked=True)
                inside = geometry_mask(
                    [geometry_part],
                    out_shape=band.shape,
                    transform=window_transform(window, source.transform),
                    invert=True,
                    all_touched=False,
                )
                valid = inside & ~np.ma.getmaskarray(band)
                covered_pixels += int(valid.sum())
                canopy_pixels += int(
                    np.count_nonzero(valid & np.isclose(band.data, tree_value))
                )

    covered_area = float(covered_pixels) * pixel_area_m2
    coverage_percentage = min(100.0, covered_area * 100.0 / parcel_area_m2)
    if coverage_percentage < minimum_coverage_percentage:
        return PropertyCanopyResult(
            None,
            parcel_area_m2,
            None,
            covered_area,
            round(coverage_percentage, 2),
            "failed",
            "raster_coverage_below_95_percent",
        )

    canopy_area = float(canopy_pixels) * pixel_area_m2
    canopy_percentage = min(100.0, canopy_area * 100.0 / parcel_area_m2)
    return PropertyCanopyResult(
        round(canopy_area, 3),
        parcel_area_m2,
        round(canopy_percentage, 2),
        round(covered_area, 3),
        round(coverage_percentage, 2),
        "passed",
    )
