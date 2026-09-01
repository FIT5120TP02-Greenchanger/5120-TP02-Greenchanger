import unittest

from greenchanger_data.classification import (
    classify_canopy_benchmark,
    classify_environmental_value,
    classify_melbourne_daily_mean_air_temperature,
)


class EnvironmentalClassificationTests(unittest.TestCase):
    def test_missing_value_is_unavailable(self):
        self.assertEqual(classify_environmental_value(None, 20, 30), "Unavailable")

    def test_missing_threshold_is_unavailable(self):
        self.assertEqual(classify_environmental_value(25, None, 30), "Unavailable")
        self.assertEqual(classify_environmental_value(25, 20, None), "Unavailable")

    def test_boundaries_are_exclusive_between_classes(self):
        self.assertEqual(classify_environmental_value(19.99, 20, 30), "Low")
        self.assertEqual(classify_environmental_value(20, 20, 30), "Low")
        self.assertEqual(classify_environmental_value(20.01, 20, 30), "Medium")
        self.assertEqual(classify_environmental_value(30, 20, 30), "Medium")
        self.assertEqual(classify_environmental_value(30.01, 20, 30), "High")

    def test_equal_thresholds_still_classify_deterministically(self):
        self.assertEqual(classify_environmental_value(20, 20, 20), "Low")
        self.assertEqual(classify_environmental_value(20.01, 20, 20), "High")

    def test_reversed_thresholds_are_rejected(self):
        with self.assertRaises(ValueError):
            classify_environmental_value(25, 30, 20)

    def test_non_numeric_input_is_rejected(self):
        with self.assertRaises(TypeError):
            classify_environmental_value("25", 20, 30)

    def test_non_finite_values_and_thresholds_are_unavailable(self):
        cases = (
            (float("nan"), 20, 30),
            (float("inf"), 20, 30),
            (float("-inf"), 20, 30),
            (25, float("nan"), 30),
            (25, float("inf"), 30),
            (25, 20, float("nan")),
            (25, 20, float("inf")),
        )
        for value, lower, upper in cases:
            with self.subTest(value=value, lower=lower, upper=upper):
                self.assertEqual(
                    classify_environmental_value(value, lower, upper),
                    "Unavailable",
                )


class MelbourneDailyMeanAirTemperatureTests(unittest.TestCase):
    def test_daily_mean_boundaries(self):
        self.assertEqual(
            classify_melbourne_daily_mean_air_temperature(32.0, 22.2), "Low"
        )
        self.assertEqual(
            classify_melbourne_daily_mean_air_temperature(32.0, 22.4), "Medium"
        )
        self.assertEqual(
            classify_melbourne_daily_mean_air_temperature(38.0, 22.0), "High"
        )

    def test_official_example_is_high(self):
        self.assertEqual(
            classify_melbourne_daily_mean_air_temperature(38.0, 25.0), "High"
        )

    def test_missing_or_non_finite_input_is_unavailable(self):
        self.assertEqual(
            classify_melbourne_daily_mean_air_temperature(None, 25.0),
            "Unavailable",
        )
        self.assertEqual(
            classify_melbourne_daily_mean_air_temperature(float("nan"), 25.0),
            "Unavailable",
        )


class CanopyBenchmarkTests(unittest.TestCase):
    def test_canopy_boundaries(self):
        self.assertEqual(classify_canopy_benchmark(15.29), "Low")
        self.assertEqual(classify_canopy_benchmark(15.3), "Medium")
        self.assertEqual(classify_canopy_benchmark(29.99), "Medium")
        self.assertEqual(classify_canopy_benchmark(30.0), "High")

    def test_missing_is_unavailable_and_invalid_range_is_rejected(self):
        self.assertEqual(classify_canopy_benchmark(None), "Unavailable")
        self.assertEqual(classify_canopy_benchmark(float("inf")), "Unavailable")
        with self.assertRaises(ValueError):
            classify_canopy_benchmark(100.1)


if __name__ == "__main__":
    unittest.main()
