import unittest

from greenchanger_data.canopy_baseline import (
    BASELINE_METHOD,
    TRANSFORMATION_NAME,
    source_type_for_asset_role,
)


class CanopyBaselineTests(unittest.TestCase):
    def test_api_tiles_are_explicitly_proxy_data(self):
        self.assertEqual(source_type_for_asset_role("canopy_api_tile_mosaic"), ("api_tile_proxy", True))

    def test_analytical_geotiff_is_not_proxy_data(self):
        self.assertEqual(source_type_for_asset_role("canopy_source_raster"), ("analytical_geotiff", False))

    def test_unknown_asset_role_is_rejected(self):
        with self.assertRaises(ValueError):
            source_type_for_asset_role("display_screenshot")

    def test_names_are_versioned(self):
        self.assertTrue(BASELINE_METHOD.endswith("_v1"))
        self.assertTrue(TRANSFORMATION_NAME.endswith("_v1"))


if __name__ == "__main__":
    unittest.main()
