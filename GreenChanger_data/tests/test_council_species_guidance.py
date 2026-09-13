import csv
from pathlib import Path
import tempfile
import unittest

from greenchanger_data.council_species_guidance import read_rows


class CouncilSpeciesGuidanceTests(unittest.TestCase):
    def _write(self, **overrides):
        row = {
            "source_name": "Example official planting guide",
            "publisher": "Example Council",
            "lga_code": "999",
            "lga_name": "Example",
            "scientific_name": "Eucalyptus example",
            "common_name": "Example gum",
            "mature_size_class": "medium",
            "mature_height_min_m": "8",
            "mature_height_max_m": "12",
            "mature_canopy_width_min_m": "5",
            "mature_canopy_width_max_m": "8",
            "minimum_planting_area_m2": "20",
            "sunlight_requirement": "full sun",
            "water_need_class": "low",
            "root_risk_class": "moderate",
            "site_requirements": "Keep clear of services",
            "guidance_status": "recommended",
            "effective_from": "2026-01-01",
            "effective_to": "",
            "source_url": "https://example.gov.au/guide",
            "licence": "Creative Commons Attribution 4.0 International",
            "limitation": "Confirm site conditions and current council rules.",
        }
        row.update(overrides)
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / "guidance.csv"
        with path.open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=row)
            writer.writeheader()
            writer.writerow(row)
        return directory, path

    def test_guidance_preserves_source_and_dimensions(self):
        directory, path = self._write()
        with directory:
            row = read_rows(path)[0]
        self.assertEqual(row["source_name"], "Example official planting guide")
        self.assertEqual(row["mature_size_class"], "medium")
        self.assertEqual(row["mature_canopy_width_max_m"], 8.0)
        self.assertEqual(row["guidance_status"], "recommended")

    def test_unrecognised_status_cannot_become_available(self):
        directory, path = self._write(guidance_status="available_now")
        with directory, self.assertRaisesRegex(ValueError, "invalid guidance_status"):
            read_rows(path)

    def test_missing_species_name_is_rejected(self):
        directory, path = self._write(scientific_name="", common_name="")
        with directory, self.assertRaisesRegex(ValueError, "name is required"):
            read_rows(path)

    def test_curated_council_guidance_files_preserve_source_contract(self):
        expected = {
            "council_species_guidance_brimbank_2021.csv": (49, "308"),
            "council_species_guidance_casey_private_landscapes.csv": (30, "312"),
            "council_species_guidance_hobsons_bay_street_trees.csv": (84, "331"),
        }
        reference = Path(__file__).parents[1] / "data" / "reference"
        for filename, (row_count, lga_code) in expected.items():
            with self.subTest(filename=filename):
                rows = read_rows(reference / filename)
                self.assertEqual(len(rows), row_count)
                self.assertEqual({row["lga_code"] for row in rows}, {lga_code})
                self.assertTrue(all(row["source_url"] for row in rows))
                self.assertTrue(all(row["licence"] for row in rows))
                self.assertTrue(all(row["limitation"] for row in rows))

    def test_public_street_tree_guidance_requires_council_approval(self):
        reference = Path(__file__).parents[1] / "data" / "reference"
        for filename in (
            "council_species_guidance_brimbank_2021.csv",
            "council_species_guidance_hobsons_bay_street_trees.csv",
        ):
            with self.subTest(filename=filename):
                rows = read_rows(reference / filename)
                self.assertEqual(
                    {row["guidance_status"] for row in rows},
                    {"approval_required"},
                )


if __name__ == "__main__":
    unittest.main()
