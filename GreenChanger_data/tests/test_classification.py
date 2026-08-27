import unittest

from greenchanger_data.classification import classify_environmental_value


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


if __name__ == "__main__":
    unittest.main()
