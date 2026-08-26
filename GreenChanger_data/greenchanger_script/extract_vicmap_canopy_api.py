"""Create a Melbourne Tree Extent GeoTIFF proxy from the official Vicmap API."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_data.vicmap_tiles import build_canopy_geotiff  # noqa: E402


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--output",
    type=Path,
    default=ROOT / "data" / "raw" / "vicmap" / "tree_extent_api_z14.tif",
)
parser.add_argument("--zoom", type=int, default=14)
parser.add_argument("--workers", type=int, default=12)
args = parser.parse_args()
print(json.dumps(build_canopy_geotiff(args.output, zoom=args.zoom, workers=args.workers), indent=2))
