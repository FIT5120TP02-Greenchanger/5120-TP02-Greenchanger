import unittest

from shapely.geometry import Polygon

from greenchanger_data.vicmap_lga import normalise_feature


class VicmapLgaTests(unittest.TestCase):
    def test_official_fields_and_polygon_are_normalised(self):
        row = normalise_feature(
            {
                "ufi": 123,
                "lga_code": "345",
                "lga_name": "TEST",
                "lga_official_name": "Test City Council",
                "abs_lga_code": "23450",
            },
            Polygon([(0, 0), (1, 0), (1, 1), (0, 0)]),
            4326,
        )
        self.assertEqual(row["source_feature_id"], "123")
        self.assertEqual(row["lga_code"], "345")
        self.assertEqual(row["lga_official_name"], "Test City Council")
        self.assertTrue(row["geometry_wkt"].startswith("MULTIPOLYGON"))

    def test_missing_geometry_remains_unavailable_for_quality_gate(self):
        row = normalise_feature(
            {"ufi": 1, "lga_code": "1", "lga_name": "Test"}, None, 7855
        )
        self.assertIsNone(row["geometry_wkt"])


if __name__ == "__main__":
    unittest.main()
