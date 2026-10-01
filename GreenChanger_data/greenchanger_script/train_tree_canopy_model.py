#!/usr/bin/env python3
"""Train the experimental mature crown-width model and print held-out R-squared."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import joblib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_data.tree_canopy_model import (  # noqa: E402
    MODEL_FEATURES,
    RANDOM_STATE,
    TARGET,
    build_species_profiles,
    load_local_wyndham_mature_trees,
    train_and_evaluate,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=ROOT / "data" / "processed" / "models" / "tree_canopy_width",
    )
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=RANDOM_STATE)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not 0.1 <= args.test_size <= 0.4:
        raise SystemExit("--test-size must be between 0.1 and 0.4")
    frame = load_local_wyndham_mature_trees(ROOT)
    species_profiles = build_species_profiles(frame)
    model, metrics = train_and_evaluate(
        frame, test_size=args.test_size, random_state=args.random_state
    )

    args.output_directory.mkdir(parents=True, exist_ok=True)
    model_path = args.output_directory / "mature_canopy_width_model.joblib"
    metrics_path = args.output_directory / "metrics.json"
    metrics_payload = {
        **metrics.as_dict(),
        "target": TARGET,
        "features": MODEL_FEATURES,
        "model_path": str(model_path),
        "validation": {
            "supported_species": "stratified held-out tree records",
            "unseen_species": "complete species held out; diagnostic only",
        },
    }
    artifact = {
        "model": model,
        "features": MODEL_FEATURES,
        "target": TARGET,
        "training_scope": "Wyndham council trees labelled Mature or Over mature",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "random_state": args.random_state,
        "metrics": metrics_payload,
        "species_profiles": species_profiles,
        "limitations": (
            "Experimental cross-sectional crown-width benchmark, not a validated "
            "longitudinal growth model. Added canopy is derived geometrically and "
            "must not be interpreted as guaranteed future canopy."
        ),
    }
    joblib.dump(artifact, model_path)
    metrics_path.write_text(
        json.dumps(metrics_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"Total eligible rows: {metrics.total_rows:,}")
    print(f"Training rows: {metrics.training_rows:,}")
    print(f"Internal validation rows: {metrics.validation_rows:,}")
    print(f"Test rows: {metrics.test_rows:,}")
    print(f"Species: {metrics.species_count:,}")
    print(f"Selected boosting iterations: {metrics.selected_iterations:,}")
    print(f"Internal validation R2: {metrics.validation_r2:.4f}")
    print(f"Held-out R2 (supported species): {metrics.supported_species_r2:.4f}")
    print(f"Held-out MAE: {metrics.supported_species_mae_m:.4f} m")
    print(f"Held-out RMSE: {metrics.supported_species_rmse_m:.4f} m")
    if metrics.unseen_species_r2 is not None:
        print(f"Unseen-species R2 (diagnostic): {metrics.unseen_species_r2:.4f}")
    else:
        print("Unseen-species R2 (diagnostic): unavailable")
    print(f"Model: {model_path}")
    print(f"Metrics: {metrics_path}")


if __name__ == "__main__":
    main()
