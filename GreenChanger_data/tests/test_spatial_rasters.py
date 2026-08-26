from datetime import date
import tempfile
from pathlib import Path
import unittest

from greenchanger_data.canopy import aggregate_canopy, profile_canopy_raster
from greenchanger_data.landsat import ST_OFFSET_K, ST_SCALE, choose_scenes, is_tiff
from greenchanger_data.vicmap_tiles import lonlat_to_tile, tile_range


class SpatialRasterTests(unittest.TestCase):
    def test_official_landsat_scale_constants(self):
        self.assertAlmostEqual(30000 * ST_SCALE + ST_OFFSET_K - 273.15, -21.6094, places=4)

    def test_scene_selection_prefers_newest_tier_one(self):
        items = [
            {"id": "older", "properties": {"datetime": "2026-01-01T00:00:00Z", "eo:cloud_cover": 2, "landsat:collection_category": "T1", "landsat:wrs_path": "093", "landsat:wrs_row": "086"}},
            {"id": "newer", "properties": {"datetime": "2026-02-01T00:00:00Z", "eo:cloud_cover": 20, "landsat:collection_category": "T1", "landsat:wrs_path": "093", "landsat:wrs_row": "087"}},
            {"id": "tier2", "properties": {"datetime": "2026-03-01T00:00:00Z", "eo:cloud_cover": 1, "landsat:collection_category": "T2", "landsat:wrs_path": "092", "landsat:wrs_row": "086"}},
        ]
        self.assertEqual([item["id"] for item in choose_scenes(items, max_scenes=2)], ["newer", "older"])

    def test_html_login_page_is_not_accepted_as_tiff(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fake.tif"
            path.write_text("<!DOCTYPE html><title>Login</title>", encoding="utf-8")
            self.assertFalse(is_tiff(path))

    def test_vicmap_melbourne_tile_range(self):
        self.assertEqual(lonlat_to_tile(144.9631, -37.8136, 16), (59157, 40213))
        self.assertEqual(tile_range((144.4, -38.5, 146.0, -37.4), 14), (14763, 14836, 10029, 10093))

    def test_binary_canopy_is_aggregated_to_percentage(self):
        try:
            import numpy as np
            import rasterio
            from rasterio.transform import from_origin
        except ImportError:
            self.skipTest("rasterio stack not installed")

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "canopy.tif"
            data = np.array([[1, 0], [1, 0]], dtype="uint8")
            with rasterio.open(
                path, "w", driver="GTiff", width=2, height=2, count=1,
                dtype="uint8", crs="EPSG:7855",
                transform=from_origin(320000, 5820000, 10, 10),
            ) as target:
                target.write(data, 1)
            profile = profile_canopy_raster(path)
            self.assertEqual(profile["sample_values"], [0.0, 1.0])
            rows, _ = aggregate_canopy(
                path, observed_on=date(2026, 1, 1),
                bbox_wgs84=(144.7701, -37.7482, 144.7704, -37.7480),
                grid_size_m=20, tree_value=1,
            )
            self.assertTrue(all(0 <= row["vegetation_percentage"] <= 100 for row in rows))


if __name__ == "__main__":
    unittest.main()
