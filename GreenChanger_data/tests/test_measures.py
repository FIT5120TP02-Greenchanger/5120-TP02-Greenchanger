import unittest

from greenchanger_data.measures import (
    canopy_gain_m2,
    community_totals,
    cost_per_canopy_m2,
    estimated_heat_reduction_c,
    greening_gain_pct,
    heat_projection_output,
    projected_canopy_proxy_shade_m2,
    shade_projection_output,
)
from greenchanger_script.calculate_measures import calculate_all, sample_report


class MeasureTests(unittest.TestCase):
    def test_canopy_gain(self):
        self.assertEqual(canopy_gain_m2(25, 40), 15)

    def test_greening_gain_is_percentage_point_change(self):
        self.assertEqual(greening_gain_pct(18.5, 31.0), 12.5)

    def test_canopy_proxy_shade_applies_all_discount_factors(self):
        result = projected_canopy_proxy_shade_m2(
            40,
            survival_probability=0.9,
            site_suitability_factor=0.85,
            overlap_factor=0.95,
        )
        self.assertAlmostEqual(result, 29.07)

    def test_shade_projection_requires_explicit_future_horizon(self):
        result = shade_projection_output(40, 10, survival_probability=0.9)
        self.assertEqual(result["measurement_type"], "canopy_area_proxy_for_shade")
        self.assertEqual(result["maturity_horizon_years"], 10)
        with self.assertRaises(ValueError):
            shade_projection_output(40, 0)

    def test_estimated_heat_reduction(self):
        self.assertAlmostEqual(estimated_heat_reduction_c(43.2, 40.7), 2.5)

    def test_unvalidated_heat_projection_suppresses_precise_output(self):
        result = heat_projection_output(43.2, 40.7)
        self.assertEqual(result["status"], "indicative_model_not_validated")
        self.assertIsNone(result["projected_surface_temperature_c"])
        self.assertIsNone(result["estimated_heat_reduction_c"])

    def test_validated_heat_projection_exposes_point_estimate(self):
        result = heat_projection_output(
            43.2,
            40.7,
            model_validation_status="validated",
            output_precision="precise_point_estimate",
        )
        self.assertEqual(result["status"], "validated_model_output")
        self.assertAlmostEqual(result["estimated_heat_reduction_c"], 2.5)

    def test_validated_range_does_not_expose_after_temperature(self):
        result = heat_projection_output(
            43.2,
            model_validation_status="validated",
            output_precision="indicative_range",
            cooling_range_min_c=0.4,
            cooling_range_max_c=1.2,
        )
        self.assertEqual(result["status"], "validated_indicative_range")
        self.assertEqual(result["cooling_range_min_c"], 0.4)
        self.assertEqual(result["cooling_range_max_c"], 1.2)
        self.assertIsNone(result["projected_surface_temperature_c"])

    def test_validation_alone_does_not_authorise_temperature_output(self):
        result = heat_projection_output(43.2, 40.7, model_validation_status="validated")
        self.assertEqual(result["status"], "indicative_model_not_validated")
        self.assertIsNone(result["estimated_heat_reduction_c"])

    def test_invalid_cooling_range_is_rejected(self):
        with self.assertRaises(ValueError):
            heat_projection_output(
                43.2,
                model_validation_status="validated",
                output_precision="indicative_range",
                cooling_range_min_c=2,
                cooling_range_max_c=1,
            )

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
        self.assertAlmostEqual(result["shade_projection"]["projected_shade_m2"], 40)
        self.assertIsNone(result["heat_projection"]["estimated_heat_reduction_c"])

    def test_sample_report_has_every_calculation(self):
        calculations = sample_report()["calculations"]
        self.assertEqual(
            set(calculations),
            {
                "canopy_gain_m2",
                "greening_gain_pct",
                "projected_canopy_proxy_shade_m2",
                "surface_cooling_output",
                "cost_per_canopy_m2",
                "community_totals",
            },
        )


if __name__ == "__main__":
    unittest.main()
