import unittest

from shapely.geometry import Point

from greenchanger_data.council_tree_inventories import (
    SOURCES,
    clean,
    normalise_feature,
    numeric_range,
    scientific_name,
)


def feature(**properties):
    return {"properties": properties, "geometry": Point(145.1, -37.8)}


class CouncilTreeInventoryTests(unittest.TestCase):
    def test_placeholders_are_missing_not_literal_names(self):
        self.assertIsNone(clean(" Unknown "))
        self.assertIsNone(clean("TBD"))
        self.assertEqual(clean("River Red Gum"), "River Red Gum")

    def test_ranges_and_scientific_names_are_standardised(self):
        self.assertEqual(numeric_range("5-10 m"), (5.0, 10.0))
        self.assertEqual(scientific_name("Acacia", "A. baileyana"),
                         ("Acacia baileyana", "species"))
        self.assertEqual(scientific_name("Eucalyptus", "species"),
                         ("Eucalyptus sp.", "genus"))

    def test_brimbank_keeps_only_existing_named_trees_and_dimension_ranges(self):
        row = normalise_feature(
            SOURCES["brimbank"],
            feature(Genus="Eucalyptus", Species="camaldulensis", height="10-15",
                    canopy="5-10", dbh="40-60", Status="Existing",
                    Location="Example Road", Type="Street"),
        )
        self.assertTrue(row["active_record"])
        self.assertEqual(row["scientific_name"], "Eucalyptus camaldulensis")
        self.assertEqual(row["height_min_m"], 10.0)
        self.assertEqual(row["canopy_width_max_m"], 10.0)
        self.assertEqual(row["dbh_min_cm"], 40.0)

    def test_yarra_preserves_name_height_maturity_and_health(self):
        row = normalise_feature(
            SOURCES["yarra"],
            feature(ref="Y1", common="Silver Wattle", genus="Acacia",
                    species="A. dealbata", family="Fabaceae", height=8.5,
                    dbh=31, maturity="Mature", health="Good", structure="Fair"),
        )
        self.assertEqual(row["source_tree_id"], "yarra:Y1")
        self.assertEqual(row["scientific_name"], "Acacia dealbata")
        self.assertEqual(row["height_m"], 8.5)
        self.assertEqual(row["age_description"], "Mature")
        self.assertEqual(row["health_status"], "Good")

    def test_casey_calculates_mean_canopy_width_from_both_axes(self):
        row = normalise_feature(
            SOURCES["casey"],
            feature(assetnumber="C1", commonname="Spotted Gum",
                    botanicname="Corymbia maculata", treeheight_m=12,
                    canopyewwidth_m=8, canopynswidth_m=6,
                    diameterbreast_hcm=45),
        )
        self.assertEqual(row["source_tree_id"], "casey:C1")
        self.assertEqual(row["canopy_width_m"], 7.0)
        self.assertEqual(row["canopy_width_ew_m"], 8.0)
        self.assertEqual(row["canopy_width_ns_m"], 6.0)

    def test_casey_uses_description_when_nominal_names_are_placeholders(self):
        row = normalise_feature(
            SOURCES["casey"],
            feature(assetnumber="C2", commonname="To Be Determined",
                    botanicname="To Be Determined",
                    familygenus="To Be Determined",
                    description="Eucalyptus leucoxylon"),
        )
        self.assertEqual(row["display_name"], "Eucalyptus leucoxylon")
        self.assertEqual(row["scientific_name"], "Eucalyptus leucoxylon")
        self.assertEqual(row["taxonomic_precision"], "species")

    def test_hobsons_bay_converts_dbh_millimetre_ranges_to_centimetres(self):
        row = normalise_feature(
            SOURCES["hobsons_bay"],
            feature(Genus="Melaleuca", Species="styphelioides",
                    dbh_mm="200-400", type="Street", suburb="Altona"),
        )
        self.assertEqual(row["dbh_min_cm"], 20.0)
        self.assertEqual(row["dbh_max_cm"], 40.0)
        self.assertEqual(row["municipality"], "City of Hobsons Bay")

    def test_wyndham_retains_common_name_dimensions_and_inspection_date(self):
        row = normalise_feature(
            SOURCES["wyndham"],
            feature(tree_id="W1", tree_common="Lemon-scented Gum", height=9,
                    canopy_width=7, diameter_breast_height=42,
                    inspection_date="2025-03-04T00:00:00"),
        )
        self.assertEqual(row["display_name"], "Lemon-scented Gum")
        self.assertEqual(row["taxonomic_precision"], "common_name")
        self.assertEqual(row["canopy_width_m"], 7.0)
        self.assertEqual(row["source_observed_on"], "2025-03-04")

    def test_three_dimensional_source_point_is_cleaned_to_database_2d(self):
        source_feature = {
            "properties": {"tree_id": "W2", "tree_common": "Spotted Gum"},
            "geometry": Point(145.1, -37.8, 42),
        }
        row = normalise_feature(SOURCES["wyndham"], source_feature)
        self.assertEqual(row["geometry_wkt"], "POINT (145.1 -37.8)")
        self.assertNotIn(" Z ", row["geometry_wkt"])


if __name__ == "__main__":
    unittest.main()
