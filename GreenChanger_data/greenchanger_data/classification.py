"""Resident-facing environmental classifications for versioned thresholds."""

from __future__ import annotations

from math import isfinite
from numbers import Real


CLASSIFICATION_LABELS = ("Low", "Medium", "High", "Unavailable")


def classify_environmental_value(
    value: Real | None,
    lower_threshold: Real | None,
    upper_threshold: Real | None,
) -> str:
    """Classify one value against ascending tercile thresholds.

    Missing values or thresholds are always ``Unavailable``. Values exactly on
    the lower boundary are Low; values exactly on the upper boundary are
    Medium. This keeps every valid value in exactly one category.
    """

    if value is None or lower_threshold is None or upper_threshold is None:
        return "Unavailable"
    if not all(
        isinstance(candidate, Real)
        for candidate in (value, lower_threshold, upper_threshold)
    ):
        raise TypeError("value and thresholds must be numeric or None")
    if not all(
        isfinite(candidate)
        for candidate in (value, lower_threshold, upper_threshold)
    ):
        return "Unavailable"
    if lower_threshold > upper_threshold:
        raise ValueError("lower_threshold must not exceed upper_threshold")
    if value <= lower_threshold:
        return "Low"
    if value <= upper_threshold:
        return "Medium"
    return "High"
