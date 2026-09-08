"""Print readiness and blockers for the four separate predictive models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_data.predictive_models import assess_all_models  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--available-dataset",
        action="append",
        default=[],
        help="Dataset key whose aligned training table has been prepared; repeat as needed.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = assess_all_models(available_dataset_keys=set(args.available_dataset))
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
