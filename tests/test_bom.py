import unittest

from greenchanger_data.bom import extract_rows, normalise_rows


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


if __name__ == "__main__":
    unittest.main()
