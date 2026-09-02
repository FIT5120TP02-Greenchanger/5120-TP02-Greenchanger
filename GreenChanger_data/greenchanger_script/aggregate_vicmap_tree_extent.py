"""Resumably aggregate native Vicmap Tree Extent tiles to Melbourne 500 m cells."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_data.canopy import aggregate_canopy_tiles_resumable  # noqa: E402
from greenchanger_data.sources import sha256_file  # noqa: E402


def aggregate(args: argparse.Namespace) -> dict:
    source_manifest = json.loads(args.source_manifest.read_text(encoding="utf-8"))
    records = source_manifest.get("selected_tiles", [])
    boundary_bounds = source_manifest.get("boundary", {}).get("boundary_wgs84_bounds")
    if not records or not boundary_bounds:
        raise ValueError("Tree Extent manifest is missing selected tiles or boundary bounds")
    if source_manifest.get("dataset_uuid") != "f6800447-ef34-5f66-acaa-77a5f2936546":
        raise ValueError("Tree Extent manifest does not identify the official DataShare dataset")

    rows, metadata = aggregate_canopy_tiles_resumable(
        records, observed_on=date.fromisoformat(args.observed_on),
        bbox_wgs84=boundary_bounds, checkpoint_path=args.checkpoint,
        grid_size_m=args.grid_size_m, tree_value=args.tree_value,
        stop_after_tiles=args.stop_after_tiles, workers=args.workers,
    )
    result = {
        **metadata,
        "dataset": source_manifest["dataset"],
        "dataset_uuid": source_manifest["dataset_uuid"],
        "catalogue_url": source_manifest["catalogue_url"],
        "source_manifest": str(args.source_manifest.resolve()),
        "source_manifest_sha256": sha256_file(args.source_manifest),
        "source_observed_from": source_manifest["source_observed_from"],
        "source_observed_to": source_manifest["source_observed_to"],
        "prepared_at": datetime.now(timezone.utc).isoformat(),
    }
    if not metadata["complete"]:
        return result

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    with gzip.open(temporary, "wt", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, separators=(",", ":")) + "\n")
    temporary.replace(args.output)
    result.update({
        "output_path": str(args.output.resolve()),
        "output_sha256": sha256_file(args.output),
        "output_rows": len(rows),
    })
    output_manifest = args.output.with_suffix(args.output.suffix + ".manifest.json")
    output_manifest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    result["output_manifest"] = str(output_manifest.resolve())
    return result


def parse_args() -> argparse.Namespace:
    source_dir = ROOT / "data/raw/vicmap/tree_extent_analytical"
    output_dir = ROOT / "data/processed/vicmap"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-manifest", type=Path,
        default=source_dir / "melbourne_tree_extent_manifest.json",
    )
    parser.add_argument(
        "--checkpoint", type=Path,
        default=ROOT / "data/interim/vicmap/tree_extent_500m_checkpoint.npz",
    )
    parser.add_argument(
        "--output", type=Path,
        default=output_dir / "melbourne_tree_extent_500m.jsonl.gz",
    )
    parser.add_argument("--observed-on", default="2020-11-02")
    parser.add_argument("--grid-size-m", type=float, default=500.0)
    parser.add_argument("--tree-value", type=float, default=1.0)
    parser.add_argument(
        "--workers", type=int, default=2,
        help="Native tiles processed concurrently; checkpoints are still written serially.",
    )
    parser.add_argument(
        "--stop-after-tiles", type=int,
        help="Testing/operations switch: checkpoint after this many new tiles.",
    )
    return parser.parse_args()


def main() -> None:
    result = aggregate(parse_args())
    print(json.dumps(result, indent=2))
    if not result["complete"]:
        print("Run the same command again to resume remaining tiles.", file=sys.stderr)


if __name__ == "__main__":
    main()
