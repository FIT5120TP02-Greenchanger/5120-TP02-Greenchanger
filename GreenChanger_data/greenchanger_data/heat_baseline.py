"""Rules shared by the Landsat baseline heat mosaic and its tests."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any, Iterable


BASELINE_METHOD = "latest_valid_date_with_same_day_overlap_mean_v1"


def choose_latest_daily_baseline(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reference implementation of the SQL mosaic rule for small test cases."""

    by_cell_date: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_cell_date[(str(row["cell_id"]), str(row["observed_on"]))].append(row)

    daily: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (cell_id, observed_on), values in by_cell_date.items():
        temperatures = [float(value["heat_value"]) for value in values]
        scenes = sorted({str(value["source_scene_id"]) for value in values})
        daily[cell_id].append({
            "cell_id": cell_id,
            "observed_on": observed_on,
            "baseline_surface_temperature_c": mean(temperatures),
            "minimum_contributing_temperature_c": min(temperatures),
            "maximum_contributing_temperature_c": max(temperatures),
            "observation_count": len(values),
            "source_scene_ids": scenes,
        })

    return [
        max(candidates, key=lambda candidate: candidate["observed_on"])
        for _, candidates in sorted(daily.items())
    ]
