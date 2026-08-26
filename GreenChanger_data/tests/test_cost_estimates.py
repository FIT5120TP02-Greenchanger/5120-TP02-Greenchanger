import csv
from datetime import date, datetime
import json
from pathlib import Path
import unittest
from urllib.parse import urlparse

from greenchanger_data.quality import validate_records


ROOT = Path(__file__).resolve().parents[1]
COST_FILE = ROOT / "data" / "reference" / "cost_estimates.csv"


class CostEstimateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with COST_FILE.open(newline="", encoding="utf-8") as handle:
            cls.rows = list(csv.DictReader(handle))
        config = json.loads(
            (ROOT / "config" / "quality_rules.json").read_text(encoding="utf-8")
        )
        cls.rules = config["datasets"]["cost_estimate"]
        cls.threshold = float(config["quality_threshold_pct"])

    def test_cost_file_passes_record_quality_gate(self):
        report = validate_records(
            "cost_estimate", self.rows, self.rules, threshold_pct=self.threshold
        )
        self.assertTrue(report.passed_gate)
        self.assertEqual(report.pass_rate, 100.0)
        self.assertEqual(report.failing_records, 0)

    def test_required_prototype_options_have_cost_context(self):
        option_codes = {row["option_code"] for row in self.rows}
        self.assertTrue(
            {
                "backyard_tree_diy",
                "backyard_tree_installed",
                "container_tree",
                "potted_plants",
                "garden_bed",
                "green_wall",
                "community_tree",
            }.issubset(option_codes)
        )

    def test_sources_and_refresh_dates_are_auditable(self):
        for row in self.rows:
            parsed_url = urlparse(row["source_url"])
            self.assertEqual(parsed_url.scheme, "https")
            self.assertTrue(parsed_url.netloc)
            valid_from = date.fromisoformat(row["valid_from"])
            valid_to = date.fromisoformat(row["valid_to"])
            verified = datetime.fromisoformat(row["last_verified_at"])
            self.assertLess(valid_from, valid_to)
            self.assertLessEqual(valid_from, verified.date())
            self.assertLessEqual((valid_to - valid_from).days, 93)

    def test_disclosed_components_reconcile_to_total_range(self):
        component_prefixes = ("material", "installation", "delivery", "setup")
        for row in self.rows:
            minimum_components = [
                float(row[f"{prefix}_min_cost"])
                for prefix in component_prefixes
                if row[f"{prefix}_min_cost"]
            ]
            maximum_components = [
                float(row[f"{prefix}_max_cost"])
                for prefix in component_prefixes
                if row[f"{prefix}_max_cost"]
            ]
            if minimum_components or maximum_components:
                self.assertAlmostEqual(sum(minimum_components), float(row["minimum_cost"]))
                self.assertAlmostEqual(sum(maximum_components), float(row["maximum_cost"]))


if __name__ == "__main__":
    unittest.main()
