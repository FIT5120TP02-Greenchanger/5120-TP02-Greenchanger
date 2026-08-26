"""Inspect an official Vicmap Tree Extent GeoTIFF before ingestion."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_data.canopy import profile_canopy_raster  # noqa: E402


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("path", type=Path)
args = parser.parse_args()
print(json.dumps(profile_canopy_raster(args.path), indent=2))
