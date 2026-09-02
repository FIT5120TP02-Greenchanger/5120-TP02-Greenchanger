"""Obtain and prepare the official analytical Vicmap Tree Extent tiles.

DataShare publishes Tree Extent as 1:250,000 map-sheet ZIP packages rather
than one Melbourne file. The official ABS Melbourne boundary intersects four
packages. This script downloads those packages, safely extracts them, keeps
the native 20 cm analytical pixels, selects intersecting tiles and creates a
small VRT catalogue for downstream canopy processing.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
import math
from pathlib import Path
import shutil
import sys
from urllib.request import Request, urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from greenchanger_data.property_canopy import (  # noqa: E402
    REQUIRED_ASSET_ROLE,
    validate_property_canopy_source,
)


DATASET_UUID = "f6800447-ef34-5f66-acaa-77a5f2936546"
CATALOGUE_URL = "https://discover.data.vic.gov.au/dataset/vicmap-vegetation-tree-extent"
DATASHARE_URL = f"https://datashare.maps.vic.gov.au/search?md={DATASET_UUID}"
DOWNLOAD_BASE = (
    "https://cl-isd-prd-datashare-s3-delivery.s3.amazonaws.com/"
    "PrePackages/VMVEG_TREE_EXTENT"
)
PACKAGE_NAMES = ("MELBOURNE", "PORT_PHILLIP", "WARBURTON", "WARRAGUL")
SOURCE_OBSERVED_FROM = "2013-12-07"
SOURCE_OBSERVED_TO = "2020-11-02"
MAXIMUM_PIXEL_SIZE_M = 2.0


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(chunk_size), b""):
            digest.update(block)
    return digest.hexdigest()


def package_url(name: str) -> str:
    return f"{DOWNLOAD_BASE}/VMVEG_TREE_EXTENT_{name}.zip"


def remote_metadata(url: str) -> dict[str, str | int | None]:
    request = Request(url, method="HEAD")
    with urlopen(request, timeout=60) as response:
        length = response.headers.get("Content-Length")
        return {
            "content_length": int(length) if length else None,
            "etag": response.headers.get("ETag", "").strip('"') or None,
            "last_modified": response.headers.get("Last-Modified"),
        }


def download(url: str, destination: Path, expected_size: int | None) -> None:
    """Download with byte-range resume and an atomic final name."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    if destination.exists():
        if expected_size is None or destination.stat().st_size == expected_size:
            return
        raise ValueError(f"Existing download has the wrong size: {destination}")

    offset = partial.stat().st_size if partial.exists() else 0
    headers = {"Range": f"bytes={offset}-"} if offset else {}
    request = Request(url, headers=headers)
    with urlopen(request, timeout=120) as response, partial.open("ab" if offset else "wb") as output:
        if offset and response.status != 206:
            raise ValueError(f"Server did not honour resume request for {url}")
        shutil.copyfileobj(response, output, length=1024 * 1024)

    if expected_size is not None and partial.stat().st_size != expected_size:
        raise ValueError(
            f"Incomplete download for {destination.name}: "
            f"{partial.stat().st_size} of {expected_size} bytes"
        )
    partial.replace(destination)


def safe_extract(archive: Path, destination: Path) -> None:
    """Extract a ZIP after rejecting absolute and parent-traversal paths."""

    destination.mkdir(parents=True, exist_ok=True)
    resolved_destination = destination.resolve()
    with ZipFile(archive) as bundle:
        bad = []
        for member in bundle.infolist():
            target = (destination / member.filename).resolve()
            if not target.is_relative_to(resolved_destination):
                bad.append(member.filename)
        if bad:
            raise ValueError(f"Unsafe ZIP members in {archive.name}: {bad[:3]}")
        bundle.extractall(destination)


def load_boundary(path: Path):
    from rasterio.warp import transform_geom
    from shapely.geometry import shape

    document = json.loads(path.read_text(encoding="utf-8"))
    features = document.get("features", [])
    if len(features) != 1:
        raise ValueError("Expected exactly one official Melbourne boundary feature")
    geometry = features[0]["geometry"]
    return shape(geometry), transform_geom


