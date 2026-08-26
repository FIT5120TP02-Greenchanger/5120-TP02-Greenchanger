import pathlib
import tempfile
import unittest

from greenchanger_script.migrate import expanded_sql, migration_files


class MigrationFileTests(unittest.TestCase):
    def test_migrations_are_numbered_and_ordered(self):
        self.assertEqual(
            [version for version, _ in migration_files()],
            [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13],
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


if __name__ == "__main__":
    unittest.main()
