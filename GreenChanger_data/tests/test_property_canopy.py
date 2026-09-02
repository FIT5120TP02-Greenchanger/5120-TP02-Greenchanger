import unittest

import numpy as np
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from shapely.geometry import box, mapping

from greenchanger_data.property_canopy import (
    calculate_property_canopy,
    validate_property_canopy_source,
)


class PropertyCanopyTests(unittest.TestCase):
    def raster(self, pixels, *, pixel_size=1.0, nodata=255):
        memory = MemoryFile()
        dataset = memory.open(
            driver="GTiff", height=pixels.shape[0], width=pixels.shape[1],
            count=1, dtype=pixels.dtype, crs="EPSG:7855",
            transform=from_origin(0, pixels.shape[0] * pixel_size, pixel_size, pixel_size),
            nodata=nodata,
        )
        dataset.write(pixels, 1)
        self.addCleanup(dataset.close)
        self.addCleanup(memory.close)
        return dataset

    def test_calculates_canopy_only_inside_property(self):
        source = self.raster(np.array([[1, 1], [0, 0]], dtype="uint8"))
        validate_property_canopy_source(source, asset_role="canopy_analytical_geotiff")
        result = calculate_property_canopy(
            source, mapping(box(0, 0, 2, 2)), parcel_area_m2=4, tree_value=1
        )
        self.assertEqual(result.canopy_area_m2, 2.0)
        self.assertEqual(result.canopy_percentage, 50.0)
        self.assertEqual(result.coverage_percentage, 100.0)
        self.assertEqual(result.quality_status, "passed")

    def test_missing_raster_coverage_is_unavailable_not_zero(self):
        source = self.raster(np.array([[1, 255], [0, 255]], dtype="uint8"))
        result = calculate_property_canopy(
            source, mapping(box(0, 0, 2, 2)), parcel_area_m2=4, tree_value=1
        )
        self.assertIsNone(result.canopy_percentage)
        self.assertEqual(result.coverage_percentage, 50.0)
        self.assertEqual(result.quality_status, "failed")

    def test_rejects_rendered_api_proxy(self):
        source = self.raster(np.zeros((2, 2), dtype="uint8"))
        with self.assertRaisesRegex(ValueError, "neighbourhood-only"):
            validate_property_canopy_source(source, asset_role="canopy_api_tile_mosaic")

    def test_rejects_coarse_raster(self):
        source = self.raster(np.zeros((2, 2), dtype="uint8"), pixel_size=19.1)
        with self.assertRaisesRegex(ValueError, "pixels <= 2"):
            validate_property_canopy_source(
                source, asset_role="canopy_analytical_geotiff"
            )


if __name__ == "__main__":
    unittest.main()
