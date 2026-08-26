import unittest

from greenchanger_data.heat_baseline import (
    BASELINE_METHOD,
    choose_latest_daily_baseline,
)


class HeatBaselineTests(unittest.TestCase):
    def test_same_day_overlaps_are_averaged(self):
        result = choose_latest_daily_baseline([
            {"cell_id": "A", "observed_on": "2026-08-02", "heat_value": 20, "source_scene_id": "one"},
            {"cell_id": "A", "observed_on": "2026-08-02", "heat_value": 24, "source_scene_id": "two"},
        ])
        self.assertEqual(result[0]["baseline_surface_temperature_c"], 22)
        self.assertEqual(result[0]["observation_count"], 2)
        self.assertEqual(result[0]["source_scene_ids"], ["one", "two"])

    def test_latest_date_is_selected_without_cross_date_average(self):
        result = choose_latest_daily_baseline([
            {"cell_id": "A", "observed_on": "2026-07-10", "heat_value": 8, "source_scene_id": "old"},
            {"cell_id": "A", "observed_on": "2026-08-02", "heat_value": 18, "source_scene_id": "new"},
        ])
        self.assertEqual(result[0]["observed_on"], "2026-08-02")
        self.assertEqual(result[0]["baseline_surface_temperature_c"], 18)

    def test_method_name_is_versioned(self):
        self.assertTrue(BASELINE_METHOD.endswith("_v1"))


if __name__ == "__main__":
    unittest.main()
