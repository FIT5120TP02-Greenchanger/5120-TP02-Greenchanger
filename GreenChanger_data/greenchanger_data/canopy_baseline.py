"""Shared provenance rules for the Greater Melbourne canopy baseline."""

BASELINE_METHOD = "vicmap_tree_extent_area_weighted_500m_v1"
TRANSFORMATION_NAME = "vicmap_canopy_baseline_500m_v1"


def source_type_for_asset_role(asset_role: str) -> tuple[str, bool]:
    """Classify the source without presenting rendered tiles as analytical data."""

    if asset_role == "canopy_api_tile_mosaic":
        return "api_tile_proxy", True
    if asset_role in {"canopy_source_raster", "canopy_analytical_geotiff"}:
        return "analytical_geotiff", False
    raise ValueError(f"Unsupported canopy asset role: {asset_role}")
