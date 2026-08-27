import json
from copy import deepcopy
from pathlib import Path
import unittest

from greenchanger_data.intervention_model import (
    calculate_intervention_impact,
    evaluate_validation_cases,
    load_parameter_registry,
)


FIXTURES = Path(__file__).parent / "fixtures"


class InterventionModelTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_parameter_registry()

    def test_registry_defines_exact_supported_actions_and_sources(self):
        self.assertEqual(
            set(self.registry["actions"]),
            {"tree", "potted_plants", "garden_bed", "green_wall"},
        )
        self.assertEqual(self.registry["output_precision"], "indicative_range")
        self.assertEqual(
            self.registry["actions"]["tree"]["temperature_evidence_bound"][
                "source_url"
            ],
            "https://doi.org/10.1016/j.landurbplan.2021.104046",
        )
        self.assertEqual(
            self.registry["actions"]["green_wall"]["temperature_evidence_bound"][
                "source_url"
            ],
            "https://doi.org/10.1016/j.enbuild.2015.06.047",
        )

    def test_potted_plants_never_invent_temperature_effect(self):
        result = calculate_intervention_impact(
            "potted_plants",
            {
                "quantity": 4,
                "foliage_area_per_pot_m2": {"minimum": 0.15, "maximum": 0.3},
            },
            registry=self.registry,
        )
        self.assertEqual(result["impact_area_range_m2"], {"minimum": 0.6, "maximum": 1.2})
        self.assertIsNone(result["temperature_change_range_c"])
        self.assertFalse(result["guaranteed_outcome"])

    def test_green_wall_retains_wall_surface_metric(self):
        result = calculate_intervention_impact(
            "green_wall",
            {
                "installed_wall_area_m2": {"minimum": 10, "maximum": 10},
                "established_cover_fraction": {"minimum": 0.8, "maximum": 1},
                "target_wall_area_m2": 10,
            },
            registry=self.registry,
        )
        temperature = result["temperature_change_range_c"]
        self.assertEqual(temperature["metric"], "wall_surface_temperature")
        self.assertEqual(temperature["maximum"], 15.5)

    def test_fraction_above_one_is_rejected(self):
        with self.assertRaises(ValueError):
            calculate_intervention_impact(
                "garden_bed",
                {
                    "planted_area_m2": {"minimum": 10, "maximum": 10},
                    "established_cover_fraction": {"minimum": 0.8, "maximum": 1.2},
                    "site_area_m2": 100,
                },
                registry=self.registry,
            )

    def test_temperature_bounds_use_respective_coverage_extremes(self):
        registry = deepcopy(self.registry)
        evidence = registry["actions"]["garden_bed"]["temperature_evidence_bound"]
        evidence["minimum_c"] = 2.0
        evidence["maximum_c"] = 6.0
        result = calculate_intervention_impact(
            "garden_bed",
            {
                "planted_area_m2": {"minimum": 10, "maximum": 100},
                "established_cover_fraction": {"minimum": 1, "maximum": 1},
                "site_area_m2": 100,
            },
            registry=registry,
        )
        self.assertEqual(
            result["temperature_change_range_c"],
            {
                "minimum": 0.2,
                "maximum": 6.0,
                "metric": "land_surface_temperature",
                "scope": "daytime land unit during comparable hot-weather conditions",
                "source_key": "ossola_2021_adelaide_vegetated_patches",
                "source_url": "https://doi.org/10.1016/j.landurbplan.2021.104046",
            },
        )

    def test_all_published_evidence_cases_pass(self):
        cases = json.loads(
            (FIXTURES / "intervention_evidence_cases.json").read_text(
                encoding="utf-8"
            )
        )
        report = evaluate_validation_cases(cases, registry=self.registry)
        self.assertTrue(report["all_passed"])
        self.assertEqual(report["case_count"], 4)
        self.assertEqual(report["passed_count"], 4)
        self.assertEqual(report["failed_count"], 0)


if __name__ == "__main__":
    unittest.main()
