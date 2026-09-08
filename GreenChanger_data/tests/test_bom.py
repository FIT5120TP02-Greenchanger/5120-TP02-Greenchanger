import json
from pathlib import Path
import tempfile
import unittest

from greenchanger_data.bom import (
    DEFAULT_STATION_REGISTRY,
    extract_rows,
    extract_station_rows,
    fetch_station_documents,
    load_station_registry,
    normalise_rows,
)


class BomTests(unittest.TestCase):
    def test_extract_and_normalise(self):
        document = {
            "observations": {
                "data": [
                    {
                        "wmo": 95936,
                        "name": "Melbourne (Olympic Park)",
                        "aifstime_utc": "20260825090000",
                        "air_temp": 20.5,
                        "apparent_t": 19.1,
                        "rel_hum": 55,
                        "wind_spd_kmh": 18,
                        "rain_trace": "Trace",
                        "lat": -37.8255,
                        "lon": 144.9816,
                    }
                ]
            }
        }

        rows = normalise_rows(extract_rows(document))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["station_code"], "95936")
        self.assertEqual(rows[0]["wind_speed_ms"], 5.0)
        self.assertEqual(rows[0]["rainfall_since_9am_mm"], 0.0)
        self.assertEqual(rows[0]["source_srid"], 4326)
        self.assertTrue(rows[0]["observed_at"].endswith("+00:00"))

    def test_missing_observation_list_is_rejected(self):
        with self.assertRaises(ValueError):
            extract_rows({"observations": {}})

    def test_station_registry_covers_greater_melbourne_regions(self):
        registry = load_station_registry(DEFAULT_STATION_REGISTRY)
        self.assertGreaterEqual(len(registry["stations"]), 10)
        roles = {station["coverage_role"] for station in registry["stations"]}
        self.assertIn("central_melbourne", roles)
        self.assertIn("western_melbourne", roles)
        self.assertIn("northern_growth_area", roles)
        self.assertIn("eastern_melbourne", roles)
        self.assertIn("bayside_and_southeastern_melbourne", roles)
        self.assertIn("frankston_and_mornington_gateway", roles)
        self.assertTrue(
            all(
                station["source_url"].startswith("https://www.bom.gov.au/fwo/")
                for station in registry["stations"]
            )
        )

    def test_duplicate_station_code_is_rejected(self):
        registry = load_station_registry(DEFAULT_STATION_REGISTRY)
        registry["stations"].append(dict(registry["stations"][0]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stations.json"
            path.write_text(json.dumps(registry), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate BOM station code"):
                load_station_registry(path)

    def test_scoresby_uses_its_official_state_observation_feed(self):
        registry = load_station_registry(DEFAULT_STATION_REGISTRY)
        self.assertEqual(
            registry["product_codes"], ["IDV60901", "IDV60801"]
        )
        scoresby = next(
            station
            for station in registry["stations"]
            if station["station_code"] == "95867"
        )
        self.assertEqual(
            scoresby["source_url"],
            "https://www.bom.gov.au/fwo/IDV60801/IDV60801.95867.json",
        )
        self.assertEqual(
            scoresby["availability_status"],
            "planned_outage_site_relocation",
        )

    def test_multi_station_document_flattens_to_observation_rows(self):
        row = {
            "wmo": 95936,
            "aifstime_utc": "20260825090000",
            "air_temp": 20.5,
        }
        document = {
            "station_feeds": [
                {"document": {"observations": {"data": [row]}}},
                {
                    "document": {
                        "observations": {"data": [{**row, "wmo": 94865}]}
                    }
                },
            ]
        }
        self.assertEqual(len(extract_station_rows(document)), 2)

    def test_one_failed_station_does_not_discard_available_feeds(self):
        registry = {
            "registry_version": "test-v1",
            "stations": [
                {
                    "station_code": "1", "station_name": "Available",
                    "coverage_role": "central", "source_url": "https://example.test/1",
                },
                {
                    "station_code": "2", "station_name": "Unavailable",
                    "coverage_role": "east", "source_url": "https://example.test/2",
                },
            ],
        }
        documents = {
            "https://example.test/1": {
                "observations": {"data": [{"wmo": "1", "air_temp": 20}]}
            },
            "https://example.test/2": {"observations": {"data": []}},
        }
        from unittest.mock import patch

        with patch(
            "greenchanger_data.bom.fetch_observations",
            side_effect=lambda url, timeout=30: documents[url],
        ):
            combined = fetch_station_documents(registry)
        self.assertEqual(len(combined["station_feeds"]), 1)
        self.assertEqual(combined["failed_station_feeds"][0]["station_code"], "2")
        self.assertEqual(len(extract_station_rows(combined)), 1)

    def test_all_failed_stations_are_rejected(self):
        registry = {
            "registry_version": "test-v1",
            "stations": [{
                "station_code": "1", "station_name": "Unavailable",
                "coverage_role": "central", "source_url": "https://example.test/1",
            }],
        }
        from unittest.mock import patch

        with patch(
            "greenchanger_data.bom.fetch_observations",
            return_value={"observations": {"data": []}},
        ):
            with self.assertRaisesRegex(ValueError, "all configured"):
                fetch_station_documents(registry)


if __name__ == "__main__":
    unittest.main()
