"""Contracts and readiness gates for four separate environmental models.

No estimator is fitted in this module.  It prevents an untrained or
insufficiently licensed model from being mistaken for a resident-facing
prediction while the source-alignment and validation work is still pending.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_REGISTRY = ROOT / "config" / "predictive_model_registry.json"
DEFAULT_SOURCE_REGISTRY = ROOT / "config" / "datasets.json"

MODEL_CODES = {
    "tree_canopy_growth",
    "melbourne_canopy_change",
    "cooling_association",
    "garden_cooling",
}
OPEN_LICENCE_STATUSES = {"open_confirmed", "public_domain"}
TRAINABLE_STATUSES = {"training_data_prepared", "validation_in_progress", "validated"}


def load_predictive_model_registry(path: Path | None = None) -> dict[str, Any]:
    """Load and validate the four-model registry and its safety policy."""

    registry = json.loads((path or DEFAULT_MODEL_REGISTRY).read_text(encoding="utf-8"))
    models = registry.get("models")
    if not isinstance(models, Mapping) or set(models) != MODEL_CODES:
        raise ValueError("predictive registry must define exactly four separate models")
    policy = registry.get("policy", {})
    if not policy.get("general_model_prohibited"):
        raise ValueError("one general environmental model must remain prohibited")
    if not policy.get("production_requires_open_licence"):
        raise ValueError("production models must require confirmed open licences")
    if not policy.get("production_requires_held_out_validation"):
        raise ValueError("production models must require held-out validation")

    targets: set[str] = set()
    for code, model in models.items():
        required = {"name", "status", "target", "output", "grain", "features", "datasets", "validation", "limitations"}
        missing = required - model.keys()
        if missing:
            raise ValueError(f"model {code} is missing: {sorted(missing)}")
        if model["target"] in targets:
            raise ValueError("separate models must not share an ambiguous target")
        targets.add(model["target"])
        if not model["features"] or not model["datasets"]:
            raise ValueError(f"model {code} must declare features and datasets")
    return registry


def load_source_licence_statuses(path: Path | None = None) -> dict[str, str]:
    """Return each registered source's explicit reuse-review status."""

    registry = json.loads((path or DEFAULT_SOURCE_REGISTRY).read_text(encoding="utf-8"))
    return {
        source["key"]: source.get("licence_status", "review_required")
        for source in registry["datasets"]
    }


def assess_model_readiness(
    model_code: str,
    *,
    available_dataset_keys: set[str] | None = None,
    registry: Mapping[str, Any] | None = None,
    licence_statuses: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Explain why a model may or may not proceed to training or publication."""

    specification = dict(registry or load_predictive_model_registry())
    if model_code not in specification["models"]:
        raise ValueError(f"unknown model_code: {model_code}")
    model = specification["models"][model_code]
    statuses = dict(licence_statuses or load_source_licence_statuses())
    available = set(available_dataset_keys or set())
    required_keys = [row["key"] for row in model["datasets"] if row["required"]]
    missing = sorted(key for key in required_keys if key not in available)
    unlicensed = sorted(
        key for key in required_keys if statuses.get(key) not in OPEN_LICENCE_STATUSES
    )
    training_data_ready = not missing and not unlicensed
    validation_passed = model["status"] == "validated"

    blockers = []
    if missing:
        blockers.append("required_training_data_missing")
    if unlicensed:
        blockers.append("required_source_licence_not_confirmed")
    if model["status"] not in TRAINABLE_STATUSES:
        blockers.append("training_dataset_not_prepared")
    if not validation_passed:
        blockers.append("held_out_validation_not_passed")

    return {
        "registry_version": specification["registry_version"],
        "model_code": model_code,
        "model_name": model["name"],
        "target": model["target"],
        "output": model["output"],
        "declared_status": model["status"],
        "required_dataset_keys": required_keys,
        "missing_required_dataset_keys": missing,
        "unconfirmed_licence_dataset_keys": unlicensed,
        "training_data_ready": training_data_ready,
        "production_ready": training_data_ready and validation_passed,
        "prediction_status": (
            "validated_model_available"
            if training_data_ready and validation_passed
            else specification["policy"]["untrained_output_status"]
        ),
        "blockers": blockers,
        "limitations": model["limitations"],
    }


def assess_all_models(
    *,
    available_dataset_keys: set[str] | None = None,
    registry: Mapping[str, Any] | None = None,
    licence_statuses: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return the independent readiness result for every model."""

    specification = dict(registry or load_predictive_model_registry())
    results = [
        assess_model_readiness(
            code,
            available_dataset_keys=available_dataset_keys,
            registry=specification,
            licence_statuses=licence_statuses,
        )
        for code in sorted(MODEL_CODES)
    ]
    return {
        "registry_version": specification["registry_version"],
        "general_model_used": False,
        "models": results,
        "production_ready_count": sum(row["production_ready"] for row in results),
    }
