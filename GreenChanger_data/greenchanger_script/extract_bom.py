"""Download and normalise current Greater Melbourne BOM station feeds."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_data.bom import (  # noqa: E402
    DEFAULT_STATION_REGISTRY,
    extract_rows,
    extract_station_rows,
    fetch_observations,
    fetch_station_documents,
    load_station_registry,
    normalise_rows,
    save_raw,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="Optional single official BOM feed override.")
    parser.add_argument(
        "--stations-file", type=Path, default=DEFAULT_STATION_REGISTRY
    )
    parser.add_argument(
        "--raw-dir", type=Path, default=ROOT / "data" / "raw" / "bom"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "interim" / "weather_observation.csv",
    )
    args = parser.parse_args()

    if args.url:
        document = fetch_observations(args.url)
        raw_rows = extract_rows(document)
    else:
        registry = load_station_registry(args.stations_file)
        document = fetch_station_documents(registry)
        raw_rows = extract_station_rows(document)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = args.raw_dir / f"melbourne_observations_{stamp}.json"
    save_raw(document, raw_path)

    rows = normalise_rows(raw_rows)
    if not rows:
        raise SystemExit("BOM feed returned no observation rows")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Raw response: {raw_path}")
    print(f"Normalised rows: {len(rows)}")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
