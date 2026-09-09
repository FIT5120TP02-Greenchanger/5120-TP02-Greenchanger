"""Extract and normalise the City of Melbourne named-tree inventory."""

from __future__ import annotations

from datetime import date
import gzip
import json
from pathlib import Path
from typing import Any, Iterable, Iterator
from urllib.parse import urlencode
from urllib.request import urlopen


RESOURCE_ID = "0f2a2180-2be0-5a58-a270-7538c35259e6"
DATASTORE_URL = "https://discover.data.vic.gov.au/api/3/action/datastore_search"
PAGE_SIZE = 10_000


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    text = _clean(value)
    if text is None:
        return None
    return float(text)


def _optional_int(value: Any) -> int | None:
    text = _clean(value)
    if text is None:
        return None
    return int(float(text))


def _optional_date(value: Any) -> str | None:
    text = _clean(value)
    if text is None:
        return None
    return date.fromisoformat(text[:10]).isoformat()


def fetch_records(*, page_size: int = PAGE_SIZE) -> list[dict[str, Any]]:
    """Download every record from the official DataVic CKAN API."""

    records: list[dict[str, Any]] = []
    offset = 0
    total: int | None = None
    while total is None or offset < total:
        query = urlencode(
            {"resource_id": RESOURCE_ID, "limit": page_size, "offset": offset}
        )
        with urlopen(f"{DATASTORE_URL}?{query}", timeout=60) as response:
            document = json.load(response)
        if not document.get("success"):
            raise RuntimeError("City of Melbourne tree API returned success=false")
        result = document["result"]
        page = result.get("records", [])
        total = int(result["total"])
        records.extend(page)
        if not page:
            break
        offset += len(page)
    if total is None or len(records) != total:
        raise RuntimeError(
            f"City of Melbourne tree API returned {len(records)} of {total} records"
        )
    return records


def save_raw(records: Iterable[dict[str, Any]], path: Path) -> None:
    """Save a deterministic compressed JSON-lines extract for reproducibility."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as output:
        for record in records:
            output.write(json.dumps(record, sort_keys=True, ensure_ascii=False))
            output.write("\n")


def read_raw(path: Path) -> Iterator[dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as source:
        for line in source:
            if line.strip():
                yield json.loads(line)


def normalise_record(record: dict[str, Any]) -> dict[str, Any]:
    """Convert one CKAN record to the named-tree database contract."""

    common_name = _clean(record.get("common_name"))
    scientific_name = _clean(record.get("scientific_name"))
    latitude = _optional_float(record.get("latitude"))
    longitude = _optional_float(record.get("longitude"))
    return {
        "source_tree_id": _clean(record.get("com_id")),
        "common_name": common_name,
        "scientific_name": scientific_name,
        "display_name": common_name or scientific_name,
        "genus": _clean(record.get("genus")),
        "family": _clean(record.get("family")),
        "diameter_breast_height_cm": _optional_float(
            record.get("diameter_breast_height")
        ),
        "year_planted": _optional_int(record.get("year_planted")),
        "date_planted": _optional_date(record.get("date_planted")),
        "age_description": _clean(record.get("age_description")),
        "useful_life_expectancy": _clean(record.get("useful_life_expectency")),
        "useful_life_expectancy_years": _optional_int(
            record.get("useful_life_expectency_value")
        ),
        "precinct": _clean(record.get("precinct")),
        "located_in": _clean(record.get("located_in")),
        "latitude": latitude,
        "longitude": longitude,
        "geometry_wkt": (
            f"POINT ({longitude} {latitude})"
            if latitude is not None and longitude is not None
            else None
        ),
        "source_srid": 4326,
    }


def normalise_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalise_record(record) for record in records]
