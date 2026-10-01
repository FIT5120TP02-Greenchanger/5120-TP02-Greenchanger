#!/usr/bin/env python3
"""Run the saved mature crown-width model for one tree and print JSON."""

from __future__ import annotations

import argparse
from difflib import get_close_matches
import json
from pathlib import Path
import sys

import joblib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_data.tree_canopy_model import MODEL_FEATURES, predict_canopy  # noqa: E402


DEFAULT_MODEL = (
    ROOT
    / "data"
    / "processed"
    / "models"
    / "tree_canopy_width"
    / "mature_canopy_width_model.joblib"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--species")
    parser.add_argument(
        "--list-species",
        action="store_true",
        help="Print supported automatic species profiles and exit.",
    )
    parser.add_argument("--height-m", type=float)
    parser.add_argument("--dbh-cm", type=float)
    parser.add_argument("--current-canopy-width-m", type=float)
    parser.add_argument("--health")
    parser.add_argument("--structure")
    parser.add_argument("--useful-life")
    parser.add_argument("--longitude", type=float)
    parser.add_argument("--latitude", type=float)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.model.is_file():
        raise SystemExit(
            f"model not found: {args.model}\n"
            "Run: python greenchanger_script/train_tree_canopy_model.py"
        )

    artifact = joblib.load(args.model)
    if artifact.get("features") != MODEL_FEATURES:
        raise SystemExit("model feature contract does not match the current code")
    profiles = artifact.get("species_profiles") or {}
    if args.list_species:
        print(
            json.dumps(
                [
                    {
                        "species_name": name,
                        "training_record_count": profile.get(
                            "training_record_count"
                        ),
                    }
                    for name, profile in sorted(profiles.items())
                ],
                indent=2,
            )
        )
        return
    if not args.species:
        raise SystemExit("provide --species, or use --list-species")

    canonical_names = {name.casefold(): name for name in profiles}
    canonical_name = canonical_names.get(args.species.strip().casefold())
    profile = profiles.get(canonical_name, {}) if canonical_name else {}
    if not profile and (args.height_m is None or args.dbh_cm is None):
        suggestions = get_close_matches(args.species, profiles, n=5, cutoff=0.5)
        suffix = f" Close matches: {', '.join(suggestions)}" if suggestions else ""
        raise SystemExit(
            "species has no automatic profile; provide both --height-m and "
            f"--dbh-cm, or choose a supported species.{suffix}"
        )

    supplied_location = args.longitude is not None or args.latitude is not None
    if supplied_location and (args.longitude is None or args.latitude is None):
        raise SystemExit("provide both --longitude and --latitude, or neither")

    provided = {
        "height_m": args.height_m,
        "diameter_breast_height_cm": args.dbh_cm,
        "health_status": args.health,
        "structure_status": args.structure,
        "useful_life_expectancy": args.useful_life,
        "longitude": args.longitude,
        "latitude": args.latitude,
    }
    resolved = {
        field: value if value is not None else profile.get(field)
        for field, value in provided.items()
    }
    resolved["health_status"] = resolved["health_status"] or "unknown"
    resolved["structure_status"] = resolved["structure_status"] or "unknown"
    resolved["useful_life_expectancy"] = (
        resolved["useful_life_expectancy"] or "unknown"
    )
    current_width = (
        args.current_canopy_width_m
        if args.current_canopy_width_m is not None
        else 0.0
    )
    auto_filled = sorted(
        field for field, value in provided.items() if value is None and field in profile
    )

    prediction = predict_canopy(
        artifact["model"],
        species_name=canonical_name or args.species,
        height_m=resolved["height_m"],
        diameter_breast_height_cm=resolved["diameter_breast_height_cm"],
        current_canopy_width_m=current_width,
        health_status=resolved["health_status"],
        structure_status=resolved["structure_status"],
        useful_life_expectancy=resolved["useful_life_expectancy"],
        longitude=resolved["longitude"],
        latitude=resolved["latitude"],
    )
    metrics = artifact.get("metrics")
    if not isinstance(metrics, dict):
        metrics_path = args.model.with_name("metrics.json")
        if metrics_path.is_file():
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        else:
            metrics = {}
    output = {
        **prediction,
        "species_name": canonical_name or args.species,
        "input_features": resolved,
        "auto_filled_features": auto_filled,
        "species_profile_training_records": profile.get("training_record_count"),
        "current_canopy_assumption": (
            "new_tree_zero_current_canopy"
            if args.current_canopy_width_m is None
            else "user_supplied_current_canopy_width"
        ),
        "model_target": artifact.get("target"),
        "model_held_out_test_r2": metrics.get(
            "test_r2", metrics.get("supported_species_r2")
        ),
        "model_unseen_species_r2": metrics.get("unseen_species_r2"),
        "trained_at": artifact.get("trained_at"),
        "limitation": artifact.get("limitations"),
    }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
