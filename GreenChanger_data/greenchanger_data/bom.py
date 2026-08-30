"""Extraction and normalisation for Melbourne BOM station feeds."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable
from urllib.request import Request, urlopen


DEFAULT_BOM_URL = "https://www.bom.gov.au/fwo/IDV60901/IDV60901.95936.json"
DEFAULT_STATION_REGISTRY = (
    Path(__file__).resolve().parents[1] / "config" / "bom_stations.json"
)
REQUIRED_COVERAGE_ROLES = {
    "central_melbourne",
    "western_melbourne",
    "northern_growth_area",
    "eastern_melbourne",
    "bayside_and_southeastern_melbourne",
    "frankston_and_mornington_gateway",
}


def fetch_observations(url: str = DEFAULT_BOM_URL, *, timeout: int = 30) -> dict[str, Any]:
    """Download the current BOM JSON document."""

    request = Request(url, headers={"User-Agent": "GreenShift university project"})
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def load_station_registry(path: Path = DEFAULT_STATION_REGISTRY) -> dict[str, Any]:
    """Load and validate the versioned Melbourne station registry."""

    registry = json.loads(path.read_text(encoding="utf-8"))
    stations = registry.get("stations")
    if not isinstance(stations, list) or not stations:
        raise ValueError("BOM station registry must contain a non-empty stations list")
    codes: set[str] = set()
    roles: set[str] = set()
    for station in stations:
        required = {"station_code", "station_name", "coverage_role", "source_url"}
        missing = required - station.keys()
        if missing:
            raise ValueError(
                f"BOM station is missing required fields: {sorted(missing)}"
            )
        code = str(station["station_code"])
        if code in codes:
            raise ValueError(f"duplicate BOM station code: {code}")
        codes.add(code)
        roles.add(station["coverage_role"])
        if not station["source_url"].startswith("https://www.bom.gov.au/fwo/"):
            raise ValueError(f"station {code} does not use an official BOM feed")
    missing_roles = REQUIRED_COVERAGE_ROLES - roles
    if missing_roles:
        raise ValueError(
            "BOM station registry is missing coverage roles: "
            + ", ".join(sorted(missing_roles))
        )
    return registry


def fetch_station_documents(
    registry: dict[str, Any], *, timeout: int = 30
) -> dict[str, Any]:
    """Fetch every configured official BOM station feed as one raw document."""

    feeds = []
    for station in registry["stations"]:
        document = fetch_observations(station["source_url"], timeout=timeout)
        rows = extract_rows(document)
        if not rows:
            raise ValueError(f"BOM station {station['station_code']} returned no rows")
        feed_codes = {
            str(row.get("wmo") or row.get("history_product") or "") for row in rows
        }
        if feed_codes != {str(station["station_code"])}:
            raise ValueError(
                f"BOM feed identity mismatch for {station['station_code']}: "
                f"received {sorted(feed_codes)}"
            )
        feeds.append({"station": station, "document": document})
    return {
        "registry_version": registry["registry_version"],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "station_feeds": feeds,
    }


def extract_station_rows(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a multi-station raw document into observation-grain rows."""

    feeds = document.get("station_feeds")
    if not isinstance(feeds, list) or not feeds:
        raise ValueError("multi-station BOM document has no station_feeds list")
    rows: list[dict[str, Any]] = []
    for feed in feeds:
        rows.extend(extract_rows(feed["document"]))
    return rows


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
