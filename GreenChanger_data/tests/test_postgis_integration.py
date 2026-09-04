"""Execute all migrations and public spatial functions against real PostGIS."""

from __future__ import annotations

from decimal import Decimal
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

    def test_fixed_temperature_display_band_boundaries(self):
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT value, classify_temperature_band(value)
                FROM (VALUES
                    (NULL::NUMERIC), (13.6::NUMERIC), (27::NUMERIC),
                    (27.01::NUMERIC), (30::NUMERIC), (30.01::NUMERIC)
                ) AS sample(value)
                """
            )
            self.assertEqual(
                cursor.fetchall(),
                [
                    (None, "Unavailable"),
                    (Decimal("13.6"), "Low"),
                    (Decimal("27"), "Low"),
                    (Decimal("27.01"), "Medium"),
                    (Decimal("30"), "Medium"),
                    (Decimal("30.01"), "High"),
                ],
            )

    def test_fixed_canopy_bands_use_evidence_boundaries(self):
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT value, classify_environmental_value('canopy', value)
                FROM (VALUES
                    (NULL::NUMERIC), (0::NUMERIC), (15.29::NUMERIC),
                    (15.3::NUMERIC), (29.99::NUMERIC), (30::NUMERIC),
                    (100::NUMERIC)
                ) AS sample(value)
                """
            )
            self.assertEqual(
                cursor.fetchall(),
                [
                    (None, "Unavailable"),
                    (Decimal("0"), "Low"),
                    (Decimal("15.29"), "Low"),
                    (Decimal("15.3"), "Medium"),
                    (Decimal("29.99"), "Medium"),
                    (Decimal("30"), "High"),
                    (Decimal("100"), "High"),
                ],
            )

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
                ("address", "Vicmap Address", "Victorian Government", "address",
                 "clip_to_abs_gccsa_2GMEL_2026_v1:test"),
                ("property", "Vicmap Property", "Victorian Government", "property",
                 "clip_to_abs_gccsa_2GMEL_2026_v1:test"),
                ("trees", "Vicmap Vegetation - Tree Urban Point", "Victorian Government",
                 "canopy", "tree_fixture_v1"),
                ("heat", "USGS Landsat Collection 2 Surface Temperature",
                 "United States Geological Survey", "heat",
                 "landsat_latest_daily_mosaic_v1"),
                ("weather", "BOM Melbourne station observations",
                 "Bureau of Meteorology", "weather", "bom_multi_station_fixture_v1"),
            )
            for key, source_name, publisher, category, method in specifications:
                cursor.execute(
                    """
                    WITH fixture_source AS (
                        INSERT INTO dataset_source (
                            source_name, publisher, source_url,
                            source_category, geographic_coverage,
                            access_method, update_frequency
                        ) VALUES (
                            %s, %s, 'https://example.invalid/integration-fixture',
                            %s, 'Melbourne integration fixture',
                            'integration fixture', 'test only'
                        )
                        ON CONFLICT (source_name, publisher) DO UPDATE
                        SET source_name = EXCLUDED.source_name
                        RETURNING source_id
                    )
                    INSERT INTO dataset_version (
                        source_id, analysis_area_id, derivation_method,
                        quality_status, integration_status, publication_status,
                        source_observed_from, source_observed_to
                    )
                    SELECT source_id, %s, %s, 'passed', 'integrated',
                           'application_ready', DATE '2020-01-01', DATE '2026-01-01'
                    FROM fixture_source
                    RETURNING dataset_version_id
                    """,
                    (source_name, publisher, category, area_id, method),
                )
                version = cursor.fetchone()
                if version is None:
                    raise AssertionError(
                        f"integration fixture could not create {source_name!r} version"
                    )
                versions[key] = version[0]

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
                    ST_SetSRID(ST_MakePoint(144.965, -37.81), 4326), 7855
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
                    ST_SetSRID(ST_MakePoint(144.965, -37.81), 4326), 7855))
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
            cursor.execute(
                """
                INSERT INTO weather_observation (
                    dataset_version_id, station_code, station_name,
                    observation_location, observed_at, air_temperature_c,
                    apparent_temperature_c, quality_status
                ) VALUES
                (%s, '95936', 'Melbourne (Olympic Park)',
                 ST_Transform(ST_SetSRID(ST_MakePoint(144.961, -37.81), 4326), 7855),
                 CURRENT_TIMESTAMP - INTERVAL '30 minutes', 21.5, 20.8, 'passed'),
                (%s, '94864', 'Coldstream',
                 ST_Transform(ST_SetSRID(ST_MakePoint(145.41, -37.72), 4326), 7855),
                 CURRENT_TIMESTAMP - INTERVAL '20 minutes', 19.0, 18.1, 'passed')
                """,
                (versions["weather"], versions["weather"]),
            )
            cursor.execute(
                """
                INSERT INTO dataset_version (
                    source_id, analysis_area_id, derivation_method,
                    spatial_resolution_m, quality_pass_rate, quality_status,
                    integration_status, publication_status,
                    source_observed_from, source_observed_to
                )
                SELECT source_id, %s, 'property_canopy_raster_clip_v2',
                       0.5, 100, 'passed', 'integrated', 'application_ready',
                       DATE '2020-01-01', DATE '2020-12-31'
                FROM dataset_source
                WHERE source_name = 'Vicmap Vegetation - Tree Extent'
                RETURNING dataset_version_id
                """,
                (area_id,),
            )
            property_canopy_version = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO property_canopy_summary (
                    dataset_version_id, source_canopy_version_id, parcel_id,
                    observed_on, canopy_area_m2, parcel_area_m2,
                    raster_covered_area_m2, canopy_percentage,
                    coverage_percentage, source_pixel_size_m,
                    quality_status
                )
                SELECT %s, %s, parcel_id, DATE '2020-12-31',
                       700, parcel_area_m2, parcel_area_m2, 25, 100, 0.5, 'passed'
                FROM parcel
                WHERE dataset_version_id = %s AND source_parcel_id = 'PARCEL-A'
                """,
                (
                    property_canopy_version, property_canopy_version,
                    versions["property"],
                ),
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

    def test_address_function_expands_road_abbreviation(self):
        rows = self._rows(
            "SELECT layer FROM get_environment_context_by_address(%s,%s,%s,%s)",
            ("10 test rd melbourne 3000", 500, ["heat"], 1),
        )
        self.assertEqual(rows, [("heat",)])
        normalized = self._rows(
            "SELECT normalize_melbourne_address_search(%s)",
            (" 10  test rd melbourne 3000 ",),
        )[0][0]
        self.assertEqual(normalized, "10 TEST ROAD MELBOURNE 3000")

    def test_address_search_returns_one_group_with_parcel_options(self):
        rows = self._rows(
            """SELECT full_address, parcel_count, cardinality(parcel_ids)
               FROM search_melbourne_addresses(%s, 10)""",
            ("10 test rd melbourne 3000",),
        )
        self.assertEqual(rows, [("10 TEST ROAD MELBOURNE 3000", 1, 1)])

    def test_grouped_address_coordinates_come_from_one_source_row(self):
        duplicate_source_id = "ADDRESS-B-COORDINATE-REGRESSION"
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO address (
                    dataset_version_id, source_address_id, source_property_id,
                    full_address, locality_name, postcode, is_primary,
                    address_location
                )
                SELECT dataset_version_id, %s, source_property_id,
                       full_address, locality_name, postcode, 'N',
                       ST_Transform(
                           ST_SetSRID(ST_MakePoint(145.02, -37.92), 4326), 7855
                       )
                FROM address
                WHERE source_address_id = 'ADDRESS-B'
                """,
                (duplicate_source_id,),
            )
        try:
            row = self._rows(
                """SELECT longitude, latitude, cardinality(address_ids)
                   FROM search_melbourne_addresses(%s, 10)""",
                ("10 test rd melbourne 3000",),
            )[0]
            coordinate = (float(row[0]), float(row[1]))
            came_from_original = (
                abs(coordinate[0] - 144.965) < 0.000001
                and abs(coordinate[1] - (-37.81)) < 0.000001
            )
            came_from_duplicate = (
                abs(coordinate[0] - 145.02) < 0.000001
                and abs(coordinate[1] - (-37.92)) < 0.000001
            )
            self.assertTrue(came_from_original or came_from_duplicate)
            self.assertEqual(row[2], 2)
        finally:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM address WHERE source_address_id = %s",
                    (duplicate_source_id,),
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

    def test_property_canopy_is_parcel_specific_and_missing_safe(self):
        available = self._rows(
            """SELECT property_canopy_percentage, raster_coverage_percentage,
                      source_pixel_size_m, data_status
               FROM get_property_canopy_by_address(%s, 1)""",
            ("10 TEST STREET MELBOURNE 3000",),
        )
        self.assertEqual(available, [(25, 100, 0.5, "Available")])
        baseline = self._rows(
            """SELECT property_canopy_percentage, canopy_analysis_scope,
                      canopy_source_type, canopy_classification
               FROM get_property_baseline(%s, 1)""",
            ("10 TEST STREET MELBOURNE 3000",),
        )
        self.assertEqual(
            baseline,
            [(25, "property_raster_clip", "analytical_geotiff_property_clip", "Unavailable")],
        )
        missing = self._rows(
            """SELECT property_canopy_percentage, data_status, limitation
               FROM get_property_canopy_by_address(%s, 1)""",
            ("10 TEST ROAD MELBOURNE 3000",),
        )[0]
        self.assertIsNone(missing[0])
        self.assertEqual(missing[1], "Unavailable")
        self.assertIn("not zero canopy", missing[2])

    def test_property_air_temperature_is_nearest_recent_station_context(self):
        row = self._rows(
            """SELECT air_temperature_c, apparent_temperature_c,
                      temperature_unit, station_code, observation_age_minutes,
                      station_distance_km, context_status, data_status,
                      measurement_type, source_name, source_publisher, limitation
               FROM get_property_air_temperature_by_address(%s, 1)""",
            ("10 TEST STREET MELBOURNE 3000",),
        )[0]
        self.assertEqual(float(row[0]), 21.5)
        self.assertEqual(float(row[1]), 20.8)
        self.assertEqual(row[2], "degC")
        self.assertEqual(row[3], "95936")
        self.assertGreaterEqual(float(row[4]), 0)
        self.assertLess(float(row[5]), 10)
        self.assertEqual(row[6], "good_local_context")
        self.assertEqual(row[7], "Available")
        self.assertEqual(
            row[8], "nearest_recent_bom_station_air_temperature_context"
        )
        self.assertEqual(row[9], "BOM Melbourne station observations")
        self.assertEqual(row[10], "Bureau of Meteorology")
        self.assertIn("not a temperature measured at the property", row[11])


if __name__ == "__main__":
    unittest.main()
