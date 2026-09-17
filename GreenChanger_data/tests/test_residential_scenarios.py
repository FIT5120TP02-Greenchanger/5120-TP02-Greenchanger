from datetime import date
import unittest

from greenchanger_data.residential_scenarios import (
    estimate_action_costs,
    evaluate_property_actions,
    load_cost_rows,
)
from greenchanger_data.scenario_inputs import load_input_contract


def property_result(category="small", area=300.0):
    return {
        "scenario_code": "TEST_PROPERTY",
        "zone": "Test zone",
        "requested_address": "1 TEST STREET MELBOURNE 3000",
        "warnings": [],
        "actual": {
            "lot_size_category": category,
            "parcel_area_m2": area,
            "land_surface_temperature_c": 14.0,
            "heat_classification": "High",
            "neighbourhood_canopy_percentage": 25.0,
            "canopy_classification": "Low",
            "canopy_scope": "neighbourhood_500m",
        },
    }


class ResidentialScenarioTests(unittest.TestCase):
    def setUp(self):
        self.contract = load_input_contract()
        self.costs = load_cost_rows()

    def test_tree_heat_range_uses_real_parcel_area(self):
        report = evaluate_property_actions(
            property_result(area=300),
            contract=self.contract,
            cost_rows=self.costs,
            action_types=["tree"],
        )
        tree = report["actions"][0]
        self.assertEqual(
            tree["canopy_shade_or_green_area_gain_m2"],
            {"minimum": 1.65, "maximum": 43.7},
        )
        self.assertEqual(
            tree["indicative_heat_reduction_range_c"]["maximum"],
            0.874,
        )

    def test_costs_scale_by_quantity_or_installed_area(self):
        pots = self.contract["actions"]["potted_plants"]["example_only"]
        pot_cost = estimate_action_costs("potted_plants", pots, self.costs)[0]
        self.assertEqual(pot_cost["minimum_cost_aud"], 196.0)
        self.assertEqual(pot_cost["maximum_cost_aud"], 700.0)
        wall = self.contract["actions"]["green_wall"]["example_only"]
        wall_costs = estimate_action_costs("green_wall", wall, self.costs)
        installed = next(item for item in wall_costs if item["option_code"] == "green_wall" and item["cost_context"].startswith("australian"))
        self.assertEqual(installed["minimum_cost_aud"], 3200.0)
        self.assertEqual(installed["maximum_cost_aud"], 7000.0)

    def test_tree_cost_outputs_keep_type_and_botanical_name(self):
        tree = self.contract["actions"]["tree"]["iteration_1_example"]
        estimates = estimate_action_costs("tree", tree, self.costs)
        water_gum = next(
            item for item in estimates
            if item["tree_type"] == "Water Gum"
            and item["cost_context"] == "melbourne_residential_standard_access"
        )
        self.assertEqual(water_gum["botanical_name"], "Tristaniopsis laurina")
        self.assertEqual(water_gum["minimum_cost_aud"], 108.95)
        self.assertEqual(water_gum["maximum_cost_aud"], 183.95)

    def test_tree_costs_can_be_filtered_by_selected_type(self):
        tree = dict(self.contract["actions"]["tree"]["iteration_1_example"])
        tree["tree_type"] = "Water Gum"
        estimates = estimate_action_costs("tree", tree, self.costs)
        self.assertEqual(len(estimates), 2)
        self.assertEqual(
            {item["tree_type"] for item in estimates},
            {"Water Gum"},
        )

    def test_cost_loader_excludes_expired_species(self):
        costs = load_cost_rows(as_of=date(2026, 9, 15))
        current_tree_types = {
            row["tree_type"]
            for row in costs
            if row["option_code"] in {
                "backyard_tree_diy", "backyard_tree_installed"
            }
        }
        self.assertEqual(
            current_tree_types,
            {"Water Gum", "Lemon-scented Gum", "Crepe Myrtle"},
        )

    def test_all_four_actions_are_validated_and_keep_scope(self):
        report = evaluate_property_actions(
            property_result(), contract=self.contract, cost_rows=self.costs
        )
        self.assertEqual(report["validation_status"], "PASS")
        self.assertEqual(len(report["actions"]), 4)
        by_action = {item["action_type"]: item for item in report["actions"]}
        self.assertIsNone(by_action["potted_plants"]["indicative_heat_reduction_range_c"])
        self.assertEqual(
            by_action["green_wall"]["indicative_heat_reduction_range_c"]["metric"],
            "wall_surface_temperature",
        )

    def test_baseline_warnings_produce_warn_without_invalidating_actions(self):
        baseline = property_result()
        baseline["warnings"] = ["proxy canopy requires imagery review"]
        report = evaluate_property_actions(
            baseline, contract=self.contract, cost_rows=self.costs
        )
        self.assertEqual(report["validation_status"], "WARN")
        self.assertTrue(all(item["output_check_status"] == "PASS" for item in report["actions"]))


if __name__ == "__main__":
    unittest.main()
