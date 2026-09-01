import unittest

from greenchanger_data.measures import (
    canopy_gain_m2,
    community_totals,
    cost_per_canopy_m2,
    estimated_heat_reduction_c,
    greening_gain_pct,
)


class MeasureTests(unittest.TestCase):
    def test_canopy_gain(self):
        self.assertEqual(canopy_gain_m2(25, 40), 15)

    def test_greening_gain_is_percentage_point_change(self):
        self.assertEqual(greening_gain_pct(18.5, 31.0), 12.5)

    def test_estimated_heat_reduction(self):
        self.assertAlmostEqual(estimated_heat_reduction_c(43.2, 40.7), 2.5)

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


if __name__ == "__main__":
    unittest.main()
