"""Validate the versioned CSV contract for council planting guidance."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path


ALLOWED_STATUSES = {
    "approved", "recommended", "conditional", "approval_required", "not_recommended"
}
ALLOWED_SIZES = {"small", "medium", "large"}


def _text(value: str | None) -> str | None:
    value = str(value or "").strip()
    return value or None


def _number(value: str | None) -> float | None:
    value = _text(value)
    if value is None:
        return None
    number = float(value)
    if number <= 0:
        raise ValueError("dimension and planting-area values must be positive")
    return number


def _date(value: str | None, field: str) -> date | None:
    value = _text(value)
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must use YYYY-MM-DD") from error


def read_rows(path: Path) -> list[dict]:
    """Read guidance without turning absent evidence into approval."""

    with path.open(newline="", encoding="utf-8-sig") as source:
        raw_rows = list(csv.DictReader(source))
    rows: list[dict] = []
    for line_number, raw in enumerate(raw_rows, start=2):
        status = (_text(raw.get("guidance_status")) or "").lower()
        size = (_text(raw.get("mature_size_class")) or "").lower()
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"line {line_number}: invalid guidance_status {status!r}")
        if size not in ALLOWED_SIZES:
            raise ValueError(f"line {line_number}: invalid mature_size_class {size!r}")
        scientific_name = _text(raw.get("scientific_name"))
        common_name = _text(raw.get("common_name"))
        if not scientific_name and not common_name:
            raise ValueError(f"line {line_number}: a scientific or common name is required")
        effective_from = _date(raw.get("effective_from"), "effective_from")
        effective_to = _date(raw.get("effective_to"), "effective_to")
        if effective_from and effective_to and effective_to < effective_from:
            raise ValueError(f"line {line_number}: effective_to precedes effective_from")
        rows.append({
            "source_row_number": line_number,
            "source_name": _text(raw.get("source_name")),
            "publisher": _text(raw.get("publisher")),
            "lga_code": _text(raw.get("lga_code")),
            "lga_name": _text(raw.get("lga_name")),
            "scientific_name": scientific_name,
            "common_name": common_name,
            "mature_size_class": size,
            "mature_height_min_m": _number(raw.get("mature_height_min_m")),
            "mature_height_max_m": _number(raw.get("mature_height_max_m")),
            "mature_canopy_width_min_m": _number(raw.get("mature_canopy_width_min_m")),
            "mature_canopy_width_max_m": _number(raw.get("mature_canopy_width_max_m")),
            "minimum_planting_area_m2": _number(raw.get("minimum_planting_area_m2")),
            "sunlight_requirement": _text(raw.get("sunlight_requirement")),
            "water_need_class": _text(raw.get("water_need_class")),
            "root_risk_class": _text(raw.get("root_risk_class")),
            "site_requirements": _text(raw.get("site_requirements")),
            "guidance_status": status,
            "effective_from": effective_from,
            "effective_to": effective_to,
            "source_url": _text(raw.get("source_url")),
            "licence": _text(raw.get("licence")),
            "limitation": _text(raw.get("limitation")),
        })
    return rows
