import inspect
import unittest

from greenchanger_script.ingestion import (
    ingest_bom,
    ingest_costs,
    optional_bool,
    quality_dimension,
    sync_sources,
)


class IngestionHelperTests(unittest.TestCase):
    def test_optional_boolean_values(self):
        self.assertTrue(optional_bool("yes"))
        self.assertTrue(optional_bool("Y"))
        self.assertFalse(optional_bool("false"))
        self.assertFalse(optional_bool("N"))
        self.assertIsNone(optional_bool(""))

    def test_invalid_boolean_is_rejected(self):
        with self.assertRaises(ValueError):
            optional_bool("sometimes")

    def test_rule_types_map_to_quality_dimensions(self):
        self.assertEqual(quality_dimension("required"), "completeness")
        self.assertEqual(quality_dimension("unique"), "uniqueness")
        self.assertEqual(quality_dimension("field_order"), "consistency")

    def test_bom_geometry_parameters_have_explicit_postgres_types(self):
        source = inspect.getsource(ingest_bom)
        self.assertIn("%s::text IS NULL", source)
        self.assertIn("ST_GeomFromText(%s::text, %s::integer)", source)
        self.assertIn("station_coverage_pct >= 80.0", source)
        self.assertIn('"application_ready" if publish_weather else "internal"', source)
        self.assertIn("partial_station_feed_availability", source)

    def test_source_sync_persists_licence_decisions(self):
        source = inspect.getsource(sync_sources)
        self.assertIn('source.get("licence_status", "review_required")', source)
        self.assertIn("source_url, licence, licence_status, source_category", source)

    def test_cost_upsert_uses_tree_type_business_key(self):
        source = inspect.getsource(ingest_costs)
        self.assertIn(
            "greening_option_id, cost_context, cost_basis, tree_type,",
            source,
        )
        self.assertIn(
            "source_name, valid_from, source_reference",
            source,
        )


if __name__ == "__main__":
    unittest.main()
