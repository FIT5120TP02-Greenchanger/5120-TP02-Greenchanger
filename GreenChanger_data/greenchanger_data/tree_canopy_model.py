"""Experimental mature-tree crown-width model and canopy-area calculations.

The training target is observed crown width for council records explicitly
labelled mature or over-mature.  It is not longitudinal growth evidence, so the
model remains an internal benchmark and must not be represented as a validated
future-growth model.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupShuffleSplit, train_test_split

from greenchanger_data.council_tree_inventories import iter_normalised


RANDOM_STATE = 20260916
TARGET = "mature_canopy_width_m"
NUMERIC_FEATURES = [
    "height_m",
    "diameter_breast_height_cm",
    "longitude",
    "latitude",
]
CATEGORICAL_FEATURES = [
    "species_name",
    "health_status",
    "structure_status",
    "useful_life_expectancy",
]
MODEL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
MATURE_AGE_LABELS = {"mature", "over mature", "over-mature", "overmature"}


@dataclass(frozen=True)
class CanopyModelMetrics:
    total_rows: int
    training_rows: int
    validation_rows: int
    test_rows: int
    species_count: int
    selected_iterations: int
    validation_r2: float
    supported_species_r2: float
    supported_species_mae_m: float
    supported_species_rmse_m: float
    unseen_species_test_rows: int
    unseen_species_r2: float | None

    def as_dict(self) -> dict[str, int | float | None]:
        return {
            "total_rows": self.total_rows,
            "training_rows": self.training_rows,
            "validation_rows": self.validation_rows,
            "test_rows": self.test_rows,
            "species_count": self.species_count,
            "selected_iterations": self.selected_iterations,
            "validation_r2": self.validation_r2,
            "test_r2": self.supported_species_r2,
            "supported_species_r2": self.supported_species_r2,
            "supported_species_mae_m": self.supported_species_mae_m,
            "supported_species_rmse_m": self.supported_species_rmse_m,
            "unseen_species_test_rows": self.unseen_species_test_rows,
            "unseen_species_r2": self.unseen_species_r2,
        }


def canopy_area_m2(canopy_width_m: float) -> float:
    """Convert a crown diameter to circular horizontal crown area."""

    width = float(canopy_width_m)
    if not math.isfinite(width) or width < 0:
        raise ValueError("canopy_width_m must be finite and non-negative")
    return math.pi * (width / 2.0) ** 2


def added_canopy_m2(current_canopy_width_m: float, mature_canopy_width_m: float) -> float:
    """Return non-negative added horizontal crown area at mature width."""

    return max(
        0.0,
        canopy_area_m2(mature_canopy_width_m)
        - canopy_area_m2(current_canopy_width_m),
    )


def _positive_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def prepare_mature_training_frame(records: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    """Create one clean training row per explicitly mature council tree."""

    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for record in records:
        source_tree_id = str(record.get("source_tree_id") or "").strip()
        maturity = str(record.get("age_description") or "").strip().casefold()
        width = _positive_number(record.get("canopy_width_m"))
        height = _positive_number(record.get("height_m"))
        dbh = _positive_number(record.get("diameter_breast_height_cm"))
        longitude = _finite_number(record.get("longitude"))
        latitude = _finite_number(record.get("latitude"))
        species = str(
            record.get("scientific_name")
            or record.get("common_name")
            or record.get("display_name")
            or ""
        ).strip()
        if (
            maturity not in MATURE_AGE_LABELS
            or width is None
            or not species
            or source_tree_id in seen_ids
            or (height is None and dbh is None)
        ):
            continue
        # Conservative physical bounds reject unit errors and placeholders.
        if width > 50 or (height is not None and height > 80) or (dbh is not None and dbh > 500):
            continue
        seen_ids.add(source_tree_id)
        rows.append(
            {
                "source_tree_id": source_tree_id,
                "inventory_source_key": str(record.get("inventory_source_key") or ""),
                "species_name": species,
                "height_m": height,
                "diameter_breast_height_cm": dbh,
                "longitude": longitude,
                "latitude": latitude,
                "health_status": str(record.get("health_status") or "unknown"),
                "structure_status": str(record.get("structure_status") or "unknown"),
                "useful_life_expectancy": str(
                    record.get("useful_life_expectancy") or "unknown"
                ),
                TARGET: width,
            }
        )
    return pd.DataFrame(rows)


def load_local_wyndham_mature_trees(project_root: Path) -> pd.DataFrame:
    """Load the newest local Wyndham extract through the production normaliser."""

    candidates = sorted(
        (project_root / "data" / "raw" / "council_trees" / "wyndham").glob("*/*")
    )
    if not candidates:
        raise FileNotFoundError("no local Wyndham council-tree extract was found")
    return prepare_mature_training_frame(iter_normalised("wyndham", candidates[-1]))


def build_species_profiles(frame: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Build label-free representative inputs for automatic species selection."""

    required = set(MODEL_FEATURES + ["species_name"])
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"species profile data is missing columns: {sorted(missing)}")

    profiles: dict[str, dict[str, Any]] = {}
    for species_name, group in frame.groupby("species_name", sort=True):
        profile: dict[str, Any] = {
            "species_name": species_name,
            "training_record_count": int(len(group)),
        }
        for field in NUMERIC_FEATURES:
            values = pd.to_numeric(group[field], errors="coerce").dropna()
            profile[field] = float(values.median()) if not values.empty else None
        for field in CATEGORICAL_FEATURES:
            if field == "species_name":
                continue
            values = group[field].dropna().astype(str)
            profile[field] = values.mode().iloc[0] if not values.empty else "unknown"
        profiles[str(species_name)] = profile
    return profiles


