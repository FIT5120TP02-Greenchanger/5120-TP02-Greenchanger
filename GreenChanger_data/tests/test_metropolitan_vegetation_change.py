import json
from pathlib import Path
import tempfile
import unittest

import geopandas as gpd
from shapely.geometry import Polygon

from greenchanger_data.metropolitan_vegetation_change import (
    normalise_feature,
    normalised_rows,
    source_checksum,
)


class MetropolitanVegetationChangeTests(unittest.TestCase):
    def setUp(self):
        self.polygon = Polygon([
            (320000, 5810000), (320100, 5810000),
            (320100, 5810100), (320000, 5810100),
            (320000, 5810000),
        ])

    def test_aliases_are_mapped_to_percentage_point_contract(self):
        row = normalise_feature(
            {
                "MMB_CODE": "200000001_1",
                "UNIQUEID": 14,
                "MB_CODE16": "200000001",
                "PP_ANYTREE": "4.5",
                "PP_SHRUB": -1,
                "PP_GRASS": 2.25,
                "PP_ANYVEG": 5.75,
            },
            self.polygon,
        )
        self.assertEqual(row["source_feature_key"], "200000001_1:14")
        self.assertEqual(row["mesh_block_code"], "200000001")
        self.assertEqual(row["tree_change_pct_points"], 4.5)
        self.assertEqual(row["shrub_change_pct_points"], -1.0)
        self.assertEqual(row["grass_change_pct_points"], 2.25)
        self.assertEqual(row["total_vegetation_change_pct_points"], 5.75)
        self.assertEqual(row["source_srid"], 7855)
        self.assertTrue(row["has_change_measure"])

    def test_unrecognised_change_schema_is_marked_for_quality_rejection(self):
        row = normalise_feature({"UNRELATED": 1}, self.polygon)
        self.assertFalse(row["has_change_measure"])

    def test_geometry_hash_is_fallback_when_mesh_block_is_missing(self):
        row = normalise_feature({"TREE_CHG": 1}, self.polygon)
        self.assertEqual(len(row["source_feature_key"]), 64)
        self.assertTrue(row["geometry_wkt"].startswith("MULTIPOLYGON"))

    def test_vector_file_is_reprojected_and_rereadable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "change.geojson"
            frame = gpd.GeoDataFrame(
                {"MB_CODE16": ["1"], "TREE_CHG": [3.0]},
                geometry=[self.polygon], crs="EPSG:7855",
            )
            frame.to_file(path, driver="GeoJSON")
            first = list(normalised_rows(path))
            second = list(normalised_rows(path))
            checksum = source_checksum(path)
        self.assertEqual(first, second)
        self.assertEqual(first[0]["tree_change_pct_points"], 3.0)
        self.assertEqual(len(checksum), 64)


if __name__ == "__main__":
    unittest.main()
