"""Reference rules for the Priority 4 property-baseline lookup."""

from __future__ import annotations


LOT_SIZE_RULE = "small <400 m2; medium 400-800 m2; large >800 m2"


def classify_lot_size(area_m2: float | None) -> str:
    """Return the project-defined prototype lot-size category.

    These categories support interface comparisons and are not statutory
    planning or property classifications.
    """

    if area_m2 is None or area_m2 <= 0:
        return "unknown"
    if area_m2 < 400:
        return "small"
    if area_m2 <= 800:
        return "medium"
    return "large"
