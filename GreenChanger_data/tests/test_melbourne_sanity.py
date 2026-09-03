import datetime
import unittest

from greenchanger_data.melbourne_sanity import (
    evaluate_property_scenario,
    validate_scenario_set,
)


SCENARIO = {
    "scenario_code": "TEST_SMALL",
    "zone": "Inner suburbs",
    "address": "1 TEST STREET RICHMOND 3121",
    "expected_localities": ["RICHMOND"],
    "expected_lot_size": "small",
    "context": "test",
}


def valid_row():
    return {
        "address_id": "address-1",
        "parcel_id": "parcel-1",
        "full_address": SCENARIO["address"],
        "locality_name": "RICHMOND",
        "postcode": "3121",
        "parcel_area_m2": 250,
        "lot_size_category": "small",
        "longitude": 145.0,
        "latitude": -37.8,
        "land_surface_temperature_c": 35,
        "surface_temperature_observed_on": datetime.date(2026, 8, 1),
        "temperature_measurement_type": "land_surface_temperature",
        "heat_classification": "High",
        "neighbourhood_canopy_percentage": 30,
        "canopy_classification": "Medium",
        "classification_scheme_version": "melbourne-terciles-v2",
        "classification_scope": "relative_to_greater_melbourne_application_ready_baseline",
        "property_canopy_percentage": 25,
        "canopy_analysis_scope": "property_raster_clip",
        "canopy_observed_on": datetime.date(2020, 11, 2),
        "canopy_source_type": "analytical_geotiff_property_clip",
        "canopy_source_is_proxy": False,
        "mapped_property_tree_count": 2,
        "property_tree_data_status": "mapped_tree_points_available",
        "weather_station_name": "Test station",
        "weather_observed_at": datetime.datetime(
            2026, 8, 27, 1, 0, tzinfo=datetime.timezone.utc
        ),
        "weather_station_distance_km": 5,
        "current_air_temperature_c": 18,
        "air_temperature_context_status": "good_local_context",
        "data_quality_status": "passed",
        "limitations": {},
    }


class MelbourneSanityTests(unittest.TestCase):
    def test_valid_result_passes(self):
        result = evaluate_property_scenario(
            SCENARIO,
            [valid_row()],
            inside_greater_melbourne=True,
            as_of=datetime.date(2026, 8, 27),
        )
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["failures"])

    def test_extreme_property_canopy_zero_trees_and_distant_weather_warn(self):
        row = valid_row()
        row["property_canopy_percentage"] = 95
        row["mapped_property_tree_count"] = 0
        row["weather_station_distance_km"] = 40
        row["current_air_temperature_c"] = None
        row["air_temperature_context_status"] = "too_distant_temperature_suppressed"
        result = evaluate_property_scenario(
            SCENARIO,
            [row],
            inside_greater_melbourne=True,
            as_of=datetime.date(2026, 8, 27),
        )
        self.assertEqual(result["status"], "WARN")
        self.assertEqual(len(result["warnings"]), 3)

    def test_property_and_neighbourhood_canopy_are_validated_separately(self):
        row = valid_row()
        row["neighbourhood_canopy_percentage"] = 30
        row["property_canopy_percentage"] = None
        result = evaluate_property_scenario(
            SCENARIO,
            [row],
            inside_greater_melbourne=True,
            as_of=datetime.date(2026, 8, 27),
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertIn(
            "application-ready property canopy percentage is unavailable",
            result["failures"],
        )

    def test_regional_weather_context_warns(self):
        row = valid_row()
        row["weather_station_distance_km"] = 15
        row["air_temperature_context_status"] = "regional_context_warning"
        result = evaluate_property_scenario(
            SCENARIO,
            [row],
            inside_greater_melbourne=True,
            as_of=datetime.date(2026, 8, 27),
        )
        self.assertEqual(result["status"], "WARN")
        self.assertIn("regional context only", result["warnings"][0])

    def test_duplicate_exact_address_is_a_failure(self):
        row = valid_row()
        result = evaluate_property_scenario(
            SCENARIO,
            [row, dict(row)],
            inside_greater_melbourne=True,
            as_of=datetime.date(2026, 8, 27),
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("expected one exact address match", result["failures"][0])

    def test_missing_heat_and_boundary_fail(self):
        row = valid_row()
        row["land_surface_temperature_c"] = None
        result = evaluate_property_scenario(
            SCENARIO,
            [row],
            inside_greater_melbourne=False,
            as_of=datetime.date(2026, 8, 27),
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertGreaterEqual(len(result["failures"]), 2)

    def test_complete_scenario_set_requires_all_zones_and_lot_sizes(self):
        scenarios = [
            {"zone": "Melbourne CBD", "expected_lot_size": "small"},
            {"zone": "Inner suburbs", "expected_lot_size": "small"},
            {"zone": "Western growth area", "expected_lot_size": "medium"},
            {"zone": "Northern growth area", "expected_lot_size": "medium"},
            {"zone": "Eastern suburbs", "expected_lot_size": "large"},
            {"zone": "Southeastern suburbs", "expected_lot_size": "large"},
        ]
        self.assertEqual(validate_scenario_set(scenarios), [])


if __name__ == "__main__":
    unittest.main()