def build_estimator(
    *,
    iterations: int = 2000,
    random_state: int = RANDOM_STATE,
) -> CatBoostRegressor:
    return CatBoostRegressor(
        iterations=iterations,
        depth=6,
        learning_rate=0.05,
        l2_leaf_reg=3,
        loss_function="RMSE",
        random_seed=random_state,
        verbose=False,
        allow_writing_files=False,
        thread_count=-1,
    )


def _stratification_labels(species: pd.Series) -> pd.Series:
    counts = Counter(species)
    return species.map(lambda value: value if counts[value] >= 2 else "__rare__")


def _score(model: Any, frame: pd.DataFrame) -> tuple[float, float, float]:
    actual = frame[TARGET].to_numpy(dtype=float)
    predicted = np.maximum(model.predict(frame[MODEL_FEATURES]), 0.0)
    return (
        float(r2_score(actual, predicted)),
        float(mean_absolute_error(actual, predicted)),
        float(math.sqrt(mean_squared_error(actual, predicted))),
    )


def train_and_evaluate(
    frame: pd.DataFrame,
    *,
    test_size: float = 0.2,
    random_state: int = RANDOM_STATE,
) -> tuple[CatBoostRegressor, CanopyModelMetrics]:
    """Fit the model and report supported- and unseen-species holdouts."""

    if len(frame) < 100:
        raise ValueError("at least 100 mature-tree records are required")
    required = set(MODEL_FEATURES + [TARGET, "species_name"])
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"training data is missing columns: {sorted(missing)}")
    if frame[TARGET].nunique() < 2:
        raise ValueError("mature canopy-width target must contain multiple values")

    development, test = train_test_split(
        frame,
        test_size=test_size,
        random_state=random_state,
        stratify=_stratification_labels(frame["species_name"]),
    )
    train, validation = train_test_split(
        development,
        test_size=0.25,
        random_state=random_state + 1,
        stratify=_stratification_labels(development["species_name"]),
    )
    tuning_model = build_estimator(random_state=random_state)
    tuning_model.fit(
        train[MODEL_FEATURES],
        train[TARGET],
        cat_features=CATEGORICAL_FEATURES,
        eval_set=(validation[MODEL_FEATURES], validation[TARGET]),
        early_stopping_rounds=100,
    )
    selected_iterations = max(tuning_model.get_best_iteration() + 1, 1)
    validation_r2, _, _ = _score(tuning_model, validation)

    # Refit on the complete 80% development partition using only the iteration
    # count selected on validation. The sealed 20% test partition remains unseen.
    evaluation_model = build_estimator(
        iterations=selected_iterations, random_state=random_state
    )
    evaluation_model.fit(
        development[MODEL_FEATURES],
        development[TARGET],
        cat_features=CATEGORICAL_FEATURES,
    )
    supported_r2, supported_mae, supported_rmse = _score(evaluation_model, test)

    unseen_r2: float | None = None
    unseen_rows = 0
    if frame["species_name"].nunique() >= 5:
        splitter = GroupShuffleSplit(
            n_splits=1, test_size=test_size, random_state=random_state
        )
        group_train_index, group_test_index = next(
            splitter.split(frame, groups=frame["species_name"])
        )
        group_train = frame.iloc[group_train_index]
        group_test = frame.iloc[group_test_index]
        if len(group_test) >= 2 and group_test[TARGET].nunique() >= 2:
            unseen_model = build_estimator(
                iterations=selected_iterations, random_state=random_state
            )
            unseen_model.fit(
                group_train[MODEL_FEATURES],
                group_train[TARGET],
                cat_features=CATEGORICAL_FEATURES,
            )
            unseen_r2, _, _ = _score(unseen_model, group_test)
            unseen_rows = len(group_test)

    metrics = CanopyModelMetrics(
        total_rows=len(frame),
        training_rows=len(development),
        validation_rows=len(validation),
        test_rows=len(test),
        species_count=frame["species_name"].nunique(),
        selected_iterations=selected_iterations,
        validation_r2=validation_r2,
        supported_species_r2=supported_r2,
        supported_species_mae_m=supported_mae,
        supported_species_rmse_m=supported_rmse,
        unseen_species_test_rows=unseen_rows,
        unseen_species_r2=unseen_r2,
    )
    # Return the estimator fitted only on the training partition. The test rows
    # remain untouched and are not folded back into the saved model artifact.
    return evaluation_model, metrics


def predict_canopy(
    model: Any,
    *,
    species_name: str,
    height_m: float | None,
    diameter_breast_height_cm: float | None,
    current_canopy_width_m: float,
    health_status: str = "unknown",
    structure_status: str = "unknown",
    useful_life_expectancy: str = "unknown",
    longitude: float | None = None,
    latitude: float | None = None,
) -> dict[str, float]:
    """Predict mature width and derive current, mature and added crown areas."""

    frame = pd.DataFrame(
        [
            {
                "species_name": species_name,
                "height_m": height_m,
                "diameter_breast_height_cm": diameter_breast_height_cm,
                "longitude": longitude,
                "latitude": latitude,
                "health_status": health_status,
                "structure_status": structure_status,
                "useful_life_expectancy": useful_life_expectancy,
            }
        ]
    )
    width = max(float(model.predict(frame[MODEL_FEATURES])[0]), 0.0)
    return {
        "predicted_mature_canopy_width_m": width,
        "current_canopy_area_m2": canopy_area_m2(current_canopy_width_m),
        "predicted_mature_canopy_area_m2": canopy_area_m2(width),
        "predicted_added_canopy_m2": added_canopy_m2(current_canopy_width_m, width),
    }
