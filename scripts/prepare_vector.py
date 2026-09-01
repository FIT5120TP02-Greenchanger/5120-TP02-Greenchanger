"""Prepare a vector source for Melbourne spatial integration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_data.spatial import prepare_vector  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--target-srid", type=int, default=7855)
    parser.add_argument(
        "--boundary",
        type=Path,
        help="Optional Melbourne boundary file used to clip the output.",
    )
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    report = prepare_vector(
        args.input,
        args.output,
        target_srid=args.target_srid,
        boundary_path=args.boundary,
    )
    text = json.dumps(report, indent=2)
    print(text)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
