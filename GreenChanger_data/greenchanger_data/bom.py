"""Extraction and normalisation for the BOM Melbourne observation feed."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable
from urllib.request import Request, urlopen


DEFAULT_BOM_URL = "https://www.bom.gov.au/fwo/IDV60901/IDV60901.95936.json"


def fetch_observations(url: str = DEFAULT_BOM_URL, *, timeout: int = 30) -> dict[str, Any]:
    """Download the current BOM JSON document."""

    request = Request(url, headers={"User-Agent": "GreenShift university project"})
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def extract_rows(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the feed's observation rows or fail on an unexpected payload."""

    observations = document.get("observations")
    if not isinstance(observations, dict):
        raise ValueError("BOM payload has no observations object")
    rows = observations.get("data")
    if not isinstance(rows, list):
        raise ValueError("BOM payload has no observations.data list")
    return rows


def _float(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rainfall(value: Any) -> float | None:
    if isinstance(value, str) and value.strip().casefold() == "trace":
        return 0.0
    return _float(value)


def _utc_timestamp(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value)
    for pattern in ("%Y%m%d%H%M%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            parsed = datetime.strptime(text, pattern)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def normalise_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map BOM field names and units to the weather_observation staging grain."""

    normalised: list[dict[str, Any]] = []
    for row in rows:
        latitude = _float(row.get("lat"))
        longitude = _float(row.get("lon"))
        wind_kmh = _float(row.get("wind_spd_kmh"))
        geometry_wkt = (
            f"POINT({longitude} {latitude})"
            if latitude is not None and longitude is not None
            else None
        )

        normalised.append(
            {
                "station_code": str(row.get("wmo") or row.get("history_product") or ""),
                "station_name": row.get("name"),
                "observed_at": _utc_timestamp(row.get("aifstime_utc")),
                "air_temperature_c": _float(row.get("air_temp")),
                "apparent_temperature_c": _float(row.get("apparent_t")),
                "humidity_pct": _float(row.get("rel_hum")),
                "wind_speed_ms": round(wind_kmh / 3.6, 3) if wind_kmh is not None else None,
                "rainfall_since_9am_mm": _rainfall(row.get("rain_trace")),
                "geometry_wkt": geometry_wkt,
                "source_srid": 4326,
                "quality_status": "unreviewed",
            }
        )
    return normalised


def save_raw(document: dict[str, Any], path: Path) -> None:
    """Preserve the unmodified response for reproducibility."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
