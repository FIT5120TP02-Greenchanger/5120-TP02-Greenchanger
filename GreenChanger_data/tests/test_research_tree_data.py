import csv
import tempfile
from pathlib import Path
import unittest
import zipfile

from greenchanger_data.research_tree_data import (
    AUSTRAITS_MEMBER,
    combined_checksum,
    iter_austraits_rows,
    normalise_climate_rows,
    normalise_growth_rows,
)


class ResearchTreeDataTests(unittest.TestCase):
    def test_austraits_stream_selects_relevant_traits_and_preserves_context(self):
        columns = [
            "dataset_id", "taxon_name", "observation_id", "trait_name", "value",
            "unit", "entity_type", "value_type", "basis_of_value", "replicates",
            "basis_of_record", "life_stage", "location_id", "collection_date",
            "source_id", "measurement_remarks", "original_name",
        ]
        records = [
            {
                "dataset_id": "study-1", "taxon_name": "Eucalyptus example",
                "observation_id": "o-1", "trait_name": "plant_height",
                "value": "12.5", "unit": "m", "entity_type": "species",
                "life_stage": "adult", "source_id": "source-1",
            },
            {
                "dataset_id": "study-1", "taxon_name": "Eucalyptus example",
                "observation_id": "o-2", "trait_name": "irrelevant_trait",
                "value": "99", "unit": "x",
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "austraits.zip"
            csv_path = Path(directory) / "traits.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as output:
                writer = csv.DictWriter(output, fieldnames=columns)
                writer.writeheader()
                writer.writerows(records)
            with zipfile.ZipFile(archive, "w") as output:
                output.write(csv_path, AUSTRAITS_MEMBER)
            rows = list(iter_austraits_rows(archive))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["taxon_name"], "Eucalyptus example")
        self.assertEqual(rows[0]["value_numeric"], 12.5)
        self.assertEqual(rows[0]["life_stage"], "adult")

    def test_growth_rows_correct_known_taxonomic_typos_and_sequence_per_tree(self):
        rows = normalise_growth_rows([
            {"City": "Melbourne", "Species": "Robinia pseudoacia", "Ttree": 1, "TRW": 0.4, "BAI": None},
            {"City": "Melbourne", "Species": "Robinia pseudoacia", "Ttree": 1, "TRW": 0.5, "BAI": 0.2},
            {"City": "Melbourne", "Species": "Ulmus parvifolia.", "Ttree": 2, "TRW": 0.6, "BAI": 0.3},
        ])
        self.assertEqual(rows[0]["species_name"], "Robinia pseudoacacia")
        self.assertEqual(rows[2]["species_name"], "Ulmus parvifolia")
        self.assertEqual([row["ring_sequence"] for row in rows], [1, 2, 1])
        self.assertIsNone(rows[0]["basal_area_increment_cm2_year"])

    def test_climate_exact_duplicates_collapse_but_conflicts_are_flagged(self):
        base = {
            "City": "Mildura", "Year": 2020, "AP": 300, "PDM": 5,
            "PWM": 40, "PDQ": 20, "MTWM": 29, "MAT": 18,
            "MTCM": 9, "IDM": 0.5, "IP": 70,
        }
        conflict = {**base, "AP": 600}
        rows = normalise_climate_rows([base, base.copy(), conflict])
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["city_year_ambiguous"] for row in rows))
        self.assertEqual(sorted(row["source_occurrence_count"] for row in rows), [1, 2])

    def test_combined_checksum_is_filename_order_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "a.txt"
            second = Path(directory) / "b.txt"
            first.write_text("alpha", encoding="utf-8")
            second.write_text("beta", encoding="utf-8")
            self.assertEqual(
                combined_checksum([first, second]),
                combined_checksum([second, first]),
            )


if __name__ == "__main__":
    unittest.main()
