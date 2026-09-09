import json
from pathlib import Path
import tempfile
import unittest

from greenchanger_data.city_canopy_history import normalise_record, normalised_rows


class CityCanopyHistoryTests(unittest.TestCase):
    @staticmethod
    def polygon_feature():
        return {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [144.96, -37.82], [144.961, -37.82],
                    [144.961, -37.819], [144.96, -37.819],
                    [144.96, -37.82],
                ]],
            },
        }

    def test_2016_polygon_is_normalised_to_common_contract(self):
        row = normalise_record(
            {"geo_shape": self.polygon_feature(), "area": "100.5"}, 2016
        )
        self.assertEqual(row["observed_year"], 2016)
        self.assertEqual(row["observed_on"], "2016-12-31")
        self.assertTrue(row["geometry_wkt"].startswith("MULTIPOLYGON"))
        self.assertGreater(row["calculated_area_m2"], 0)
        self.assertEqual(row["source_area_m2"], 100.5)
        self.assertEqual(len(row["source_feature_key"]), 64)

    def test_2021_multipolygon_has_same_contract(self):
        geometry = self.polygon_feature()["geometry"]
        row = normalise_record(
            {
                "geo_shape": {
                    "type": "Feature",
                    "geometry": {
                        "type": "MultiPolygon",
                        "coordinates": [geometry["coordinates"]],
                    },
                }
            },
            2021,
        )
        self.assertEqual(row["observed_year"], 2021)
        self.assertIsNone(row["source_area_m2"])
        self.assertGreater(row["calculated_area_m2"], 0)

    def test_missing_geometry_remains_missing_for_quality_rejection(self):
        row = normalise_record({"geo_shape": None}, 2021)
        self.assertIsNone(row["source_feature_key"])
        self.assertIsNone(row["geometry_wkt"])
        self.assertIsNone(row["calculated_area_m2"])

    def test_jsonl_file_is_rereadable_for_streaming_quality_and_copy(self):
        record = {"geo_shape": self.polygon_feature()}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.jsonl"
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            first = list(normalised_rows(path, 2016))
            second = list(normalised_rows(path, 2016))
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
