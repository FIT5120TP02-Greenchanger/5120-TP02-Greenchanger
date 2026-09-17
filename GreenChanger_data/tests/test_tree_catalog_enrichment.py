import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from greenchanger_script.enrich_tree_catalog import (
    deterministic_taxon_candidates,
    enrich_species,
    enrich_species_with_commons,
    normalized_gbif_media_licence,
    read_checkpoint,
    wikipedia_title_candidate,
)


class TreeCatalogEnrichmentTests(unittest.TestCase):
    def test_deterministic_candidates_extract_embedded_binomial(self):
        self.assertIn(
            ("Prunus armeniaca", "embedded_scientific_name"),
            deterministic_taxon_candidates("Apricot Tree, Prunus armeniaca"),
        )

    def test_deterministic_candidates_normalize_nothospecies_symbol(self):
        self.assertIn(
            ("Acer × freemanii", "normalized_hybrid_name"),
            deterministic_taxon_candidates("Acer x freemanii 'Autumn Blaze'"),
        )

    def test_wikipedia_title_candidate_selects_unique_close_binomial(self):
        result = {"query": {"prefixsearch": [
            {"title": "Acacia filifolia"},
            {"title": "Acacia filicifolia"},
            {"title": "Acacia fimbriata"},
        ]}}
        with patch(
            "greenchanger_script.enrich_tree_catalog.get_wikimedia_json",
            return_value=result,
        ):
            candidate = wikipedia_title_candidate("Acacia ficifolia")
        self.assertEqual(candidate, "Acacia filicifolia")

    def test_wikipedia_title_candidate_rejects_non_binomial_common_name(self):
        with patch("greenchanger_script.enrich_tree_catalog.get_wikimedia_json") as request:
            candidate = wikipedia_title_candidate("American Elm")
        self.assertIsNone(candidate)
        request.assert_not_called()

    def test_legacy_checkpoint_rows_get_non_null_gbif_source(self):
        legacy = {
            "scientific_name": "Abutilon sp.",
            "gbif_taxon_key": 3152599,
            "image_source_name": None,
            "taxon_verification_id": None,
        }
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.jsonl"
            checkpoint.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
            row = read_checkpoint(checkpoint)["Abutilon sp."]
        self.assertEqual(row["image_source_name"], "GBIF occurrence media API")
        self.assertEqual(row["taxon_verification_id"], "3152599")

    def test_legacy_unmatched_checkpoint_row_gets_explicit_null_verification_id(self):
        legacy = {"scientific_name": "Unknown tree", "gbif_taxon_key": None}
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.jsonl"
            checkpoint.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
            row = read_checkpoint(checkpoint)["Unknown tree"]
        self.assertEqual(row["image_source_name"], "GBIF occurrence media API")
        self.assertIsNone(row["taxon_verification_id"])

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
                    "license": "https://creativecommons.org/licenses/by/4.0/",
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

    def test_gbif_media_licence_accepts_only_policy_approved_values(self):
        self.assertEqual(
            normalized_gbif_media_licence("http://creativecommons.org/licenses/by/4.0/"),
            ("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/"),
        )
        self.assertEqual(
            normalized_gbif_media_licence("CC0_1_0"),
            ("CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/"),
        )
        for rejected in (
            None,
            "All rights reserved",
            "https://creativecommons.org/licenses/by-nc/4.0/",
            "https://creativecommons.org/licenses/by-nc-sa/4.0/",
            "https://creativecommons.org/licenses/by-nd/4.0/",
        ):
            self.assertIsNone(normalized_gbif_media_licence(rejected))

    def test_occurrence_filter_does_not_override_restricted_media_licence(self):
        match = {
            "usageKey": 123, "speciesKey": 123,
            "scientificName": "Example tree L.", "rank": "SPECIES",
            "status": "ACCEPTED", "confidence": 99,
            "matchType": "EXACT", "kingdom": "Plantae",
        }
        restricted = {"results": [{
            "key": 456, "speciesKey": 123,
            "media": [{
                "identifier": "https://images.example/tree.jpg",
                "creator": "Example Creator",
                "license": "All rights reserved",
            }],
        }]}
        noncommercial = {"results": [{
            "key": 789, "speciesKey": 123,
            "media": [{
                "identifier": "https://images.example/tree-2.jpg",
                "creator": "Example Creator",
                "license": "https://creativecommons.org/licenses/by-nc/4.0/",
            }],
        }]}
        with patch(
            "greenchanger_script.enrich_tree_catalog.get_json",
            side_effect=[match, restricted, noncommercial],
        ):
            row = enrich_species("Example tree")
        self.assertEqual(row["enrichment_status"], "no_open_image")
        self.assertIsNone(row["image_url"])
        self.assertIn("media-level", row["limitation"])

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
        self.assertIn("media-level CC0", row["limitation"])

    def test_commons_fallback_requires_exact_wikidata_taxon_and_keeps_attribution(self):
        base = {
            "scientific_name": "Example tree",
            "enrichment_status": "no_open_image",
            "gbif_taxon_key": 123,
        }
        search = {"search": [{"id": "Q123"}]}
        entity = {
            "entities": {"Q123": {"claims": {
                "P225": [{"mainsnak": {"datavalue": {"value": "Example tree"}}}],
                "P18": [{"mainsnak": {"datavalue": {"value": "Example tree.jpg"}}}],
            }}}
        }
        image = {"query": {"pages": {"1": {
            "title": "File:Example tree.jpg",
            "imageinfo": [{
                "url": "https://upload.wikimedia.org/example.jpg",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Example_tree.jpg",
                "mime": "image/jpeg",
                "extmetadata": {
                    "LicenseShortName": {"value": "CC BY-SA 4.0"},
                    "Artist": {"value": "<a>Example Creator</a>"},
                },
            }],
        }}}}
        with (
            patch(
                "greenchanger_script.enrich_tree_catalog.get_json",
                return_value={"canonicalName": "Example tree"},
            ),
            patch(
                "greenchanger_script.enrich_tree_catalog.get_wikimedia_json",
                side_effect=[search, entity, image],
            ),
        ):
            row = enrich_species_with_commons("Example tree", base)
        self.assertEqual(row["enrichment_status"], "verified_open_image")
        self.assertEqual(row["image_source_name"], "Wikimedia Commons")
        self.assertEqual(row["taxon_verification_id"], "Q123")
        self.assertEqual(row["image_licence"], "CC BY-SA 4.0")
        self.assertIn("Example Creator", row["image_attribution"])

    def test_commons_fallback_can_use_exact_canonical_gbif_taxon_for_cultivar(self):
        base = {
            "scientific_name": "Example tree 'Compacta'",
            "enrichment_status": "taxon_unresolved",
            "gbif_taxon_key": 123,
            "match_type": "EXACT",
        }
        canonical_search = {"search": [{"id": "Q123"}]}
        entity = {
            "entities": {"Q123": {"claims": {
                "P225": [{"mainsnak": {"datavalue": {"value": "Example tree"}}}],
                "P18": [{"mainsnak": {"datavalue": {"value": "Example tree.jpg"}}}],
            }}}
        }
        image = {"query": {"pages": {"1": {
            "title": "File:Example tree.jpg",
            "imageinfo": [{
                "url": "https://upload.wikimedia.org/example.jpg",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Example_tree.jpg",
                "mime": "image/jpeg",
                "extmetadata": {
                    "LicenseShortName": {"value": "Public domain"},
                    "Artist": {"value": "Example Creator"},
                },
            }],
        }}}}
        with (
            patch(
                "greenchanger_script.enrich_tree_catalog.get_json",
                return_value={"canonicalName": "Example tree"},
            ),
            patch(
                "greenchanger_script.enrich_tree_catalog.get_wikimedia_json",
                side_effect=[canonical_search, entity, image],
            ),
        ):
            row = enrich_species_with_commons("Example tree 'Compacta'", base)
        self.assertEqual(row["matched_scientific_name"], "Example tree")
        self.assertEqual(row["taxonomic_status"], "WIKIDATA_EXACT_P225")
        self.assertIn("necessarily the named cultivar/form", row["limitation"])

    def test_commons_fallback_does_not_use_canonical_name_for_fuzzy_gbif_match(self):
        base = {
            "scientific_name": "Acacia cultiformis",
            "enrichment_status": "taxon_unresolved",
            "gbif_taxon_key": 123,
            "match_type": "FUZZY",
        }
        with (
            patch("greenchanger_script.enrich_tree_catalog.get_json") as get_json,
            patch(
                "greenchanger_script.enrich_tree_catalog.get_wikimedia_json",
                return_value={"search": []},
            ),
        ):
            row = enrich_species_with_commons("Acacia cultiformis", base)
        get_json.assert_not_called()
        self.assertIs(row, base)

    def test_broader_fallback_accepts_high_confidence_same_genus_spelling_fix(self):
        base = {
            "scientific_name": "Acacia decurens",
            "enrichment_status": "taxon_unresolved",
            "gbif_taxon_key": 123,
            "match_type": "FUZZY",
            "match_confidence": 96,
            "taxon_rank": "SPECIES",
        }
        search = {"search": [{"id": "Q123"}]}
        entity = {"entities": {"Q123": {"claims": {
            "P225": [{"mainsnak": {"datavalue": {"value": "Acacia decurrens"}}}],
            "P18": [{"mainsnak": {"datavalue": {"value": "Acacia decurrens.jpg"}}}],
        }}}}
        image = {"query": {"pages": {"1": {
            "title": "File:Acacia decurrens.jpg",
            "imageinfo": [{
                "url": "https://upload.wikimedia.org/acacia.jpg",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Acacia_decurrens.jpg",
                "mime": "image/jpeg",
                "extmetadata": {
                    "LicenseShortName": {"value": "CC0 1.0"},
                    "Artist": {"value": "Example Creator"},
                },
            }],
        }}}}
        with (
            patch(
                "greenchanger_script.enrich_tree_catalog.get_json",
                return_value={"canonicalName": "Acacia decurrens", "rank": "SPECIES"},
            ),
            patch(
                "greenchanger_script.enrich_tree_catalog.get_wikimedia_json",
                side_effect=[search, entity, image],
            ),
        ):
            row = enrich_species_with_commons("Acacia decurens", base, broader=True)
        self.assertEqual(row["enrichment_status"], "verified_open_image")
        self.assertEqual(row["matched_scientific_name"], "Acacia decurrens")
        self.assertIn("spelling correction", row["limitation"])

    def test_broader_fallback_rejects_low_confidence_spelling_fix(self):
        base = {
            "scientific_name": "Acacia salicifolia",
            "enrichment_status": "taxon_unresolved",
            "gbif_taxon_key": 123,
            "match_type": "FUZZY",
            "match_confidence": 93,
            "taxon_rank": "SPECIES",
        }
        with (
            patch(
                "greenchanger_script.enrich_tree_catalog.get_json",
                return_value={"canonicalName": "Acacia saliciformis", "rank": "SPECIES"},
            ),
            patch(
                "greenchanger_script.enrich_tree_catalog.get_wikimedia_json",
                return_value={"search": []},
            ),
        ):
            row = enrich_species_with_commons("Acacia salicifolia", base, broader=True)
        self.assertIs(row, base)

    def test_broader_fallback_accepts_exact_common_name_alias_on_taxon_item(self):
        base = {
            "scientific_name": "American Elm",
            "enrichment_status": "taxon_unresolved",
            "gbif_taxon_key": None,
            "match_type": "NONE",
        }
        search = {"search": [{
            "id": "Q469382", "label": "Ulmus americana",
            "match": {"type": "alias", "language": "en", "text": "American elm"},
        }]}
        entity = {"entities": {"Q469382": {"claims": {
            "P225": [{"mainsnak": {"datavalue": {"value": "Ulmus americana"}}}],
            "P18": [{"mainsnak": {"datavalue": {"value": "Ulmus americana.jpg"}}}],
        }}}}
        image = {"query": {"pages": {"1": {
            "title": "File:Ulmus americana.jpg",
            "imageinfo": [{
                "url": "https://upload.wikimedia.org/ulmus.jpg",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Ulmus_americana.jpg",
                "mime": "image/jpeg",
                "extmetadata": {
                    "LicenseShortName": {"value": "CC BY 4.0"},
                    "Artist": {"value": "Example Creator"},
                },
            }],
        }}}}
        with patch(
            "greenchanger_script.enrich_tree_catalog.get_wikimedia_json",
            side_effect=[search, entity, image],
        ):
            row = enrich_species_with_commons("American Elm", base, broader=True)
        self.assertEqual(row["matched_scientific_name"], "Ulmus americana")
        self.assertEqual(row["taxon_verification_id"], "Q469382")
        self.assertIn("exactly matches an English Wikidata label or alias", row["limitation"])

    def test_broader_fallback_rejects_exact_non_taxon_label(self):
        base = {
            "scientific_name": "American Elm",
            "enrichment_status": "taxon_unresolved",
            "gbif_taxon_key": None,
            "match_type": "NONE",
        }
        search = {"search": [{
            "id": "Q1", "label": "American Elm",
            "match": {"type": "label", "language": "en", "text": "American Elm"},
        }]}
        entity = {"entities": {"Q1": {"claims": {}}}}
        with patch(
            "greenchanger_script.enrich_tree_catalog.get_wikimedia_json",
            side_effect=[search, entity],
        ):
            row = enrich_species_with_commons("American Elm", base, broader=True)
        self.assertIs(row, base)

    def test_commons_fallback_rejects_nonmatching_wikidata_taxon(self):
        base = {"scientific_name": "Example tree", "enrichment_status": "taxon_unresolved"}
        search = {"search": [{"id": "Q123"}]}
        entity = {"entities": {"Q123": {"claims": {
            "P225": [{"mainsnak": {"datavalue": {"value": "Different tree"}}}],
        }}}}
        with patch(
            "greenchanger_script.enrich_tree_catalog.get_wikimedia_json",
            side_effect=[search, entity],
        ):
            row = enrich_species_with_commons("Example tree", base)
        self.assertIs(row, base)


if __name__ == "__main__":
    unittest.main()
