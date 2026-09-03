"""Resumably rewrite native Tree Extent strips as parcel-friendly tiled GeoTIFFs.

The official analytical pixels and georeferencing are preserved. Only the
physical block layout and lossless compression change, making small random
parcel reads substantially cheaper than reads from the native one-row strips.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_data.sources import sha256_file  # noqa: E402
from greenchanger_script.prepare_vicmap_tree_extent import build_vrt  # noqa: E402


METHOD = "lossless_tiled_geotiff_v1"


def optimise_tile(source_record: dict, destination: Path, block_size: int) -> dict:
    """Create or reuse one verified lossless tiled copy."""

    import numpy as np
    import rasterio
    from rasterio.shutil import copy as copy_raster

    source = Path(source_record["path"])
    source_checksum = source_record["sha256"]
    checkpoint = destination.with_suffix(destination.suffix + ".json")
    if destination.exists() and checkpoint.exists():
        saved = json.loads(checkpoint.read_text(encoding="utf-8"))
        if (
            saved.get("method") == METHOD
            and saved.get("source_sha256") == source_checksum
            and saved.get("block_size") == block_size
            and saved.get("output_sha256") == sha256_file(destination)
        ):
            return saved

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    copy_raster(
        source,
        temporary,
        driver="GTiff",
        tiled=True,
        blockxsize=block_size,
        blockysize=block_size,
        compress="ZSTD",
        predictor=1,
        zstd_level=9,
        bigtiff="YES",
        num_threads="ALL_CPUS",
    )
    with rasterio.open(source) as original, rasterio.open(temporary) as tiled:
        if (
            original.shape != tiled.shape
            or original.crs != tiled.crs
            or original.transform != tiled.transform
            or original.nodata != tiled.nodata
            or original.dtypes != tiled.dtypes
        ):
            temporary.unlink(missing_ok=True)
            raise ValueError(f"Optimised tile metadata differs from source: {source.name}")
        sample_windows = [
            rasterio.windows.Window(0, 0, min(1024, original.width), min(1024, original.height)),
            rasterio.windows.Window(
                max(0, original.width - min(1024, original.width)),
                max(0, original.height - min(1024, original.height)),
                min(1024, original.width),
                min(1024, original.height),
            ),
        ]
        for window in sample_windows:
            if not np.ma.allequal(
                original.read(1, window=window, masked=True),
                tiled.read(1, window=window, masked=True),
            ):
                temporary.unlink(missing_ok=True)
                raise ValueError(f"Optimised tile changed analytical values: {source.name}")
        block_shape = list(tiled.block_shapes[0])
    temporary.replace(destination)
    result = {
        **source_record,
        "path": str(destination.resolve()),
        "source_path": str(source.resolve()),
        "source_sha256": source_checksum,
        "output_sha256": sha256_file(destination),
        "block_shape": block_shape,
        "block_size": block_size,
        "method": METHOD,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    checkpoint.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def optimise(args: argparse.Namespace) -> dict:
    manifest = json.loads(args.source_manifest.read_text(encoding="utf-8"))
    records = manifest.get("selected_tiles", [])
    if not records:
        raise ValueError("Tree Extent manifest contains no selected tiles")
    completed = []
    new_count = 0
    for record in sorted(records, key=lambda item: item["filename"]):
        destination = args.output_dir / record["filename"]
        checkpoint = destination.with_suffix(destination.suffix + ".json")
        was_complete = destination.exists() and checkpoint.exists()
        completed.append(optimise_tile(record, destination, args.block_size))
        if not was_complete:
            new_count += 1
            if args.stop_after_tiles and new_count >= args.stop_after_tiles:
                break

    complete = len(completed) == len(records)
    result = {
        "method": METHOD,
        "source_manifest": str(args.source_manifest.resolve()),
        "source_manifest_sha256": sha256_file(args.source_manifest),
        "source_vrt_sha256": manifest.get("virtual_mosaic", {}).get("sha256"),
        "tiles_complete": len(completed),
        "tiles_total": len(records),
        "complete": complete,
        "output_dir": str(args.output_dir.resolve()),
    }
    if complete:
        vrt_records = [{
            key: value for key, value in record.items()
            if key not in {"source_path", "source_sha256", "output_sha256", "method", "completed_at"}
        } for record in completed]
        vrt = build_vrt(vrt_records, args.output_vrt)
        result["virtual_mosaic"] = vrt
        output_manifest = args.output_vrt.with_suffix(".manifest.json")
        output_manifest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        result["output_manifest"] = str(output_manifest.resolve())
    return result


def parse_args() -> argparse.Namespace:
    raw = ROOT / "data/raw/vicmap/tree_extent_analytical"
    output_dir = ROOT / "data/interim/vicmap/tree_extent_tiled"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, default=raw / "melbourne_tree_extent_manifest.json")
    parser.add_argument("--output-dir", type=Path, default=output_dir)
    parser.add_argument("--output-vrt", type=Path, default=output_dir / "melbourne_tree_extent_20cm_tiled.vrt")
    parser.add_argument("--block-size", type=int, default=512)
    parser.add_argument("--stop-after-tiles", type=int)
    args = parser.parse_args()
    if args.block_size < 128 or args.block_size % 16:
        parser.error("--block-size must be at least 128 and divisible by 16")
    return args


def main() -> None:
    result = optimise(parse_args())
    print(json.dumps(result, indent=2))
    if not result["complete"]:
        print("Run the same command again to resume remaining tiles.", file=sys.stderr)


if __name__ == "__main__":
    main()
