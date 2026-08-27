import pathlib
import tempfile
import unittest

from greenchanger_script.migrate import expanded_sql, migration_files


class MigrationFileTests(unittest.TestCase):
    def test_migrations_are_numbered_and_ordered(self):
        self.assertEqual(
            [version for version, _ in migration_files()],
            [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16],
        )

    def test_include_is_expanded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            included = root / "included.sql"
            migration = root / "001_test.sql"
            included.write_text("SELECT 1;", encoding="utf-8")
            migration.write_text("-- include: included.sql\n", encoding="utf-8")
            self.assertIn("SELECT 1;", expanded_sql(migration))

    def test_circular_include_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "001_loop.sql"
            path.write_text("-- include: 001_loop.sql\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                expanded_sql(path)

    def test_cost_migration_conditionally_renames_legacy_quality_column(self):
        migration = next(
            path for version, path in migration_files() if version == 13
        )
        sql = expanded_sql(migration)
        self.assertIn("information_schema.columns", sql)
        self.assertIn("column_name = 'passed_kpi_1_gate'", sql)
        self.assertIn("column_name = 'passed_quality_gate'", sql)
        self.assertIn(
            "RENAME COLUMN passed_kpi_1_gate TO passed_quality_gate", sql
        )
        self.assertNotIn(
            "CREATE OR REPLACE VIEW dataset_quality_summary", sql
        )

    def test_intervention_evidence_migration_separates_validation_and_precision(self):
        migration = next(
            path for version, path in migration_files() if version == 14
        )
        sql = expanded_sql(migration)
        self.assertIn("CREATE TABLE intervention_evidence", sql)
        self.assertIn("CREATE TABLE model_evidence", sql)
        self.assertIn("output_precision", sql)
        self.assertIn("indicative_range", sql)
        self.assertIn("precise_point_estimate", sql)
        self.assertIn("selected_intervention_evidence", sql)
        self.assertIn("10.1016/j.landurbplan.2021.104046", sql)
        self.assertIn("10.1007/s00704-015-1409-y", sql)

    def test_intervention_validation_migration_starts_unvalidated(self):
        migration = next(
            path for version, path in migration_files() if version == 15
        )
        sql = expanded_sql(migration)
        self.assertIn("CREATE TABLE intervention_model_parameter", sql)
        self.assertIn("CREATE TABLE intervention_model_validation_run", sql)
        self.assertIn("CREATE TABLE intervention_model_validation_result", sql)
        self.assertIn("'validation_in_progress'", sql)
        self.assertNotIn("SET validation_status = 'validated'", sql)
        self.assertIn("literature-bounded-indicative-v1", sql)

    def test_multi_station_weather_context_has_freshness_and_distance_guards(self):
        migration = next(
            path for version, path in migration_files() if version == 16
        )
        sql = expanded_sql(migration)
        self.assertIn("INTERVAL '3 hours'", sql)
        self.assertIn("good_local_context", sql)
        self.assertIn("regional_context_warning", sql)
        self.assertIn("too_distant_temperature_suppressed", sql)
        self.assertIn("distance_m <= 25000", sql)
        self.assertIn("THEN weather.air_temperature_c", sql)


if __name__ == "__main__":
    unittest.main()
