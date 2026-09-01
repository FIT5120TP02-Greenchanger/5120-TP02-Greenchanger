"""Resident-facing environmental classifications for versioned thresholds."""

from __future__ import annotations

from math import isfinite
from numbers import Real


CLASSIFICATION_LABELS = ("Low", "Medium", "High", "Unavailable")

# Historical Melbourne daily-mean air-temperature evidence. These boundaries
# must not be applied to an instantaneous BOM observation or Landsat LST.
MELBOURNE_ELEVATED_DAILY_MEAN_C = 27.2
MELBOURNE_HIGH_DAILY_MEAN_C = 30.0

# Prototype canopy progress benchmarks. The current rendered canopy proxy is
# not accurate enough for this absolute classification.
CANOPY_MEDIUM_BENCHMARK_PCT = 15.3
CANOPY_HIGH_BENCHMARK_PCT = 30.0


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


def classify_melbourne_daily_mean_air_temperature(
    forecast_maximum_c: Real | None,
    following_overnight_minimum_c: Real | None,
) -> str:
    """Classify Melbourne daily-mean air heat from a max/min forecast pair.

    The daily mean is ``(forecast maximum + following overnight minimum) / 2``.
    It is not an instantaneous-temperature, Landsat-LST or current BOM
    heatwave-warning classification. The 27.2 C boundary is the published
    Melbourne summer 95th-percentile daily mean; 30 C is the historical
    Victorian Central District heat-health threshold.
    """

    values = (forecast_maximum_c, following_overnight_minimum_c)
    if any(value is None for value in values):
        return "Unavailable"
    if not all(isinstance(value, Real) for value in values):
        raise TypeError("forecast maximum and overnight minimum must be numeric or None")
    if not all(isfinite(value) for value in values):
        return "Unavailable"

    daily_mean_c = sum(values) / 2
    if daily_mean_c >= MELBOURNE_HIGH_DAILY_MEAN_C:
        return "High"
    if daily_mean_c >= MELBOURNE_ELEVATED_DAILY_MEAN_C:
        return "Medium"
    return "Low"


def classify_canopy_benchmark(canopy_percentage: Real | None) -> str:
    """Classify canopy against the official 15.3% baseline and 30% target.

    This is a progress indicator, not a statutory standard. It must only be
    used with a validated analytical canopy percentage at a compatible spatial
    scope; the current rendered API proxy remains restricted to relative
    neighbourhood comparisons.
    """

    if canopy_percentage is None:
        return "Unavailable"
    if not isinstance(canopy_percentage, Real):
        raise TypeError("canopy percentage must be numeric or None")
    if not isfinite(canopy_percentage):
        return "Unavailable"
    if not 0 <= canopy_percentage <= 100:
        raise ValueError("canopy percentage must be between 0 and 100")
    if canopy_percentage >= CANOPY_HIGH_BENCHMARK_PCT:
        return "High"
    if canopy_percentage >= CANOPY_MEDIUM_BENCHMARK_PCT:
        return "Medium"
    return "Low"
