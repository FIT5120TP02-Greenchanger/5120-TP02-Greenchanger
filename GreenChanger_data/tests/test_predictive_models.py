import unittest

from greenchanger_data.predictive_models import (
    MODEL_CODES,
    assess_all_models,
    assess_model_readiness,
    load_predictive_model_registry,
    load_source_licence_statuses,
)


class PredictiveModelContractTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_predictive_model_registry()
        self.licences = load_source_licence_statuses()

    def test_exactly_four_independent_models_are_defined(self):
        self.assertEqual(set(self.registry["models"]), MODEL_CODES)
        self.assertTrue(self.registry["policy"]["general_model_prohibited"])
        self.assertEqual(
            len({model["target"] for model in self.registry["models"].values()}),
            4,
        )
        referenced = {
            row["key"]
            for model in self.registry["models"].values()
            for row in model["datasets"]
        }
        self.assertEqual(referenced - set(self.licences), set())

    def test_cooling_model_keeps_landsat_target_and_weather_controls_separate(self):
        model = self.registry["models"]["cooling_association"]
        self.assertEqual(model["target"], "landsat_land_surface_temperature_c")
        roles = {row["key"]: row["role"] for row in model["datasets"]}
        self.assertEqual(roles["landsat_surface_temperature"], "land-surface-temperature target")
        self.assertIn("weather controls", roles["era5_land"])

    def test_missing_training_data_never_returns_a_prediction(self):
        result = assess_model_readiness(
            "tree_canopy_growth",
            available_dataset_keys=set(),
            registry=self.registry,
            licence_statuses=self.licences,
        )
        self.assertFalse(result["production_ready"])
        self.assertEqual(result["prediction_status"], "unavailable_model_not_trained")
        self.assertIn("required_training_data_missing", result["blockers"])

    def test_burnley_model_is_blocked_until_record_licence_is_confirmed(self):
        result = assess_model_readiness(
            "garden_cooling",
            available_dataset_keys={"burnley_irrigation_experiment"},
            registry=self.registry,
            licence_statuses=self.licences,
        )
        self.assertFalse(result["training_data_ready"])
        self.assertIn(
            "burnley_irrigation_experiment",
            result["unconfirmed_licence_dataset_keys"],
        )

    def test_even_available_open_data_requires_held_out_validation(self):
        required = {
            row["key"]
            for model in self.registry["models"].values()
            for row in model["datasets"]
            if row["required"]
        }
        statuses = {key: "open_confirmed" for key in required}
        report = assess_all_models(
            available_dataset_keys=required,
            registry=self.registry,
            licence_statuses=statuses,
        )
        self.assertEqual(report["production_ready_count"], 0)
        self.assertTrue(
            all("held_out_validation_not_passed" in row["blockers"] for row in report["models"])
        )


if __name__ == "__main__":
    unittest.main()
