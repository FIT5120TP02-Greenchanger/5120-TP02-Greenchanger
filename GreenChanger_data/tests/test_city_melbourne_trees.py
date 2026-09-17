import unittest

from greenchanger_data.city_melbourne_trees import normalise_record


class CityMelbourneTreeTests(unittest.TestCase):
    def test_normalises_name_location_and_inventory_attributes(self):
        row = normalise_record(
            {
                "com_id": "1286320",
                "common_name": "Peppercorn Tree",
                "scientific_name": "Schinus molle",
                "genus": "Schinus",
                "family": "Anacardiaceae",
                "diameter_breast_height": "45",
                "year_planted": "2008",
                "date_planted": "2008-07-16",
                "age_description": "Mature",
                "useful_life_expectency": "21 - 30 years",
                "useful_life_expectency_value": "30",
                "precinct": "Kensington",
                "located_in": "Park",
                "latitude": "-37.78870471",
                "longitude": "144.926149",
            }
        )
        self.assertEqual(row["display_name"], "Peppercorn Tree")
        self.assertEqual(row["scientific_name"], "Schinus molle")
        self.assertEqual(row["diameter_breast_height_cm"], 45.0)
        self.assertEqual(row["geometry_wkt"], "POINT (144.926149 -37.78870471)")

    def test_scientific_name_is_display_fallback(self):
        row = normalise_record(
            {
                "com_id": "one",
                "common_name": "",
                "scientific_name": "Ulmus parvifolia",
                "latitude": "-37.81",
                "longitude": "144.96",
            }
        )
        self.assertEqual(row["display_name"], "Ulmus parvifolia")


if __name__ == "__main__":
    unittest.main()
