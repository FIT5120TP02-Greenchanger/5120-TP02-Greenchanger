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

    def test_open_tree_research_contract_is_internal_and_conflict_safe(self):
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT source_name, licence_status
                   FROM dataset_source
                   WHERE source_name IN (
                       'AusTraits 7.0.0',
                       'Tree growth of 10 tree species planted in seven Australian cities'
                   )
                   ORDER BY source_name"""
            )
            self.assertEqual(
                cursor.fetchall(),
                [
                    ("AusTraits 7.0.0", "open_confirmed"),
                    (
                        "Tree growth of 10 tree species planted in seven Australian cities",
                        "open_confirmed",
                    ),
                ],
            )
            cursor.execute(
                """SELECT COUNT(*)
                   FROM predictive_model_source AS link
                   JOIN dataset_source AS source USING (source_id)
                   WHERE link.model_code = 'tree_canopy_growth'
                     AND NOT link.required_for_training
                     AND link.training_use_allowed
                     AND source.source_name IN (
                         'AusTraits 7.0.0',
                         'Tree growth of 10 tree species planted in seven Australian cities'
                     )"""
            )
            self.assertEqual(cursor.fetchone()[0], 2)
            cursor.execute(
                """SELECT to_regclass('plant_trait_observation'),
                          to_regclass('urban_tree_growth_observation'),
                          to_regclass('urban_tree_growth_climate'),
                          to_regclass('usable_urban_tree_growth_climate')"""
            )
            self.assertTrue(all(cursor.fetchone()))

    def test_dea_and_era5_tables_enforce_separate_spatial_contracts(self):
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT to_regclass('dea_land_cover_observation'),
                          to_regclass('era5_land_daily_observation'),
                          to_regclass('latest_dea_land_cover'),
                          to_regclass('latest_era5_land_daily')"""
            )
            self.assertTrue(all(cursor.fetchone()))
            cursor.execute(
                """SELECT
                       Find_SRID(current_schema()::text, 'dea_land_cover_observation',
                                 'observation_geometry'),
                       Find_SRID(current_schema()::text, 'era5_land_daily_observation',
                                 'observation_location')"""
            )
            self.assertEqual(cursor.fetchone(), (7855, 7855))
            cursor.execute(
                """SELECT source_name, licence_status
                   FROM dataset_source
                   WHERE source_name IN (
                       'DEA Land Cover (Landsat)',
                       'ERA5-Land hourly data from 1950 to present'
                   ) ORDER BY source_name"""
            )
            self.assertEqual(
                cursor.fetchall(),
                [
                    ("DEA Land Cover (Landsat)", "open_confirmed"),
                    ("ERA5-Land hourly data from 1950 to present", "open_confirmed"),
                ],
            )

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

    def test_historical_canopy_sources_and_metric_geometry_contract(self):
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT source_id, source_name
                   FROM dataset_source
                   WHERE publisher = 'City of Melbourne'
                     AND source_name IN (
                         'Tree Canopies 2008 (Urban Forest)',
                         'Tree Canopies 2015 (Urban Forest)',
                         'Tree Canopies 2016 (Urban Forest)',
                         'Tree Canopies 2021 (Urban Forest)'
                     )
                   ORDER BY source_name"""
            )
            sources = cursor.fetchall()
            self.assertEqual(len(sources), 4)
            source_id = next(
                source_id for source_id, name in sources
                if name == "Tree Canopies 2016 (Urban Forest)"
            )
            cursor.execute(
                """INSERT INTO dataset_version (
                       source_id, source_observed_from, source_observed_to,
                       quality_status, integration_status, publication_status,
                       derivation_method
                   ) VALUES (
                       %s, DATE '2016-01-01', DATE '2016-12-31',
                       'passed_with_limitations', 'integrated', 'internal',
                       'integration_fixture'
                   ) RETURNING dataset_version_id""",
                (source_id,),
            )
            version_id = cursor.fetchone()[0]
            cursor.execute(
                """INSERT INTO canopy_snapshot_feature (
                       dataset_version_id, source_feature_key, observed_year,
                       observed_on, canopy_geometry, calculated_area_m2
                   ) VALUES (
                       %s, 'fixture-polygon', 2016, DATE '2016-12-31',
                       ST_Multi(ST_Buffer(ST_Transform(ST_SetSRID(
                           ST_MakePoint(144.96, -37.81), 4326
                       ), 7855), 5)), 78.54
                   )""",
                (version_id,),
            )
            cursor.execute(
                """SELECT observed_year, ST_SRID(canopy_geometry),
                          publication_status
                   FROM latest_city_canopy_snapshots
                   JOIN dataset_version USING (dataset_version_id)
                   WHERE source_feature_key = 'fixture-polygon'"""
            )
            self.assertEqual(cursor.fetchone(), (2016, 7855, "internal"))

    def test_metropolitan_vegetation_change_has_separate_versioned_grain(self):
        with self.connection.cursor() as cursor:
            cursor.execute(
                """SELECT source_id
                   FROM dataset_source
                   WHERE source_name =
                     'Change in Vegetation Cover in Metropolitan Melbourne between 2014 and 2018'"""
            )
            source_id = cursor.fetchone()[0]
            cursor.execute(
                """INSERT INTO dataset_version (
                       source_id, source_observed_from, source_observed_to,
                       quality_status, integration_status, publication_status,
                       derivation_method
                   ) VALUES (
                       %s, DATE '2014-01-01', DATE '2018-12-31',
                       'passed_with_limitations', 'integrated', 'internal',
                       'integration_fixture'
                   ) RETURNING dataset_version_id""",
                (source_id,),
            )
            version_id = cursor.fetchone()[0]
            cursor.execute(
                """INSERT INTO metropolitan_vegetation_change_feature (
                       dataset_version_id, source_feature_key, mesh_block_code,
                       tree_change_pct_points, change_geometry
                   ) VALUES (
                       %s, 'fixture-change', '200000001', 4.5,
                       ST_Multi(ST_Buffer(ST_Transform(ST_SetSRID(
                           ST_MakePoint(144.96, -37.81), 4326
                       ), 7855), 100))
                   )""",
                (version_id,),
            )
            cursor.execute(
                """SELECT mesh_block_code, tree_change_pct_points,
                          ST_SRID(change_geometry), publication_status
                   FROM latest_metropolitan_vegetation_change
                   JOIN dataset_version USING (dataset_version_id)
                   WHERE source_feature_key = 'fixture-change'"""
            )
            self.assertEqual(
                cursor.fetchone(), ("200000001", Decimal("4.5"), 7855, "internal")
            )

    def test_metropolitan_named_tree_lookup_preserves_council_source(self):
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT municipality, display_name, taxonomic_precision,
                       height_m, canopy_width_m, status, limitation
                FROM get_metropolitan_named_tree_context(
                    144.96, -37.81, 100, 10
                )
                """
            )
            rows = cursor.fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][:6], (
                "City of Brimbank", "River Red Gum", "species",
                Decimal("12"), Decimal("8"), "observed_council_inventory",
            ))
            self.assertIn("not every private tree", rows[0][6])

    def test_cost_business_key_separates_tree_types_and_deduplicates_null(self):
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT greening_option_id FROM greening_option "
                "WHERE option_code = 'backyard_tree_diy'"
            )
            tree_option_id = cursor.fetchone()[0]
            cursor.execute(
                "SELECT greening_option_id FROM greening_option "
                "WHERE option_code = 'potted_plants'"
            )
            non_tree_option_id = cursor.fetchone()[0]

            common_values = (
                "integration_test", "per_item", "Integration source",
                "integration-business-key", "2026-09-08",
            )
            cursor.execute(
                """
                INSERT INTO cost_estimate (
                    greening_option_id, cost_context, cost_basis, tree_type,
                    minimum_cost, maximum_cost, source_name, source_reference,
                    valid_from, last_verified_at, confidence_level
                ) VALUES
                    (%s, %s, %s, 'Tree A', 10, 20, %s, %s, %s,
                     CURRENT_TIMESTAMP, 'high'),
                    (%s, %s, %s, 'Tree B', 30, 40, %s, %s, %s,
                     CURRENT_TIMESTAMP, 'high')
                """,
                (
                    tree_option_id, *common_values[:2], *common_values[2:],
                    tree_option_id, *common_values[:2], *common_values[2:],
                ),
            )
            cursor.execute(
                """
                SELECT COUNT(*), COUNT(DISTINCT tree_type)
                FROM cost_estimate
                WHERE source_name = 'Integration source'
                  AND source_reference = 'integration-business-key'
                  AND greening_option_id = %s
                """,
                (tree_option_id,),
            )
            self.assertEqual(cursor.fetchone(), (2, 2))

            upsert_parameters = (
                non_tree_option_id, *common_values[:2], *common_values[2:]
            )
            for maximum_cost in (20, 25):
                cursor.execute(
                    """
                    INSERT INTO cost_estimate (
                        greening_option_id, cost_context, cost_basis, tree_type,
                        minimum_cost, maximum_cost, source_name,
                        source_reference, valid_from, last_verified_at,
                        confidence_level
                    ) VALUES (%s, %s, %s, NULL, 10, %s, %s, %s, %s,
                              CURRENT_TIMESTAMP, 'high')
                    ON CONFLICT (
                        greening_option_id, cost_context, cost_basis, tree_type,
                        source_name, valid_from, source_reference
                    ) DO UPDATE SET maximum_cost = EXCLUDED.maximum_cost
                    """,
                    (
                        *upsert_parameters[:3], maximum_cost,
                        *upsert_parameters[3:],
                    ),
                )
            cursor.execute(
                """
                SELECT COUNT(*), MAX(maximum_cost)
                FROM cost_estimate
                WHERE source_name = 'Integration source'
                  AND source_reference = 'integration-business-key'
                  AND greening_option_id = %s
                  AND tree_type IS NULL
                """,
                (non_tree_option_id,),
            )
            self.assertEqual(cursor.fetchone(), (1, Decimal("25")))

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
                ("tree_extent", "Vicmap Vegetation - Tree Extent",
                 "Victorian Government", "canopy",
                 "property_canopy_raster_clip_v2:test"),
                ("heat", "USGS Landsat Collection 2 Surface Temperature",
                 "United States Geological Survey", "heat",
                 "landsat_latest_daily_mosaic_v1"),
                ("weather", "BOM Melbourne station observations",
                 "Bureau of Meteorology", "weather", "bom_multi_station_fixture_v1"),
                ("named_trees", "Brimbank Street Trees",
                 "Brimbank City Council", "tree_inventory",
                 "brimbank_inventory_filter_to_abs_2GMEL_2026_v1"),
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
                INSERT INTO species_profile (
                    scientific_name, common_name, genus, source_reference
                ) VALUES (
                    'Eucalyptus camaldulensis', 'River Red Gum',
                    'Eucalyptus', 'PostGIS integration fixture'
                )
                RETURNING species_id
                """
            )
            species_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO named_tree_inventory (
                    dataset_version_id, source_tree_id, species_id,
                    inventory_source_key, municipality, common_name,
                    scientific_name, display_name, genus, taxonomic_precision,
                    height_m, canopy_width_m, tree_location, quality_status
                ) VALUES (
                    %s, 'BRIMBANK-FIXTURE-1', %s, 'brimbank',
                    'City of Brimbank', 'River Red Gum',
                    'Eucalyptus camaldulensis', 'River Red Gum',
                    'Eucalyptus', 'species', 12, 8,
                    ST_Transform(ST_SetSRID(
                        ST_MakePoint(144.9601, -37.81), 4326
                    ), 7855), 'passed'
                )
                """,
                (versions["named_trees"], species_id),
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
                FROM dataset_version
                WHERE dataset_version_id = %s
                RETURNING dataset_version_id
                """,
                (area_id, versions["tree_extent"]),
            )
            property_canopy_version = cursor.fetchone()
            if property_canopy_version is None:
                raise AssertionError(
                    "integration fixture could not create property canopy version"
                )
            property_canopy_version = property_canopy_version[0]
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
                    property_canopy_version, versions["tree_extent"],
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
