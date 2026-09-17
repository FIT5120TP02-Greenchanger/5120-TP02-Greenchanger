import math
import unittest

import pandas as pd

from greenchanger_data.tree_canopy_model import (
    TARGET,
    added_canopy_m2,
    build_species_profiles,
    canopy_area_m2,
    prepare_mature_training_frame,
    predict_canopy,
    train_and_evaluate,
)


class TreeCanopyModelTests(unittest.TestCase):
    def test_canopy_area_and_added_canopy_use_circular_crown(self):
        self.assertAlmostEqual(canopy_area_m2(4), 4 * math.pi)
        self.assertAlmostEqual(added_canopy_m2(2, 4), 3 * math.pi)
        self.assertEqual(added_canopy_m2(4, 2), 0)

    def test_training_frame_keeps_only_unique_explicitly_mature_records(self):
        base = {
            "inventory_source_key": "test",
            "common_name": "Tree A",
            "height_m": 8,
            "diameter_breast_height_cm": 30,
            "canopy_width_m": 6,
            "health_status": "Good",
            "structure_status": "Good",
        }
        records = [
            {**base, "source_tree_id": "1", "age_description": "Mature"},
            {**base, "source_tree_id": "1", "age_description": "Mature"},
            {**base, "source_tree_id": "2", "age_description": "Young"},
            {**base, "source_tree_id": "3", "age_description": "Over mature"},
        ]
        frame = prepare_mature_training_frame(records)
        self.assertEqual(len(frame), 2)
        self.assertEqual(frame[TARGET].tolist(), [6.0, 6.0])

    def test_species_profile_uses_representative_features_not_target(self):
        frame = pd.DataFrame(
            [
                {
                    "species_name": "Tree A",
                    "height_m": 6,
                    "diameter_breast_height_cm": 20,
                    "longitude": 144.5,
                    "latitude": -37.8,
                    "health_status": "Good",
                    "structure_status": "Fair",
                    "useful_life_expectancy": "20-30 years",
                    TARGET: 5,
                },
                {
                    "species_name": "Tree A",
                    "height_m": 10,
                    "diameter_breast_height_cm": 40,
                    "longitude": 144.7,
                    "latitude": -37.6,
                    "health_status": "Good",
                    "structure_status": "Fair",
                    "useful_life_expectancy": "20-30 years",
                    TARGET: 9,
                },
            ]
        )
        profile = build_species_profiles(frame)["Tree A"]
        self.assertEqual(profile["height_m"], 8)
        self.assertEqual(profile["diameter_breast_height_cm"], 30)
        self.assertNotIn(TARGET, profile)

    def test_training_reports_r2_and_prediction_derives_added_area(self):
        rows = []
        for index in range(180):
            height = 3.0 + index / 20
            dbh = 8.0 + index / 5
            rows.append(
                {
                    "source_tree_id": str(index),
                    "inventory_source_key": "test",
                    "species_name": f"Species {index % 6}",
                    "height_m": height,
                    "diameter_breast_height_cm": dbh,
                    "longitude": 144.5 + (index % 20) / 100,
                    "latitude": -37.9 + (index % 20) / 100,
                    "health_status": "Good",
                    "structure_status": "Good",
                    "useful_life_expectancy": "20-30 years",
                    TARGET: 1.0 + 0.5 * height + 0.04 * dbh,
                }
            )
        frame = pd.DataFrame(rows)
        model, metrics = train_and_evaluate(frame, random_state=7)
        self.assertEqual(metrics.total_rows, 180)
        self.assertEqual(metrics.training_rows, 144)
        self.assertEqual(metrics.validation_rows, 36)
        self.assertEqual(metrics.test_rows, 36)
        self.assertGreater(metrics.supported_species_r2, 0.9)
        prediction = predict_canopy(
            model,
            species_name="Species 1",
            height_m=9,
            diameter_breast_height_cm=35,
            current_canopy_width_m=2,
            useful_life_expectancy="20-30 years",
            longitude=144.6,
            latitude=-37.8,
        )
        self.assertGreater(prediction["predicted_mature_canopy_width_m"], 2)
        self.assertGreater(prediction["predicted_added_canopy_m2"], 0)

    def test_too_few_rows_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "at least 100"):
            train_and_evaluate(pd.DataFrame([{TARGET: 1}] * 10))


if __name__ == "__main__":
    unittest.main()
