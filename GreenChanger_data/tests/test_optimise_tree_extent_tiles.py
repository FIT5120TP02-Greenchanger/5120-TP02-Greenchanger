import tempfile
from pathlib import Path
import unittest

try:
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin
except ImportError:
    GEOSPATIAL_TEST_STACK = False
else:
    GEOSPATIAL_TEST_STACK = True

from greenchanger_data.sources import sha256_file
from greenchanger_script.optimise_vicmap_tree_extent_tiles import optimise_tile


@unittest.skipUnless(
    GEOSPATIAL_TEST_STACK,
    "install requirements.txt to run Tree Extent optimisation tests",
)
class OptimiseTreeExtentTileTests(unittest.TestCase):
    def test_lossless_tiled_output_is_resumable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.tif"
            output = root / "output.tif"
            pixels = np.array([[0, 1, 2], [1, 1, 0], [0, 0, 1]], dtype="uint8")
            with rasterio.open(
                source, "w", driver="GTiff", width=3, height=3, count=1,
                dtype="uint8", crs="EPSG:7899",
                transform=from_origin(0, 3, 0.2, 0.2), nodata=2,
            ) as dataset:
                dataset.write(pixels, 1)
            record = {
                "path": str(source), "filename": source.name,
                "sha256": sha256_file(source), "epsg": 7899,
                "width": 3, "height": 3, "dtype": "uint8",
                "band_count": 1, "nodata": 2.0,
                "pixel_size_m": [0.2, 0.2], "bounds": [0, 2.4, 0.6, 3],
                "block_shape": [3, 3],
            }

            first = optimise_tile(record, output, 256)
            second = optimise_tile(record, output, 256)

            self.assertEqual(first, second)
            self.assertEqual(first["method"], "lossless_tiled_geotiff_v1")
            with rasterio.open(output) as dataset:
                self.assertEqual(dataset.block_shapes[0], (256, 256))
                np.testing.assert_array_equal(dataset.read(1), pixels)


if __name__ == "__main__":
    unittest.main()
