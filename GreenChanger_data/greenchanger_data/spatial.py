"""Spatial cleaning helpers for GreenChanger vector source files."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def prepare_vector(
    input_path: Path,
    output_path: Path,
    *,
    target_srid: int = 7855,
    boundary_path: Path | None = None,
) -> dict[str, Any]:
    """Validate, repair, reproject and optionally clip a vector dataset.

    GeoPandas is imported inside the function so the lightweight quality and
    analytics tests can run without the geospatial dependency stack.
    """

    import geopandas as gpd

    frame = gpd.read_file(input_path)
    input_count = len(frame)
    if frame.crs is None:
        raise ValueError("Input vector data has no CRS; set it before integration")

    missing_geometry_count = int(frame.geometry.isna().sum())
    frame = frame.loc[frame.geometry.notna()].copy()

    invalid_before = int((~frame.geometry.is_valid).sum())
    if invalid_before:
        frame.geometry = frame.geometry.make_valid()
    frame = frame.loc[~frame.geometry.is_empty].copy()
    frame = frame.to_crs(epsg=target_srid)

    if boundary_path is not None:
        boundary = gpd.read_file(boundary_path)
        if boundary.crs is None:
            raise ValueError("Boundary data has no CRS")
        boundary = boundary.to_crs(epsg=target_srid)
        frame = gpd.clip(frame, boundary)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = output_path.suffix.casefold()
    if suffix in {".parquet", ".geoparquet"}:
        frame.to_parquet(output_path, index=False)
    elif suffix in {".geojson", ".json"}:
        frame.to_file(output_path, driver="GeoJSON")
    else:
        frame.to_file(output_path)

    return {
        "input_records": input_count,
        "missing_geometry_records": missing_geometry_count,
        "invalid_geometry_records_repaired": invalid_before,
        "output_records": len(frame),
        "target_srid": target_srid,
        "output_path": str(output_path),
    }
