import unittest

from greenchanger_data.measures import (
    canopy_gain_m2,
    community_totals,
    cost_per_canopy_m2,
    estimated_heat_reduction_c,
    greening_gain_pct,
    heat_projection_output,
)
from greenchanger_script.calculate_measures import calculate_all, sample_report


class MeasureTests(unittest.TestCase):
    def test_canopy_gain(self):
        self.assertEqual(canopy_gain_m2(25, 40), 15)

    def test_greening_gain_is_percentage_point_change(self):
        self.assertEqual(greening_gain_pct(18.5, 31.0), 12.5)

    def test_estimated_heat_reduction(self):
        self.assertAlmostEqual(estimated_heat_reduction_c(43.2, 40.7), 2.5)

    def test_unvalidated_heat_projection_suppresses_precise_output(self):
        result = heat_projection_output(43.2, 40.7)
        self.assertEqual(result["status"], "indicative_model_not_validated")
        self.assertIsNone(result["projected_surface_temperature_c"])
        self.assertIsNone(result["estimated_heat_reduction_c"])

    def test_validated_heat_projection_exposes_point_estimate(self):
        result = heat_projection_output(
            43.2, 40.7, model_validation_status="validated"
        )
        self.assertEqual(result["status"], "validated_model_output")
        self.assertAlmostEqual(result["estimated_heat_reduction_c"], 2.5)

    def test_cost_per_canopy(self):
        self.assertEqual(cost_per_canopy_m2(1200, 15), 80)

    def test_community_totals(self):
        result = community_totals(
            [
                {
                    "quantity": 2,
                    "intervention_area_m2": 20,
                    "minimum_cost": 400,
                    "maximum_cost": 700,
                },
                {
                    "quantity": 1,
                    "intervention_area_m2": 8,
                    "minimum_cost": 250,
                    "maximum_cost": 400,
                },
            ]
        )
        self.assertEqual(result["quantity"], 3)
        self.assertEqual(result["intervention_area_m2"], 28)
        self.assertEqual(result["minimum_cost"], 650)
        self.assertEqual(result["maximum_cost"], 1100)

    def test_invalid_percentage_is_rejected(self):
        with self.assertRaises(ValueError):
            greening_gain_pct(20, 120)

    def test_calculate_all_includes_optional_calculations(self):
        result = calculate_all(
            {
                "baseline_canopy_m2": 25,
                "projected_canopy_m2": 40,
                "baseline_greenery_pct": 18.5,
                "projected_greenery_pct": 31,
                "baseline_surface_temperature_c": 43.2,
                "projected_surface_temperature_c": 40.7,
                "total_cost": 1200,
                "community_interventions": [],
            }
        )
        self.assertEqual(result["cost_per_canopy_m2"], 80)
        self.assertIn("community_totals", result)
        self.assertIsNone(result["heat_projection"]["estimated_heat_reduction_c"])

    def test_sample_report_has_every_calculation(self):
        calculations = sample_report()["calculations"]
        self.assertEqual(
            set(calculations),
            {
                "canopy_gain_m2",
                "greening_gain_pct",
                "estimated_heat_reduction_c",
                "cost_per_canopy_m2",
                "community_totals",
            },
        )


if __name__ == "__main__":
    unittest.main()
