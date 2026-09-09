"""Download and normalise metropolitan council tree inventories.

Each council publishes a different schema.  This module translates those
source records into one source-labelled database contract without spatially
matching them to Vicmap Tree Urban points.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import math
from pathlib import Path
import re
import shutil
from typing import Any, Iterator
from urllib.request import Request, urlopen


PLACEHOLDERS = {
    "", "-", "n/a", "na", "none", "null", "unknown", "not applicable",
    "not appliable", "not specified", "to be determined", "tbd",
}


@dataclass(frozen=True)
class CouncilTreeSource:
    key: str
    source_name: str
    publisher: str
    municipality: str
    url: str
    file_suffix: str
    source_crs_override: int | None = None


SOURCES = {
    "brimbank": CouncilTreeSource(
        "brimbank", "Brimbank Street Trees", "Brimbank City Council",
        "City of Brimbank",
        "https://data.gov.au/data/dataset/f918f178-90f5-4c9d-b15a-9447301a381e/resource/0072de55-3e43-4d0e-9a5e-7a9449b828fc/download/brimbank-street-trees.zip",
        ".zip",
    ),
    "yarra": CouncilTreeSource(
        "yarra", "City of Yarra street and park trees", "City of Yarra",
        "City of Yarra",
        "https://data.gov.au/data/dataset/f3c88ce7-504b-4ef7-907f-686037f7420c/resource/6e4186b0-3e00-48f9-a09c-cb60d1d0d49f/download/yarra-street-and-park-trees.geojson",
        ".geojson",
    ),
    "casey": CouncilTreeSource(
        "casey", "City of Casey owned Trees", "City of Casey",
        "City of Casey",
        "https://data.casey.vic.gov.au/api/explore/v2.1/catalog/datasets/council_trees_pt_t1eam/exports/geojson?lang=en&timezone=Australia%2FMelbourne",
        ".geojson",
    ),
    "hobsons_bay": CouncilTreeSource(
        "hobsons_bay", "Street and Park Trees in Hobsons Bay City Council",
        "Hobsons Bay City Council", "City of Hobsons Bay",
        "https://data.gov.au/data/dataset/80051ffe-04d5-4602-b15b-60e0d0e3d153/resource/ea1ec6fc-02bd-4e36-8e43-c990b6a9268d/download/hbcc_street_and_park_trees.json",
        ".geojson",
    ),
    "wyndham": CouncilTreeSource(
        "wyndham", "Wyndham Tree and latest inspection data",
        "Wyndham City Council", "City of Wyndham",
        "https://data.gov.au/data/dataset/0254dee0-5b26-484f-a5ae-5ca3cab46601/resource/fb06e7c8-d037-489b-a963-b747271f2e54/download/trees.json",
        ".geojson", 28355,
    ),
}


def clean(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return None if text.casefold() in PLACEHOLDERS else text


def positive_float(value: Any, *, scale: float = 1.0) -> float | None:
    text = clean(value)
    if text is None:
        return None
    try:
        number = float(text.replace(",", "")) * scale
    except ValueError:
        return None
    return round(number, 4) if math.isfinite(number) and number > 0 else None


def numeric_range(value: Any, *, scale: float = 1.0) -> tuple[float | None, float | None]:
    text = clean(value)
    if text is None:
        return None, None
    numbers = [float(item) * scale for item in re.findall(r"\d+(?:\.\d+)?", text)]
    numbers = [item for item in numbers if math.isfinite(item) and item > 0]
    if not numbers:
        return None, None
    return round(min(numbers), 4), round(max(numbers), 4)


def iso_date(value: Any) -> str | None:
    text = clean(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def scientific_name(genus: Any, species: Any) -> tuple[str | None, str | None]:
    genus_text = clean(genus)
    species_text = clean(species)
    if not genus_text and not species_text:
        return None, None
    if not genus_text:
        return species_text, "species"
    if not species_text or species_text.casefold() in {"sp", "sp.", "species"}:
        return f"{genus_text} sp.", "genus"
    if species_text.casefold().startswith(genus_text.casefold() + " "):
        return species_text, "species"
    abbreviated = re.match(r"^[A-Za-z]\.\s*(.+)$", species_text)
    if abbreviated:
        species_text = abbreviated.group(1)
    return f"{genus_text} {species_text}", "species"


def stable_id(source_key: str, *parts: Any) -> str:
    payload = "|".join("" if item is None else str(item).strip() for item in parts)
    return f"{source_key}:{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:32]}"


def download(source: CouncilTreeSource, directory: Path) -> Path:
    """Download one immutable raw council extract using an atomic rename."""

    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{source.key}_trees{source.file_suffix}"
    part = path.with_suffix(path.suffix + ".part")
    request = Request(source.url, headers={"User-Agent": "GreenChanger-data/1.0"})
    with urlopen(request, timeout=600) as response, part.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)
    part.replace(path)
    return path


def iter_features(source: CouncilTreeSource, path: Path, *, batch_size: int = 25_000) -> Iterator[dict[str, Any]]:
    """Read large spatial files in bounded batches and yield WGS84 records."""

    import pyogrio

    dataset_path = str(path)
    if source.key == "brimbank" and path.suffix.lower() == ".zip":
        dataset_path = f"zip://{path}!Brimbank Street Trees.shp"
    info = pyogrio.read_info(dataset_path)
    total = int(info["features"])
    for offset in range(0, total, batch_size):
        frame = pyogrio.read_dataframe(
            dataset_path, skip_features=offset, max_features=batch_size,
        )
        if source.source_crs_override is not None:
            frame = frame.set_crs(source.source_crs_override, allow_override=True)
        frame = frame.to_crs(4326)
        for _, row in frame.iterrows():
            geometry = row.geometry
            properties = row.drop(labels=[frame.geometry.name]).to_dict()
            yield {"properties": properties, "geometry": geometry}


def feature_count(source_key: str, path: Path) -> int:
    import pyogrio

    source = SOURCES[source_key]
    dataset_path = str(path)
    if source.key == "brimbank" and path.suffix.lower() == ".zip":
        dataset_path = f"zip://{path}!Brimbank Street Trees.shp"
    return int(pyogrio.read_info(dataset_path)["features"])


def iter_normalised(source_key: str, path: Path) -> Iterator[dict[str, Any]]:
    source = SOURCES[source_key]
    for feature in iter_features(source, path):
        yield normalise_feature(source, feature)


def _base(source: CouncilTreeSource, feature: dict[str, Any]) -> dict[str, Any]:
    geometry = feature["geometry"]
    if geometry is not None and not geometry.is_empty and geometry.has_z:
        from shapely import force_2d

        geometry = force_2d(geometry)
    longitude = float(geometry.x) if geometry is not None and not geometry.is_empty else None
    latitude = float(geometry.y) if geometry is not None and not geometry.is_empty else None
    return {
        "inventory_source_key": source.key,
        "municipality": source.municipality,
        "longitude": longitude,
        "latitude": latitude,
        "geometry_wkt": geometry.wkt if longitude is not None and latitude is not None else None,
        "source_srid": 4326,
        "active_record": True,
        "common_name": None,
        "scientific_name": None,
        "display_name": None,
        "genus": None,
        "family": None,
        "taxonomic_precision": None,
        "diameter_breast_height_cm": None,
        "dbh_min_cm": None,
        "dbh_max_cm": None,
        "height_m": None,
        "height_min_m": None,
        "height_max_m": None,
        "canopy_width_m": None,
        "canopy_width_min_m": None,
        "canopy_width_max_m": None,
        "canopy_width_ew_m": None,
        "canopy_width_ns_m": None,
        "year_planted": None,
        "date_planted": None,
        "age_description": None,
        "useful_life_expectancy": None,
        "useful_life_expectancy_years": None,
        "health_status": None,
        "structure_status": None,
        "precinct": None,
        "located_in": None,
        "address": None,
        "source_observed_on": None,
    }


def normalise_feature(source: CouncilTreeSource, feature: dict[str, Any]) -> dict[str, Any]:
    """Translate one council feature to the shared named-tree contract."""

    p = feature["properties"]
    row = _base(source, feature)
    lon, lat = row["longitude"], row["latitude"]

    if source.key == "brimbank":
        botanical, precision = scientific_name(p.get("Genus"), p.get("Species"))
        hmin, hmax = numeric_range(p.get("height"))
        cmin, cmax = numeric_range(p.get("canopy"))
        dmin, dmax = numeric_range(p.get("dbh"))
        row.update(
            source_tree_id=stable_id(source.key, lon, lat, p.get("Location"), botanical),
            scientific_name=botanical, display_name=botanical,
            genus=clean(p.get("Genus")), taxonomic_precision=precision,
            dbh_min_cm=dmin, dbh_max_cm=dmax,
            height_min_m=hmin, height_max_m=hmax,
            canopy_width_min_m=cmin, canopy_width_max_m=cmax,
            located_in=clean(p.get("Type")), address=clean(p.get("Location")),
            active_record=(clean(p.get("Status")) or "").casefold() == "existing",
        )
    elif source.key == "yarra":
        botanical, precision = scientific_name(p.get("genus"), p.get("species"))
        common = clean(p.get("common"))
        row.update(
            source_tree_id=f"yarra:{clean(p.get('ref'))}" if clean(p.get("ref")) else stable_id(source.key, lon, lat, common, botanical),
            common_name=common, scientific_name=botanical,
            display_name=common or botanical, genus=clean(p.get("genus")),
            family=clean(p.get("family")), taxonomic_precision=precision or ("common_name" if common else None),
            diameter_breast_height_cm=positive_float(p.get("dbh")),
            height_m=positive_float(p.get("height")),
            age_description=clean(p.get("maturity")),
            useful_life_expectancy=clean(p.get("ule_min, ule_max")),
            health_status=clean(p.get("health")), structure_status=clean(p.get("structure")),
            located_in=clean(p.get("location")), address=clean(p.get("address")),
            source_observed_on=iso_date(p.get("updated")),
        )
    elif source.key == "casey":
        common = clean(p.get("commonname"))
        botanical = clean(p.get("botanicname"))
        precision = "species" if botanical else None
        if not botanical:
            botanical, precision = scientific_name(p.get("familygenus"), None)
        if not botanical:
            # Casey currently places the usable botanical label in
            # `description` for most rows while the nominal name fields contain
            # "To Be Determined". Preserve that source value instead of
            # treating almost the whole inventory as unnamed.
            description = clean(p.get("description"))
            match = re.match(r"^([A-Z][A-Za-z.-]+)\s+(.+)$", description or "")
            if match:
                genus, remainder = match.groups()
                if remainder.casefold() in {"species", "sp", "sp."}:
                    botanical, precision = f"{genus} sp.", "genus"
                else:
                    botanical, precision = description, "species"
        ew = positive_float(p.get("canopyewwidth_m"))
        ns = positive_float(p.get("canopynswidth_m"))
        row.update(
            source_tree_id=f"casey:{clean(p.get('assetnumber')) or clean(p.get('legacyassetnumber'))}" if clean(p.get("assetnumber")) or clean(p.get("legacyassetnumber")) else stable_id(source.key, lon, lat, common, botanical),
            common_name=common, scientific_name=botanical,
            display_name=common or botanical, genus=(botanical.split()[0] if botanical else None),
            family=clean(p.get("details")), taxonomic_precision=precision or ("common_name" if common else None),
            diameter_breast_height_cm=positive_float(p.get("diameterbreast_hcm")),
            height_m=positive_float(p.get("treeheight_m")),
            canopy_width_m=round((ew + ns) / 2, 4) if ew and ns else ew or ns,
            canopy_width_ew_m=ew, canopy_width_ns_m=ns,
            age_description=clean(p.get("treeage")),
            useful_life_expectancy=clean(p.get("expectedusefullife")),
            health_status=clean(p.get("treehealth")), structure_status=clean(p.get("treestructure")),
            precinct=clean(p.get("ward")), located_in=clean(p.get("treetype")),
            address=" ".join(filter(None, [clean(p.get("address")), clean(p.get("suburb")), clean(p.get("postcode"))])) or None,
            date_planted=iso_date(p.get("acquisitiondate")),
        )
    elif source.key == "hobsons_bay":
        botanical, precision = scientific_name(p.get("Genus"), p.get("Species"))
        dmin, dmax = numeric_range(p.get("dbh_mm"), scale=0.1)
        row.update(
            source_tree_id=stable_id(source.key, lon, lat, p.get("type"), botanical),
            scientific_name=botanical, display_name=botanical,
            genus=clean(p.get("Genus")), taxonomic_precision=precision,
            dbh_min_cm=dmin, dbh_max_cm=dmax,
            precinct=clean(p.get("ward_name")), located_in=clean(p.get("type")),
            address=clean(p.get("suburb")),
        )
    elif source.key == "wyndham":
        common = clean(p.get("tree_common"))
        row.update(
            source_tree_id=f"wyndham:{clean(p.get('tree_id'))}" if clean(p.get("tree_id")) else stable_id(source.key, lon, lat, common),
            common_name=common, display_name=common,
            taxonomic_precision="common_name" if common else None,
            diameter_breast_height_cm=positive_float(p.get("diameter_breast_height")),
            height_m=positive_float(p.get("height")), canopy_width_m=positive_float(p.get("canopy_width")),
            age_description=clean(p.get("tree_age")),
            useful_life_expectancy=clean(p.get("useful_life_expectancy")),
            health_status=clean(p.get("health")), structure_status=clean(p.get("structure")),
            source_observed_on=iso_date(p.get("inspection_date")),
        )
    else:
        raise ValueError(f"Unsupported council tree source: {source.key}")
    return row


def normalise_file(source_key: str, path: Path) -> list[dict[str, Any]]:
    source = SOURCES[source_key]
    return [normalise_feature(source, feature) for feature in iter_features(source, path)]
