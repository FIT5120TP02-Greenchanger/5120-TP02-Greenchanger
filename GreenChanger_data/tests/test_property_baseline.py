import unittest
from pathlib import Path

from greenchanger_data.property_baseline import LOT_SIZE_RULE, classify_lot_size


class PropertyBaselineTests(unittest.TestCase):
    def test_unknown_area(self):
        self.assertEqual(classify_lot_size(None), "unknown")
        self.assertEqual(classify_lot_size(0), "unknown")

    def test_small_lot(self):
        self.assertEqual(classify_lot_size(399.99), "small")

    def test_medium_boundaries(self):
        self.assertEqual(classify_lot_size(400), "medium")
        self.assertEqual(classify_lot_size(800), "medium")

    def test_large_lot(self):
        self.assertEqual(classify_lot_size(800.01), "large")

    def test_rule_is_documented(self):
        self.assertIn("not statutory", classify_lot_size.__doc__)
        self.assertIn("400-800", LOT_SIZE_RULE)

    def test_database_contract_separates_measurement_scopes(self):
        migration = (
            Path(__file__).resolve().parents[1]
            / "greenchanger_sql/migrations/010_property_baseline_lookup.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("land_surface_temperature_c", migration)
        self.assertIn("current_air_temperature_c", migration)
        self.assertIn("neighbourhood_canopy_percentage", migration)
        self.assertIn("NULL::NUMERIC AS property_canopy_percentage", migration)
        self.assertIn("application_ready_measure_result", migration)
        self.assertIn("model.validation_status = 'validated'", migration)

    def test_property_lookup_exposes_environmental_classifications(self):
        migration = (
            Path(__file__).resolve().parents[1]
            / "greenchanger_sql/migrations/017_environmental_classifications.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("heat_classification TEXT", migration)
        self.assertIn("canopy_classification TEXT", migration)
        self.assertIn("classification_scheme_version TEXT", migration)
        self.assertIn("classification_scope TEXT", migration)


if __name__ == "__main__":
    unittest.main()
