import csv
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PRICE_FILE = ROOT / "data" / "reference" / "tree_supplier_size_prices.csv"
ALIAS_FILE = ROOT / "data" / "reference" / "tree_price_taxon_aliases.csv"
EXACT_SIZE_STATUSES = {
    "exact_variant_size_price",
    "exact_listed_size_price",
    "single_product_price_with_size_label",
}


class TreeSupplierSizePriceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with PRICE_FILE.open(newline="", encoding="utf-8") as handle:
            cls.rows = list(csv.DictReader(handle))

    def test_every_price_is_species_and_supplier_specific(self):
        self.assertTrue(self.rows)
        for row in self.rows:
            self.assertTrue(row["botanical_name"].strip())
            self.assertTrue(row["tree_type"].strip())
            self.assertTrue(row["source_name"].strip())
            self.assertTrue(row["source_url"].startswith("https://"))
            self.assertNotIn("generic", row["cost_context"].casefold())

    def test_size_specific_rows_have_a_size_and_point_price(self):
        exact_rows = [
            row for row in self.rows
            if row["size_price_status"] in EXACT_SIZE_STATUSES
        ]
        self.assertTrue(exact_rows)
        for row in exact_rows:
            self.assertNotIn(row["stock_size"], {"", "Not mapped", "Not supplied"})
            self.assertEqual(row["minimum_cost"], row["maximum_cost"])

    def test_unmapped_prices_are_explicit(self):
        unmapped_rows = [
            row for row in self.rows
            if row["size_price_status"] not in EXACT_SIZE_STATUSES
        ]
        self.assertTrue(unmapped_rows)
        for row in unmapped_rows:
            self.assertEqual(
                row["cost_context"],
                "supplier_advertised_species_product_size_unmapped",
            )

    def test_source_business_key_is_unique(self):
        keys = [
            (
                row["option_code"], row["cost_context"], row["cost_basis"],
                row["tree_type"], row["stock_size"], row["source_name"],
                row["valid_from"], row["source_reference"],
            )
            for row in self.rows
        ]
        self.assertEqual(len(keys), len(set(keys)))

    def test_taxon_aliases_are_auditable_and_reference_priced_identities(self):
        with ALIAS_FILE.open(newline="", encoding="utf-8") as handle:
            aliases = list(csv.DictReader(handle))
        self.assertTrue(aliases)
        priced_names = {row["botanical_name"] for row in self.rows}
        for row in aliases:
            self.assertIn(row["priced_identity"], priced_names)
            self.assertTrue(row["catalogue_name"].strip())
            self.assertTrue(row["match_method"].strip())
            self.assertEqual(row["reviewed_at"], "2026-09-18")
            self.assertIn("not represented as a distinct named-cultivar quote", row["limitation"])


if __name__ == "__main__":
    unittest.main()
