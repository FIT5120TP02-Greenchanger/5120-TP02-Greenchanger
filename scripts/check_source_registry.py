"""Validate the GreenShift data-source registry."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_data.sources import load_source_registry  # noqa: E402


def main() -> None:
    path = ROOT / "config" / "datasets.json"
    registry = load_source_registry(path)
    print(f"Registered sources: {len(registry['datasets'])}")
    print(f"Target SRID: {registry['target_srid']}")
    print(f"Quality threshold: {registry['quality_threshold_pct']:.1f}%")


if __name__ == "__main__":
    main()
