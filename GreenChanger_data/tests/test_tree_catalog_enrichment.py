import unittest
from unittest.mock import patch

from greenchanger_script.enrich_tree_catalog import enrich_species


class TreeCatalogEnrichmentTests(unittest.TestCase):
    def test_retry_failed_flag_is_exposed_by_the_resumable_job(self):
        script = __import__(
            "greenchanger_script.enrich_tree_catalog",
            fromlist=["__file__"],
        )
        with open(script.__file__, encoding="utf-8") as stream:
            self.assertIn("--retry-failed", stream.read())

    def test_exact_open_image_keeps_licence_and_attribution(self):
        match = {
            "usageKey": 123,
            "speciesKey": 123,
            "scientificName": "Example tree L.",
            "rank": "SPECIES",
            "status": "ACCEPTED",
            "confidence": 99,
            "matchType": "EXACT",
            "kingdom": "Plantae",
        }
        occurrence = {
            "results": [{
                "key": 456,
                "speciesKey": 123,
                "media": [{
                    "identifier": "https://images.example/tree.jpg",
                    "references": "https://records.example/456",
                    "creator": "Example Creator",
                    "rightsHolder": "Example Creator",
                }],
            }]
        }
        with patch(
            "greenchanger_script.enrich_tree_catalog.get_json",
            side_effect=[match, occurrence],
        ):
            row = enrich_species("Example tree")
        self.assertEqual(row["enrichment_status"], "verified_open_image")
        self.assertEqual(row["image_licence"], "CC BY 4.0")
        self.assertEqual(row["gbif_occurrence_key"], 456)
        self.assertIn("Example Creator", row["image_attribution"])

    def test_fuzzy_taxon_match_never_publishes_image(self):
        with patch(
            "greenchanger_script.enrich_tree_catalog.get_json",
            return_value={
                "usageKey": 123,
                "scientificName": "Different tree",
                "confidence": 80,
                "matchType": "FUZZY",
                "kingdom": "Plantae",
            },
        ):
            row = enrich_species("Misspelled tree")
        self.assertEqual(row["enrichment_status"], "taxon_unresolved")
        self.assertIsNone(row["image_url"])

    def test_no_accepted_open_media_is_explicitly_unavailable(self):
        match = {
            "usageKey": 123,
            "speciesKey": 123,
            "scientificName": "Example tree L.",
            "rank": "SPECIES",
            "status": "ACCEPTED",
            "confidence": 99,
            "matchType": "EXACT",
            "kingdom": "Plantae",
        }
        with patch(
            "greenchanger_script.enrich_tree_catalog.get_json",
            side_effect=[match, {"results": []}, {"results": []}, {"results": []}],
        ):
            row = enrich_species("Example tree")
        self.assertEqual(row["enrichment_status"], "no_open_image")
        self.assertIsNone(row["image_url"])
        self.assertIn("no usable CC0", row["limitation"])


if __name__ == "__main__":
    unittest.main()
