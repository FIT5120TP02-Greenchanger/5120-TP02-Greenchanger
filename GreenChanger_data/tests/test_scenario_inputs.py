import unittest

from greenchanger_data.scenario_inputs import (
    calculate_simulated_action,
    load_input_contract,
    prepare_model_inputs,
)


class ResidentialGreeningScenarioInputTests(unittest.TestCase):
    def setUp(self):
        self.contract = load_input_contract()

    def test_contract_has_four_actions_and_prohibits_exact_temperature(self):
        self.assertEqual(
            set(self.contract["actions"]),
            {"tree", "potted_plants", "garden_bed", "green_wall"},
        )
        self.assertFalse(
            self.contract["output_policy"]["exact_after_temperature_permitted"]
        )

    def test_iteration_one_allows_only_one_tree(self):
        inputs = dict(self.contract["actions"]["tree"]["iteration_1_example"])
        inputs["quantity"] = 2
        with self.assertRaisesRegex(ValueError, "exceeds the action maximum"):
            prepare_model_inputs("tree", inputs, contract=self.contract)

    def test_tree_example_uses_published_ten_year_crown_range(self):
        inputs = dict(self.contract["actions"]["tree"]["iteration_1_example"])
        result = calculate_simulated_action("tree", inputs, contract=self.contract)
        self.assertEqual(
            result["projected_canopy_range_m2"],
            {"minimum": 6.6, "maximum": 43.7},
        )
        self.assertEqual(result["maturity_horizon_years"], 10)
        self.assertFalse(result["exact_after_temperature_permitted"])

    def test_potted_example_accounts_for_establishment_uncertainty(self):
        inputs = self.contract["actions"]["potted_plants"]["example_only"]
        result = calculate_simulated_action(
            "potted_plants", inputs, contract=self.contract
        )
        self.assertEqual(
            result["impact_area_range_m2"],
            {"minimum": 0.294, "maximum": 1.2},
        )
        self.assertIsNone(result["temperature_change_range_c"])

    def test_garden_and_wall_keep_distinct_temperature_metrics(self):
        garden = calculate_simulated_action(
            "garden_bed",
            self.contract["actions"]["garden_bed"]["example_only"],
            contract=self.contract,
        )
        wall = calculate_simulated_action(
            "green_wall",
            self.contract["actions"]["green_wall"]["example_only"],
            contract=self.contract,
        )
        self.assertEqual(
            garden["temperature_change_range_c"]["metric"],
            "land_surface_temperature",
        )
        self.assertEqual(
            wall["temperature_change_range_c"]["metric"],
            "wall_surface_temperature",
        )

    def test_missing_common_uncertainty_is_rejected(self):
        inputs = dict(self.contract["actions"]["tree"]["iteration_1_example"])
        inputs.pop("survival_probability")
        with self.assertRaisesRegex(ValueError, "survival_probability"):
            prepare_model_inputs("tree", inputs, contract=self.contract)


if __name__ == "__main__":
    unittest.main()
