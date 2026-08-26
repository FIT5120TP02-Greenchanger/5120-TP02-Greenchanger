import unittest

from greenchanger_data.boundary import normalise_greater_melbourne


class BoundaryTests(unittest.TestCase):
    def test_normalise_greater_melbourne(self):
        document = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {
                    "GCCSA_CODE_2026": "2GMEL",
                    "GCCSA_NAME_2026": "Greater Melbourne",
                    "AREA_ALBERS_SQKM": 9992.6078,
                    "CHANGE_FLAG_2026": "0",
                    "CHANGE_LABEL_2026": "No change",
                    "STATE_NAME_2026": "Victoria",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[144.0, -38.0], [145.0, -38.0], [145.0, -37.0], [144.0, -38.0]]],
                },
            }],
        }
        row = normalise_greater_melbourne(document)
        self.assertEqual(row["source_area_code"], "2GMEL")
        self.assertEqual(row["area_name"], "Greater Melbourne")
        self.assertEqual(row["source_year"], 2026)
        self.assertAlmostEqual(row["area_m2"], 9_992_607_800)
        self.assertTrue(row["geometry_wkt"].startswith("MULTIPOLYGON"))


if __name__ == "__main__":
    unittest.main()