def inspect_and_select_tiles(extract_root: Path, boundary_path: Path) -> tuple[list[dict], dict]:
    """Validate analytical tiles and retain those intersecting Melbourne."""

    import numpy as np
    import rasterio
    from shapely.geometry import box, shape

    boundary_wgs84, transform_geom = load_boundary(boundary_path)
    records: list[dict] = []
    rejected: list[str] = []
    for path in sorted(extract_root.rglob("*.tif")):
        with rasterio.open(path) as source:
            validate_property_canopy_source(
                source,
                asset_role=REQUIRED_ASSET_ROLE,
                maximum_pixel_size_m=MAXIMUM_PIXEL_SIZE_M,
            )
            epsg = source.crs.to_epsg()
            if epsg is None:
                raise ValueError(f"Tile has no EPSG code: {path}")
            boundary_source = shape(
                transform_geom("EPSG:4326", f"EPSG:{epsg}", boundary_wgs84.__geo_interface__)
            )
            intersection = boundary_source.intersection(box(*source.bounds))
            if intersection.is_empty or intersection.area <= 0:
                rejected.append(path.name)
                continue

            sample = source.read(1, out_shape=(512, 512), masked=True)
            values = sorted(float(value) for value in np.unique(sample.compressed()))
            invalid_values = [value for value in values if value not in (0.0, 1.0)]
            if invalid_values:
                raise ValueError(f"Unexpected analytical classes in {path.name}: {invalid_values}")
            records.append(
                {
                    "path": str(path.resolve()),
                    "filename": path.name,
                    "sha256": sha256_file(path),
                    "epsg": epsg,
                    "width": source.width,
                    "height": source.height,
                    "dtype": source.dtypes[0],
                    "band_count": source.count,
                    "nodata": source.nodata,
                    "pixel_size_m": [abs(source.transform.a), abs(source.transform.e)],
                    "bounds": list(source.bounds),
                    "block_shape": list(source.block_shapes[0]),
                    "sample_values": values,
                    "melbourne_intersection_km2": round(intersection.area / 1_000_000, 3),
                }
            )

    if not records:
        raise ValueError("No Tree Extent tiles intersect the official Melbourne boundary")
    return records, {
        "boundary_path": str(boundary_path.resolve()),
        "boundary_sha256": sha256_file(boundary_path),
        "boundary_wgs84_bounds": list(boundary_wgs84.bounds),
        "non_intersecting_tile_count": len(rejected),
    }


def gdal_dtype(dtype: str) -> str:
    return {
        "uint8": "Byte",
        "uint16": "UInt16",
        "int16": "Int16",
        "uint32": "UInt32",
        "int32": "Int32",
        "float32": "Float32",
        "float64": "Float64",
    }[dtype]


def build_vrt(records: list[dict], destination: Path, resolution_m: float = 0.2) -> dict:
    """Create a deterministic VRT catalogue without resampling source files."""

    import rasterio

    if resolution_m <= 0:
        raise ValueError("resolution_m must be greater than zero")
    epsgs = {record["epsg"] for record in records}
    dtypes = {record["dtype"] for record in records}
    nodata_values = {record["nodata"] for record in records}
    if len(epsgs) != 1 or len(dtypes) != 1 or len(nodata_values) != 1:
        raise ValueError("VRT inputs must share CRS, data type and nodata value")

    # The tolerance prevents exact grid coordinates such as 0.6 from becoming
    # 0.599999... and creating an unintended extra row or column.
    tolerance = 1e-8
    min_x = math.floor(min(record["bounds"][0] for record in records) / resolution_m + tolerance) * resolution_m
    min_y = math.floor(min(record["bounds"][1] for record in records) / resolution_m + tolerance) * resolution_m
    max_x = math.ceil(max(record["bounds"][2] for record in records) / resolution_m - tolerance) * resolution_m
    max_y = math.ceil(max(record["bounds"][3] for record in records) / resolution_m - tolerance) * resolution_m
    width = int(round((max_x - min_x) / resolution_m))
    height = int(round((max_y - min_y) / resolution_m))
    epsg = next(iter(epsgs))
    dtype = next(iter(dtypes))
    nodata = next(iter(nodata_values))
    with rasterio.open(records[0]["path"]) as first:
        srs = first.crs.to_wkt()

    destination.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f'<VRTDataset rasterXSize="{width}" rasterYSize="{height}">',
        f"  <SRS>{escape(srs)}</SRS>",
        f"  <GeoTransform>{min_x}, {resolution_m}, 0, {max_y}, 0, {-resolution_m}</GeoTransform>",
        f'  <VRTRasterBand dataType="{gdal_dtype(dtype)}" band="1">',
        f"    <NoDataValue>{nodata:g}</NoDataValue>",
    ]
    for record in sorted(records, key=lambda item: item["filename"]):
        source_path = Path(record["path"])
        relative = source_path.relative_to(destination.parent.resolve()) if source_path.is_relative_to(destination.parent.resolve()) else Path(
            __import__("os").path.relpath(source_path, destination.parent.resolve())
        )
        left, bottom, right, top = record["bounds"]
        x_offset = int(round((left - min_x) / resolution_m))
        y_offset = int(round((max_y - top) / resolution_m))
        x_size = int(round((right - left) / resolution_m))
        y_size = int(round((top - bottom) / resolution_m))
        block_y, block_x = record["block_shape"]
        lines.extend(
            [
                "    <SimpleSource>",
                f'      <SourceFilename relativeToVRT="1">{escape(str(relative))}</SourceFilename>',
                "      <SourceBand>1</SourceBand>",
                f'      <SourceProperties RasterXSize="{record["width"]}" RasterYSize="{record["height"]}" DataType="{gdal_dtype(dtype)}" BlockXSize="{block_x}" BlockYSize="{block_y}"/>',
                f'      <SrcRect xOff="0" yOff="0" xSize="{record["width"]}" ySize="{record["height"]}"/>',
                f'      <DstRect xOff="{x_offset}" yOff="{y_offset}" xSize="{x_size}" ySize="{y_size}"/>',
                f"      <NODATA>{nodata:g}</NODATA>",
                "    </SimpleSource>",
            ]
        )
    lines.extend(["  </VRTRasterBand>", "</VRTDataset>"])
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with rasterio.open(destination) as mosaic:
        validate_property_canopy_source(mosaic, asset_role=REQUIRED_ASSET_ROLE)
        if mosaic.crs.to_epsg() != epsg or mosaic.count != 1:
            raise ValueError("Prepared VRT failed CRS/band validation")
    return {
        "path": str(destination.resolve()),
        "sha256": sha256_file(destination),
        "epsg": epsg,
        "pixel_size_m": resolution_m,
        "width": width,
        "height": height,
        "bounds": [min_x, min_y, max_x, max_y],
        "source_tile_count": len(records),
    }


