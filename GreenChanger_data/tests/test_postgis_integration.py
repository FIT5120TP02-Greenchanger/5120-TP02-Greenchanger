"""Execute all migrations and public spatial functions against real PostGIS."""

from __future__ import annotations

import os
import time
import unittest
from uuid import uuid4

try:
    import psycopg
    from psycopg import errors, sql
except ModuleNotFoundError:  # Keep fast-test discovery usable before dependencies.
    psycopg = None
    errors = None
    sql = None

from greenchanger_script.migrate import executable_sql, migration_files


DATABASE_URL = os.getenv("GREENCHANGER_TEST_DATABASE_URL")


@unittest.skipUnless(
    DATABASE_URL and psycopg is not None,
    "install requirements and set GREENCHANGER_TEST_DATABASE_URL to run PostGIS tests",
)
class PostgisEnvironmentContextIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = f"greenchanger_it_{uuid4().hex}"
        cls.connection = cls._connect_with_startup_retry()
        cls.connection.autocommit = True
        try:
            with cls.connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.schema))
                )
                cursor.execute(
                    sql.SQL("SET search_path TO {}, public").format(
                        sql.Identifier(cls.schema)
                    )
                )
                for _, path in migration_files():
                    cursor.execute(executable_sql(path))
            cls._seed_spatial_contract()
        except Exception:
            with cls.connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        sql.Identifier(cls.schema)
                    )
                )
            cls.connection.close()
            raise

    @classmethod
    def _connect_with_startup_retry(cls):
        """Tolerate the brief post-health restart seen under amd64 emulation."""

        last_error = None
        for _ in range(30):
            try:
                return psycopg.connect(DATABASE_URL)
            except psycopg.OperationalError as error:
                last_error = error
                time.sleep(0.5)
        raise last_error

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "connection"):
            with cls.connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        sql.Identifier(cls.schema)
                    )
                )
            cls.connection.close()

    @classmethod
    def _seed_spatial_contract(cls):
        with cls.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO analysis_area (
                    area_name, area_type, boundary_geometry, area_m2,
                    source_area_code, source_year
                ) VALUES (
                    'Melbourne integration fixture', 'gccsa',
                    ST_Transform(ST_Multi(ST_GeomFromText(
                        'POLYGON((144.80 -37.95,145.15 -37.95,145.15 -37.65,144.80 -37.65,144.80 -37.95))',
                        4326
                    )), 7855),
                    1000000000, '2GMEL', 2026
                )
                RETURNING analysis_area_id
                """
            )
            area_id = cursor.fetchone()[0]

            versions = {}
            specifications = (
                ("address", "Vicmap Address", "clip_to_abs_gccsa_2GMEL_2026_v1:test"),
                ("property", "Vicmap Property", "clip_to_abs_gccsa_2GMEL_2026_v1:test"),
                ("trees", "Vicmap Vegetation - Tree Urban Point", "tree_fixture_v1"),
                ("heat", "USGS Landsat Collection 2 Surface Temperature", "landsat_latest_daily_mosaic_v1"),
            )
            for key, source_name, method in specifications:
                cursor.execute(
                    """
                    INSERT INTO dataset_version (
                        source_id, analysis_area_id, derivation_method,
                        quality_status, integration_status, publication_status,
                        source_observed_from, source_observed_to
                    )
                    SELECT source_id, %s, %s, 'passed', 'integrated',
                           'application_ready', DATE '2020-01-01', DATE '2026-01-01'
                    FROM dataset_source
                    WHERE source_name = %s
                    RETURNING dataset_version_id
                    """,
                    (area_id, method, source_name),
                )
                versions[key] = cursor.fetchone()[0]

            cursor.execute(
                """
                INSERT INTO parcel (
                    dataset_version_id, source_parcel_id, parcel_geometry,
                    parcel_area_m2, property_type, property_status
                ) VALUES
                (%s, 'PARCEL-A', ST_Multi(ST_Buffer(ST_Transform(
                    ST_SetSRID(ST_MakePoint(144.96, -37.81), 4326), 7855
                ), 30)), 2800, 'residential', 'active'),
                (%s, 'PARCEL-B', ST_Multi(ST_Buffer(ST_Transform(
                    ST_SetSRID(ST_MakePoint(144.97, -37.81), 4326), 7855
                ), 30)), 2800, 'residential', 'active')
                """,
                (versions["property"], versions["property"]),
            )
            cursor.execute(
                """
                INSERT INTO address (
                    dataset_version_id, source_address_id, source_property_id,
                    full_address, locality_name, postcode, is_primary,
                    address_location
                ) VALUES
                (%s, 'ADDRESS-A', 'PARCEL-A', '10 TEST STREET MELBOURNE 3000',
                 'MELBOURNE', '3000', 'Y', ST_Transform(
                    ST_SetSRID(ST_MakePoint(144.96, -37.81), 4326), 7855)),
                (%s, 'ADDRESS-B', 'PARCEL-B', '10 TEST ROAD MELBOURNE 3000',
                 'MELBOURNE', '3000', 'Y', ST_Transform(
                    ST_SetSRID(ST_MakePoint(144.97, -37.81), 4326), 7855))
                """,
                (versions["address"], versions["address"]),
            )
            cursor.execute(
                """
                INSERT INTO urban_tree (
                    dataset_version_id, source_tree_id, tree_location,
                    source_observed_from, source_observed_to, quality_status
                )
                SELECT %s, 'TREE-' || offset_m,
                       ST_Translate(ST_Transform(ST_SetSRID(
                           ST_MakePoint(144.96, -37.81), 4326), 7855),
                           offset_m, 0),
                       DATE '2019-01-01', DATE '2020-12-31', 'passed'
                FROM UNNEST(ARRAY[5, 10, 15]) AS fixture(offset_m)
                """,
                (versions["trees"],),
            )
            cursor.execute(
                """
                INSERT INTO heat_baseline_cell (
                    dataset_version_id, analysis_area_id, cell_geometry,
                    baseline_surface_temperature_c, observed_on,
                    observation_count, scene_count, source_scene_ids,
                    minimum_contributing_temperature_c,
                    maximum_contributing_temperature_c, same_day_spread_c,
                    baseline_method, quality_status
                ) VALUES (
                    %s, %s, ST_Envelope(ST_Buffer(ST_Transform(ST_SetSRID(
                        ST_MakePoint(144.96, -37.81), 4326), 7855), 250)),
                    35.5, DATE '2026-01-15', 4, 1, ARRAY['SCENE-1'],
                    34.0, 37.0, 3.0, 'landsat_latest_daily_mosaic_v1', 'passed'
                )
                """,
                (versions["heat"], area_id),
            )

    def _rows(self, query, parameters=()):
        with self.connection.cursor() as cursor:
            cursor.execute(query, parameters)
            return cursor.fetchall()

    def test_coordinate_function_honours_layers_and_per_layer_limit(self):
        rows = self._rows(
            "SELECT layer FROM get_environment_context(%s,%s,%s,%s,%s)",
            (144.96, -37.81, 500, ["trees", "heat"], 1),
        )
        layers = [row[0] for row in rows]
        self.assertEqual(layers.count("trees"), 1)
        self.assertEqual(layers.count("heat"), 1)
        tree_only = self._rows(
            "SELECT layer FROM get_environment_context(%s,%s,%s,%s,%s)",
            (144.96, -37.81, 500, ["trees"], 2),
        )
        self.assertEqual(tree_only, [("trees",), ("trees",)])

    def test_coordinate_function_rejects_invalid_radius_layer_and_boundary(self):
        cases = (
            ((144.96, -37.81, 0, ["trees"], 1), "radius_m"),
            ((144.96, -37.81, 500, ["canopy"], 1), "unsupported layer"),
            ((144.96, -37.81, 500, ["trees"], 2001), "result_limit"),
            ((150.0, -30.0, 500, ["trees"], 1), "outside"),
        )
        for parameters, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(errors.RaiseException, message):
                    self._rows(
                        "SELECT * FROM get_environment_context(%s,%s,%s,%s,%s)",
                        parameters,
                    )

    def test_address_function_resolves_exact_and_rejects_ambiguous_prefix(self):
        rows = self._rows(
            "SELECT layer FROM get_environment_context_by_address(%s,%s,%s,%s)",
            ("10 TEST STREET MELBOURNE 3000", 500, ["trees", "heat"], 1),
        )
        self.assertEqual({row[0] for row in rows}, {"trees", "heat"})
        with self.assertRaisesRegex(errors.RaiseException, "ambiguous"):
            self._rows(
                "SELECT * FROM get_environment_context_by_address(%s,%s,%s,%s)",
                ("10 TEST", 500, ["trees"], 1),
            )

    def test_historical_temperature_function_returns_metadata(self):
        result = self._rows(
            "SELECT classify_melbourne_daily_mean_air_temperature(32, 22.4)"
        )[0][0]
        self.assertEqual(result["classification"], "Below historical 30 C threshold")
        self.assertEqual(result["status"], "historical_context")
        self.assertEqual(
            result["historical_percentile_context"]["minimum_consecutive_days"],
            2,
        )
        self.assertEqual(
            result["historical_percentile_context"]["source"]["publisher"],
            "BMJ Open",
        )


if __name__ == "__main__":
    unittest.main()
