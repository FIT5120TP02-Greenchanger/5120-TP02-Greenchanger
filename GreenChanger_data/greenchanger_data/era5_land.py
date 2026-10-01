"""Download and normalise Melbourne ERA5-Land into daily weather controls."""

from __future__ import annotations

from datetime import date, timedelta
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

import numpy as np
import pandas as pd


DATASET_ID = "reanalysis-era5-land"
VARIABLES = (
    "2m_temperature",
    "total_precipitation",
    "volumetric_soil_water_layer_1",
    "surface_solar_radiation_downwards",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
)
VARIABLE_ALIASES = {
    "temperature": ("t2m", "2m_temperature"),
    "precipitation": ("tp", "total_precipitation"),
    "soil_moisture": ("swvl1", "volumetric_soil_water_layer_1"),
    "solar_radiation": ("ssrd", "surface_solar_radiation_downwards"),
    "wind_u": ("u10", "10m_u_component_of_wind"),
    "wind_v": ("v10", "10m_v_component_of_wind"),
}


def _month_starts(start: date, end: date) -> Iterator[date]:
    current = start.replace(day=1)
    while current <= end:
        yield current
        current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)


def download_era5_land(
    output_directory: Path,
    *,
    start: date,
    end: date,
    bbox_wgs84: Sequence[float],
) -> list[Path]:
    """Download one NetCDF per month through the official CDS API."""

    if end < start:
        raise ValueError("ERA5 end date must not precede start date")
    if len(bbox_wgs84) != 4:
        raise ValueError("bbox_wgs84 must be west, south, east, north")
    try:
        import cdsapi
    except ImportError as error:
        raise RuntimeError("Install requirements.txt to use the ERA5 CDS API") from error

    output_directory.mkdir(parents=True, exist_ok=True)
    client = cdsapi.Client()
    paths: list[Path] = []
    for month_start in _month_starts(start, end):
        month_end = (month_start + pd.offsets.MonthEnd(0)).date()
        first_day = max(start, month_start)
        last_day = min(end, month_end)
        days = [f"{day:02d}" for day in range(first_day.day, last_day.day + 1)]
        target = output_directory / f"era5_land_{month_start:%Y_%m}.nc"
        if target.is_file() and target.stat().st_size > 0:
            paths.append(target)
            continue
        request = {
            "variable": list(VARIABLES),
            "year": f"{month_start.year:04d}",
            "month": f"{month_start.month:02d}",
            "day": days,
            "time": [f"{hour:02d}:00" for hour in range(24)],
            "data_format": "netcdf",
            "download_format": "unarchived",
            "area": [bbox_wgs84[3], bbox_wgs84[0], bbox_wgs84[1], bbox_wgs84[2]],
        }
        partial_target = target.with_suffix(f"{target.suffix}.part")
        client.retrieve(DATASET_ID, request, str(partial_target))
        partial_target.replace(target)
        paths.append(target)
    return paths


def source_files(path: Path) -> list[Path]:
    """Resolve one NetCDF or all NetCDF files in a directory."""

    if path.is_file():
        return [path]
    if path.is_dir():
        files = sorted((*path.glob("*.nc"), *path.glob("*.nc4")))
        if files:
            return files
    raise FileNotFoundError(f"No ERA5-Land NetCDF files found at {path}")


def combined_checksum(paths: Iterable[Path]) -> str:
    digest = sha256()
    for path in sorted(paths):
        digest.update(path.name.encode("utf-8"))
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def _variable(dataset, logical_name: str):
    for name in VARIABLE_ALIASES[logical_name]:
        if name in dataset:
            return dataset[name]
    raise ValueError(
        f"ERA5-Land file is missing {logical_name}; accepted names: "
        f"{VARIABLE_ALIASES[logical_name]}"
    )


def _coordinate_name(dataset, candidates: Sequence[str]) -> str:
    for name in candidates:
        if name in dataset.coords:
            return name
    raise ValueError(f"ERA5-Land file is missing coordinate {candidates}")