def prepare(args: argparse.Namespace) -> dict:
    packages = []
    for name in PACKAGE_NAMES:
        url = package_url(name)
        metadata = remote_metadata(url)
        archive = args.output_dir / f"VMVEG_TREE_EXTENT_{name}.zip"
        if not args.skip_download:
            download(url, archive, metadata["content_length"])
        if not archive.exists():
            raise FileNotFoundError(archive)
        if metadata["content_length"] and archive.stat().st_size != metadata["content_length"]:
            raise ValueError(f"Package size mismatch: {archive}")
        safe_extract(archive, args.output_dir / "extracted")
        packages.append(
            {
                "name": name,
                "url": url,
                "path": str(archive.resolve()),
                "size_bytes": archive.stat().st_size,
                "sha256": sha256_file(archive),
                **metadata,
            }
        )

    tiles, boundary = inspect_and_select_tiles(args.output_dir / "extracted", args.boundary_file)
    vrt = build_vrt(tiles, args.output_dir / "melbourne_tree_extent_20cm.vrt")
    result = {
        "dataset": "Vicmap Vegetation - Tree Extent",
        "dataset_uuid": DATASET_UUID,
        "catalogue_url": CATALOGUE_URL,
        "datashare_url": DATASHARE_URL,
        "publisher": "Department of Transport and Planning, Victoria",
        "licence": "Creative Commons Attribution 4.0 International",
        "source_observed_from": SOURCE_OBSERVED_FROM,
        "source_observed_to": SOURCE_OBSERVED_TO,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "analytical_class": {"0": "no mapped tree extent", "1": "mapped tree extent", "2": "nodata"},
        "packages": packages,
        "boundary": boundary,
        "selected_tiles": tiles,
        "virtual_mosaic": vrt,
        "limitations": [
            "Tree cover is machine-derived from aerial photography captured between 2013 and 2020.",
            "Mapped tree extent is not a current field survey and does not prove current tree presence, health or ownership.",
            "The VRT is a catalogue of the unchanged native GeoTIFF tiles; source files must remain beside it.",
        ],
    }
    manifest = args.output_dir / "melbourne_tree_extent_manifest.json"
    manifest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    result["manifest"] = str(manifest.resolve())
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--boundary-file",
        type=Path,
        default=ROOT / "data/raw/abs/greater_melbourne_gccsa_2026_20260826T025121Z.geojson",
        help="Official one-feature Melbourne boundary GeoJSON.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data/raw/vicmap/tree_extent_analytical",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Use already-downloaded official ZIP files after verifying their sizes.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = prepare(args)
    print(
        json.dumps(
            {
                "manifest": result["manifest"],
                "packages": len(result["packages"]),
                "selected_tiles": len(result["selected_tiles"]),
                "pixel_size_m": result["virtual_mosaic"]["pixel_size_m"],
                "vrt": result["virtual_mosaic"]["path"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
