from datetime import date
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import xarray as xr

from greenchanger_data.era5_land import download_era5_land, normalise_era5_files


class Era5LandTests(unittest.TestCase):
    def test_download_reuses_completed_month_without_new_cds_request(self):
        client = Mock()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "era5_land_2018_01.nc"
            target.write_bytes(b"completed")
            fake_cdsapi = SimpleNamespace(Client=Mock(return_value=client))
            with patch.dict(sys.modules, {"cdsapi": fake_cdsapi}):
                paths = download_era5_land(
                    Path(directory),
                    start=date(2018, 1, 1),
                    end=date(2018, 1, 31),
                    bbox_wgs84=(144.3, -38.6, 146.3, -37.3),
                )

        self.assertEqual(paths, [target])
        client.retrieve.assert_not_called()

    def test_hourly_values_are_converted_to_daily_controls(self):
        times = pd.date_range("2025-01-02", periods=24, freq="h")
        shape = (24, 1, 1)
        dataset = xr.Dataset(
            {
                "t2m": (("valid_time", "latitude", "longitude"), np.full(shape, 293.15)),
                "tp": (("valid_time", "latitude", "longitude"), np.full(shape, 0.001)),
                "swvl1": (("valid_time", "latitude", "longitude"), np.full(shape, 0.25)),
                "ssrd": (("valid_time", "latitude", "longitude"), np.full(shape, 1_000_000.0)),
                "u10": (("valid_time", "latitude", "longitude"), np.full(shape, 3.0)),
                "v10": (("valid_time", "latitude", "longitude"), np.full(shape, 4.0)),
            },
            coords={"valid_time": times, "latitude": [-37.8], "longitude": [145.0]},
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "era5.nc"
            dataset.to_netcdf(path)
            rows = list(normalise_era5_files(
                [path], start=date(2025, 1, 2), end=date(2025, 1, 2)
            ))

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertAlmostEqual(row["air_temperature_mean_c"], 20.0, places=5)
        self.assertAlmostEqual(row["precipitation_total_mm"], 24.0, places=5)
        self.assertAlmostEqual(row["surface_solar_radiation_total_mj_m2"], 24.0, places=5)
        self.assertAlmostEqual(row["wind_speed_mean_ms"], 5.0, places=5)
        self.assertEqual(row["hour_count"], 24)

    def test_date_filter_excludes_other_days(self):
        times = pd.date_range("2025-01-01", periods=48, freq="h")
        shape = (48, 1, 1)
        variables = {
            "t2m": np.full(shape, 290.0), "tp": np.zeros(shape),
            "swvl1": np.full(shape, 0.2), "ssrd": np.zeros(shape),
            "u10": np.ones(shape), "v10": np.ones(shape),
        }
        dataset = xr.Dataset(
            {name: (("time", "latitude", "longitude"), values)
             for name, values in variables.items()},
            coords={"time": times, "latitude": [-37.8], "longitude": [145.0]},
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "era5.nc"
            dataset.to_netcdf(path)
            rows = list(normalise_era5_files(
                [path], start=date(2025, 1, 2), end=date(2025, 1, 2)
            ))
        self.assertEqual([row["observed_on"] for row in rows], ["2025-01-02"])


if __name__ == "__main__":
    unittest.main()
