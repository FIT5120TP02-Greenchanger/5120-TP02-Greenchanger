import unittest
from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "greenchanger_sql/migrations/018_environment_context_radius.sql"
)
SCHEMA = (
    Path(__file__).resolve().parents[1] / "greenchanger_sql/schema.sql"
)
ADDRESS_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "greenchanger_sql/migrations/019_environment_context_by_address.sql"
)


class EnvironmentContextContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8")

    def test_only_supported_layers_are_accepted(self):
        self.assertIn("ARRAY['trees', 'heat']::TEXT[]", self.sql)
        self.assertIn("unsupported layer(s)", self.sql)

    def test_coordinate_and_radius_are_validated(self):
        self.assertIn("p_longitude < -180", self.sql)
        self.assertIn("p_longitude > 180", self.sql)
        self.assertIn("p_latitude < -90", self.sql)
        self.assertIn("p_latitude > 90", self.sql)
        self.assertIn("p_radius_m <= 0", self.sql)
        self.assertIn("p_radius_m > 2000", self.sql)
        self.assertIn("source_area_code = '2GMEL'", self.sql)
        self.assertIn("ST_Covers(area.boundary_geometry, v_point)", self.sql)

    def test_only_current_application_ready_tree_version_is_used(self):
        self.assertIn("Vicmap Vegetation - Tree Urban Point", self.sql)
        self.assertIn("version.integration_status = 'integrated'", self.sql)
        self.assertIn("version.publication_status = 'application_ready'", self.sql)
        self.assertIn("tree.quality_status = 'passed'", self.sql)

    def test_tree_and_heat_searches_use_spatial_radius_predicates(self):
        self.assertIn(
            "ST_DWithin(tree.tree_location, v_point, p_radius_m)", self.sql
        )
        self.assertIn(
            "ST_DWithin(heat.cell_geometry, v_point, p_radius_m)", self.sql
        )
        self.assertIn("tree.tree_location <-> v_point", self.sql)
        self.assertIn("heat.cell_geometry <-> v_point", self.sql)

    def test_heat_geometry_is_clipped_and_limit_is_per_layer(self):
        self.assertIn(
            "ST_Intersection(heat.cell_geometry, v_search_area)", self.sql
        )
        self.assertEqual(self.sql.count("LIMIT p_result_limit"), 2)
        self.assertIn("500m_baseline_cell", self.sql)
        self.assertIn(
            "Landsat land-surface temperature, not air temperature.", self.sql
        )

    def test_cumulative_schema_exposes_the_same_function_contract(self):
        schema = SCHEMA.read_text(encoding="utf-8")
        self.assertIn("CREATE OR REPLACE FUNCTION get_environment_context", schema)
        self.assertIn("p_radius_m DOUBLE PRECISION DEFAULT 500.0", schema)
        self.assertIn("ST_DWithin(tree.tree_location, v_point, p_radius_m)", schema)
        self.assertIn("ST_DWithin(heat.cell_geometry, v_point, p_radius_m)", schema)

    def test_address_wrapper_requires_one_resolved_property(self):
        sql = ADDRESS_MIGRATION.read_text(encoding="utf-8")
        self.assertIn("address search is required", sql)
        self.assertIn("FROM get_property_baseline(p_address_search, 2)", sql)
        self.assertIn("no Melbourne address matched", sql)
        self.assertIn("address search is ambiguous", sql)
        self.assertIn("matched address has no usable coordinate", sql)

    def test_address_wrapper_delegates_radius_validation_and_query(self):
        sql = ADDRESS_MIGRATION.read_text(encoding="utf-8")
        self.assertIn("p_radius_m DOUBLE PRECISION DEFAULT 500.0", sql)
        self.assertIn("p_layers TEXT[] DEFAULT ARRAY['trees', 'heat']", sql)
        self.assertIn("FROM get_environment_context(", sql)
        self.assertIn("v_longitude", sql)
        self.assertIn("v_latitude", sql)

    def test_cumulative_schema_contains_address_wrapper(self):
        schema = SCHEMA.read_text(encoding="utf-8")
        self.assertIn(
            "CREATE OR REPLACE FUNCTION get_environment_context_by_address",
            schema,
        )


if __name__ == "__main__":
    unittest.main()