def _finite(value: Any) -> float | None:
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def normalise_era5_files(
    paths: Iterable[Path], *, start: date, end: date
) -> Iterator[dict[str, Any]]:
    """Yield daily grid-point controls with explicit converted units."""

    import xarray as xr

    for path in paths:
        with xr.open_dataset(path) as opened:
            dataset = opened.load()
        time_name = _coordinate_name(dataset, ("valid_time", "time"))
        latitude_name = _coordinate_name(dataset, ("latitude", "lat"))
        longitude_name = _coordinate_name(dataset, ("longitude", "lon"))
        times = pd.to_datetime(dataset[time_name].values, utc=True)
        selected_indices = [
            index for index, timestamp in enumerate(times)
            if start <= timestamp.date() <= end
        ]
        by_day: dict[date, list[int]] = {}
        for index in selected_indices:
            by_day.setdefault(times[index].date(), []).append(index)

        temperature = _variable(dataset, "temperature")
        precipitation = _variable(dataset, "precipitation")
        soil_moisture = _variable(dataset, "soil_moisture")
        solar_radiation = _variable(dataset, "solar_radiation")
        wind_u = _variable(dataset, "wind_u")
        wind_v = _variable(dataset, "wind_v")

        latitudes = dataset[latitude_name].values
        longitudes = dataset[longitude_name].values
        for observed_on, indices in sorted(by_day.items()):
            selector = {time_name: indices}
            temp_values = temperature.isel(selector).values.astype("float64")
            if np.nanmedian(temp_values) > 150:
                temp_values -= 273.15
            precipitation_values = precipitation.isel(selector).values.astype("float64") * 1000.0
            soil_values = soil_moisture.isel(selector).values.astype("float64")
            solar_values = solar_radiation.isel(selector).values.astype("float64") / 1_000_000.0
            u_values = wind_u.isel(selector).values.astype("float64")
            v_values = wind_v.isel(selector).values.astype("float64")
            wind_values = np.sqrt(np.square(u_values) + np.square(v_values))

            for latitude_index, latitude in enumerate(latitudes):
                for longitude_index, longitude in enumerate(longitudes):
                    cell_temp = temp_values[:, latitude_index, longitude_index]
                    if not np.isfinite(cell_temp).any():
                        continue
                    lat = float(latitude)
                    lon = float(longitude)
                    yield {
                        "cell_key": f"era5:{lat:.4f}:{lon:.4f}",
                        "observed_on": observed_on.isoformat(),
                        "latitude": lat,
                        "longitude": lon,
                        "air_temperature_mean_c": _finite(np.nanmean(cell_temp)),
                        "air_temperature_min_c": _finite(np.nanmin(cell_temp)),
                        "air_temperature_max_c": _finite(np.nanmax(cell_temp)),
                        "precipitation_total_mm": _finite(
                            np.nansum(precipitation_values[:, latitude_index, longitude_index])
                        ),
                        "soil_water_layer_1_mean_m3_m3": _finite(
                            np.nanmean(soil_values[:, latitude_index, longitude_index])
                        ),
                        "surface_solar_radiation_total_mj_m2": _finite(
                            np.nansum(solar_values[:, latitude_index, longitude_index])
                        ),
                        "wind_speed_mean_ms": _finite(
                            np.nanmean(wind_values[:, latitude_index, longitude_index])
                        ),
                        "hour_count": len(indices),
                        "geometry_wkt": f"POINT({lon} {lat})",
                        "source_srid": 4326,
                        "source_file": path.name,
                    }


def request_metadata(start: date, end: date, bbox_wgs84: Sequence[float]) -> str:
    payload = {
        "dataset": DATASET_ID,
        "variables": VARIABLES,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "bbox_wgs84": list(bbox_wgs84),
        "aggregation": "daily_by_grid_point",
    }
    return json.dumps(payload, sort_keys=True)
