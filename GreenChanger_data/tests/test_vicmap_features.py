import unittest

from shapely import wkt

from greenchanger_data.vicmap_features import (
    normalise_address,
    normalise_property,
    normalise_urban_tree,
)


class VicmapFeatureTests(unittest.TestCase):
    def test_address_retains_property_join_key(self):
        record = normalise_address({
            "properties": {
                "pfi": "A1",
                "property_pfi": "P9",
                "ezi_address": "1 TEST STREET MELBOURNE 3000",
                "locality_name": "MELBOURNE",
                "postcode": "3000",
            },
            "geometry": {"type": "Point", "coordinates": [144.96, -37.81]},
        })
        self.assertEqual(record["source_address_id"], "A1")
        self.assertEqual(record["source_property_id"], "P9")
        self.assertEqual(record["source_srid"], 4326)
        self.assertTrue(record["geometry_wkt"].startswith("POINT"))

    def test_property_polygon_is_normalised_to_multipolygon(self):
        record = normalise_property({
            "properties": {"prop_pfi": "P9", "Shape__Area": 100.5},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [144.0, -37.0], [144.01, -37.0],
                    [144.01, -37.01], [144.0, -37.0],
                ]],
            },
        })
        self.assertEqual(record["source_parcel_id"], "P9")
        self.assertEqual(record["parcel_area_m2"], 100.5)
        self.assertEqual(wkt.loads(record["geometry_wkt"]).geom_type, "MultiPolygon")

    def test_urban_tree_retains_mapped_dimensions_and_dates(self):
        record = normalise_urban_tree({
            "properties": {
                "ufi": "TREE-1",
                "feature_type": "Tree",
                "canopy_radius_m": 3.2,
                "height_m": 8.4,
                "dense_canopy": "Y",
                "source_begin_date": "2019-01-01",
                "source_end_date": "2020-11-02",
            },
            "geometry": {"type": "Point", "coordinates": [144.96, -37.81]},
        })
        self.assertEqual(record["source_tree_id"], "TREE-1")
        self.assertEqual(record["canopy_radius_m"], 3.2)
        self.assertEqual(record["height_m"], 8.4)
        self.assertEqual(record["source_observed_to"], "2020-11-02")
        self.assertTrue(record["geometry_wkt"].startswith("POINT"))

    def test_urban_tree_suppresses_implausible_optional_dimensions(self):
        record = normalise_urban_tree({
            "properties": {
                "ufi": "TREE-OUTLIER",
                "canopy_radius_m": 80,
                "height_m": 181.45,
            },
            "geometry": {"type": "Point", "coordinates": [144.96, -37.81]},
        })
        self.assertIsNone(record["canopy_radius_m"])
        self.assertIsNone(record["height_m"])

        very_short = normalise_urban_tree({
            "properties": {"ufi": "TREE-SHORT", "height_m": 0.01},
            "geometry": {"type": "Point", "coordinates": [144.96, -37.81]},
        })
        self.assertIsNone(very_short["height_m"])


if __name__ == "__main__":
    unittest.main()
