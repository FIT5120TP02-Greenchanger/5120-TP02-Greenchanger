"""Resident-facing environmental classifications for versioned thresholds."""

from __future__ import annotations

from math import isfinite
from numbers import Real


CLASSIFICATION_LABELS = ("Low", "Medium", "High", "Unavailable")

# Historical Melbourne daily-mean air-temperature evidence. The 27.2 C value
# is percentile context requiring at least two consecutive days; it is not a
# one-day category boundary. The retired Victorian 30 C system is exposed only
# as explicitly labelled historical context.
MELBOURNE_HISTORICAL_95TH_PERCENTILE_C = 27.2
MELBOURNE_HIGH_DAILY_MEAN_C = 30.0
HISTORICAL_HEAT_SOURCE = {
    "title": "Planning for extreme heat and heatwaves",
    "publisher": "Victorian Department of Health",
    "url": (
        "https://www.health.vic.gov.au/environmental-health/"
        "planning-for-extreme-heat-and-heatwaves"
    ),
    "locator": "Calculating the average temperature; Figure 1",
}
HISTORICAL_PERCENTILE_SOURCE = {
    "title": "The impact of heatwaves on mortality in Australia: a multicity study",
    "publisher": "BMJ Open",
    "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC3931989/",
    "locator": "Table 2: Heatwave days and threshold",
}
HISTORICAL_HEAT_LIMITATION = (
    "Historical Victorian Central District context only. That system ended in "
    "2021-22 and is not comparable with the current BOM heatwave warning. The "
    "27.2 C research percentile requires two or more consecutive days and is "
    "not used to classify this one-day pair."
)

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
) -> dict[str, object]:
    """Describe one daily-mean pair using retired Victorian heat context.

    The daily mean is ``(forecast maximum + following overnight minimum) / 2``.
    The result is deliberately structured so consumers cannot mistake it for a
    current warning. The 27.2 C research threshold is included as context only
    because its definition requires at least two consecutive days.
    """

    result: dict[str, object] = {
        "classification": "Unavailable",
        "daily_mean_c": None,
        "method": "historical_victorian_central_daily_mean_threshold",
        "status": "historical_context",
        "limitation": HISTORICAL_HEAT_LIMITATION,
        "source": dict(HISTORICAL_HEAT_SOURCE),
        "historical_percentile_context": {
            "threshold_c": MELBOURNE_HISTORICAL_95TH_PERCENTILE_C,
            "minimum_consecutive_days": 2,
            "used_for_this_classification": False,
            "source": dict(HISTORICAL_PERCENTILE_SOURCE),
        },
    }
    values = (forecast_maximum_c, following_overnight_minimum_c)
    if any(value is None for value in values):
        return result
    if not all(isinstance(value, Real) for value in values):
        raise TypeError("forecast maximum and overnight minimum must be numeric or None")
    if not all(isfinite(value) for value in values):
        return result

    daily_mean_c = sum(values) / 2
    result["daily_mean_c"] = round(float(daily_mean_c), 3)
    if daily_mean_c >= MELBOURNE_HIGH_DAILY_MEAN_C:
        result["classification"] = "At or above historical 30 C threshold"
    else:
        result["classification"] = "Below historical 30 C threshold"
    return result


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
