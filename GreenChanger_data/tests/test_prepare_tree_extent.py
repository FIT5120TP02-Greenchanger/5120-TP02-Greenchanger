import tempfile
from hashlib import sha256
import json
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

from greenchanger_script.prepare_vicmap_tree_extent import build_vrt
from greenchanger_script.ingestion import analytical_canopy_manifest


@unittest.skipUnless(
    GEOSPATIAL_TEST_STACK,
    "install requirements.txt to run Tree Extent preparation tests",
)
class PrepareTreeExtentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def tile(self, name, values, left):
        path = self.root / name
        transform = from_origin(left, 1.0, 0.2, 0.2)
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=values.shape[1],
            height=values.shape[0],
            count=1,
            dtype="uint8",
            crs="EPSG:7899",
            transform=transform,
            nodata=2,
        ) as target:
            target.write(values, 1)
        with rasterio.open(path) as source:
            return {
                "path": str(path.resolve()),
                "filename": path.name,
                "epsg": 7899,
                "width": source.width,
                "height": source.height,
                "dtype": source.dtypes[0],
                "nodata": source.nodata,
                "pixel_size_m": [0.2, 0.2],
                "bounds": list(source.bounds),
                "block_shape": list(source.block_shapes[0]),
            }

    def test_vrt_catalogues_adjacent_native_analytical_tiles(self):
        first = self.tile("first.tif", np.zeros((2, 2), dtype="uint8"), 0.0)
        second = self.tile("second.tif", np.ones((2, 2), dtype="uint8"), 0.4)

        result = build_vrt([first, second], self.root / "mosaic.vrt")

        self.assertEqual(result["pixel_size_m"], 0.2)
        self.assertEqual(result["source_tile_count"], 2)
        with rasterio.open(result["path"]) as mosaic:
            np.testing.assert_array_equal(
                mosaic.read(1),
                np.array([[0, 0, 1, 1], [0, 0, 1, 1]], dtype="uint8"),
            )

    def test_ingestion_verifies_vrt_manifest_and_boundary(self):
        record = self.tile("source.tif", np.ones((2, 2), dtype="uint8"), 0.0)
        vrt = self.root / "melbourne_tree_extent_20cm.vrt"
        build_vrt([record], vrt)
        digest = sha256(vrt.read_bytes()).hexdigest()
        (self.root / "melbourne_tree_extent_manifest.json").write_text(
            json.dumps(
                {
                    "dataset_uuid": "f6800447-ef34-5f66-acaa-77a5f2936546",
                    "boundary": {"boundary_wgs84_bounds": [144.0, -39.0, 146.0, -37.0]},
                    "virtual_mosaic": {"sha256": digest},
                }
            ),
            encoding="utf-8",
        )

        manifest = analytical_canopy_manifest(vrt)

        self.assertEqual(
            manifest["boundary"]["boundary_wgs84_bounds"],
            [144.0, -39.0, 146.0, -37.0],
        )

    def test_ingestion_rejects_vrt_without_manifest(self):
        vrt = self.root / "melbourne_tree_extent_20cm.vrt"
        vrt.write_text("not used", encoding="utf-8")
        with self.assertRaisesRegex(FileNotFoundError, "provenance manifest"):
            analytical_canopy_manifest(vrt)


if __name__ == "__main__":
    unittest.main()
