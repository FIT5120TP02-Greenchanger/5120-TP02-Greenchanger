import json
from pathlib import Path
import tempfile
import unittest

from greenchanger_data.sources import load_source_registry


ROOT = Path(__file__).resolve().parents[1]


class SourceRegistryLicenceTests(unittest.TestCase):
    def test_every_registered_source_has_an_explicit_licence_decision(self):
        registry = load_source_registry(ROOT / "config" / "datasets.json")
        self.assertTrue(
            all(source["licence"] for source in registry["datasets"])
        )
        self.assertTrue(
            all(source["licence_status"] for source in registry["datasets"])
        )

    def test_missing_licence_decision_is_rejected(self):
        registry = {
            "datasets": [
                {
                    "key": "example",
                    "name": "Example",
                    "publisher": "Example",
                    "url": "https://example.test",
                    "category": "example",
                    "coverage": "Melbourne",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "datasets.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_source_registry(path)


if __name__ == "__main__":
    unittest.main()
