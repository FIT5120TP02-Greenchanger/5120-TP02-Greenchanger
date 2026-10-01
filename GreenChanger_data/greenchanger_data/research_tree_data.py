"""Download and normalise open plant-trait and urban-tree-growth evidence."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from hashlib import sha256
import io
import math
from pathlib import Path
import shutil
from typing import Any, Iterable, Iterator
from urllib.request import urlopen
import zipfile

import pandas as pd


AUSTRAITS_VERSION = "7.0.0"
AUSTRAITS_URL = (
    "https://github.com/traitecoevo/austraits.build/releases/download/"
    "v7.0.0/austraits-7.0.0.zip"
)
AUSTRAITS_SHA256 = "2995fb9e5eebf9271f9241b5a6c2e2cbb7b45e8eda5ce4db43c14c68f95e2f3f"
AUSTRAITS_MEMBER = "austraits-7.0.0/traits.csv"
AUSTRAITS_SOURCE_NAME = "AusTraits 7.0.0"

# Traits that can inform the prototype without pretending that physiological
# measurements are horticultural watering instructions or root-risk ratings.
AUSTRAITS_PROTOTYPE_TRAITS = frozenset(
    {
        "establishment_light_environment_index",
        "leaf_water_use_efficiency_instantaneous",
        "leaf_water_use_efficiency_integrated",
        "leaf_water_use_efficiency_intrinsic",
        "lifespan",
        "plant_growth_form",
        "plant_height",
        "plant_tolerance_water_logged_soils",
        "root_structure",
        "root_system_type",
        "stem_growth_habit",
    }
)

URBAN_GROWTH_SOURCE_NAME = (
    "Tree growth of 10 tree species planted in seven Australian cities"
)
URBAN_GROWTH_FILES = {
    "Raw_data_GCB.xlsx": (
        "https://ndownloader.figshare.com/files/54762779",
        "8021eae3315f8a90c877baf3a8b52942",
    ),
    "Climate_data_GCB.xlsx": (
        "https://ndownloader.figshare.com/files/54762788",
        "270f127d4474761e4079e351bd1a1ffe",
    ),
}

SPECIES_CORRECTIONS = {
    "Robinia pseudoacia": "Robinia pseudoacacia",
    "Ulmus parvifolia.": "Ulmus parvifolia",
}


def _checksum(path: Path, algorithm: str = "sha256") -> str:
    digest = __import__("hashlib").new(algorithm)
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_file(
    url: str,
    path: Path,
    *,
    expected_checksum: str,
    algorithm: str = "sha256",
) -> Path:
    """Download atomically and reject any file that fails its published digest."""

    if path.exists() and _checksum(path, algorithm) == expected_checksum:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    with urlopen(url, timeout=180) as response, partial.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)
    actual = _checksum(partial, algorithm)
    if actual != expected_checksum:
        partial.unlink(missing_ok=True)
        raise ValueError(
            f"Checksum mismatch for {path.name}: expected {expected_checksum}, got {actual}"
        )
    partial.replace(path)
    return path


def download_austraits(path: Path) -> Path:
    return download_file(
        AUSTRAITS_URL,
        path,
        expected_checksum=AUSTRAITS_SHA256,
    )


def download_urban_growth(directory: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for filename, (url, md5) in URBAN_GROWTH_FILES.items():
        paths[filename] = download_file(
            url,
            directory / filename,
            expected_checksum=md5,
            algorithm="md5",
        )
    return paths


def combined_checksum(paths: Iterable[Path]) -> str:
    """Return a stable digest for a named collection of source files."""

    digest = sha256()
    for path in sorted(paths, key=lambda value: value.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_checksum(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _finite_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def iter_austraits_rows(
    archive: Path,
    *,
    trait_names: set[str] | frozenset[str] = AUSTRAITS_PROTOTYPE_TRAITS,
    maximum: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Stream prototype-relevant observations from the AusTraits release ZIP."""

    emitted = 0
    with zipfile.ZipFile(archive) as source:
        if AUSTRAITS_MEMBER not in source.namelist():
            raise ValueError(f"AusTraits archive is missing {AUSTRAITS_MEMBER}")
        with source.open(AUSTRAITS_MEMBER) as raw:
            text = io.TextIOWrapper(
                raw, encoding="utf-8", errors="replace", newline=""
            )
            for source_row_number, row in enumerate(csv.DictReader(text), start=2):
                if row.get("trait_name") not in trait_names:
                    continue
                value_text = (row.get("value") or "").strip()
                yield {
                    "source_row_number": source_row_number,
                    "dataset_id": (row.get("dataset_id") or "").strip(),
                    "observation_id": (row.get("observation_id") or "").strip(),
                    "taxon_name": (row.get("taxon_name") or "").strip(),
                    "original_name": (row.get("original_name") or "").strip() or None,
                    "trait_name": (row.get("trait_name") or "").strip(),
                    "value_text": value_text,
                    "value_numeric": _finite_float(value_text),
                    "unit": (row.get("unit") or "").strip() or None,
                    "entity_type": (row.get("entity_type") or "").strip() or None,
                    "value_type": (row.get("value_type") or "").strip() or None,
                    "basis_of_value": (row.get("basis_of_value") or "").strip() or None,
                    "replicates": _finite_float(row.get("replicates")),
                    "basis_of_record": (row.get("basis_of_record") or "").strip() or None,
                    "life_stage": (row.get("life_stage") or "").strip() or None,
                    "location_id": (row.get("location_id") or "").strip() or None,
                    "collection_date": (row.get("collection_date") or "").strip() or None,
                    "source_dataset_id": (row.get("source_id") or "").strip() or None,
                    "measurement_remarks": (
                        row.get("measurement_remarks") or ""
                    ).strip() or None,
                }
                emitted += 1
                if maximum is not None and emitted >= maximum:
                    return


def austraits_counts(archive: Path) -> tuple[int, int]:
    """Return full source row count and prototype-relevant selected row count."""

    total = selected = 0
    with zipfile.ZipFile(archive) as source, source.open(AUSTRAITS_MEMBER) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
        for row in csv.DictReader(text):
            total += 1
            if row.get("trait_name") in AUSTRAITS_PROTOTYPE_TRAITS:
                selected += 1
    return total, selected


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return frame.where(pd.notna(frame), None).to_dict(orient="records")


def read_urban_growth_workbook(path: Path) -> list[dict[str, Any]]:
    return _records(pd.read_excel(path, sheet_name="Data"))


def normalise_growth_rows(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Preserve each tree-ring row and add a within-tree sequence, not a year."""

    sequences: Counter[tuple[str, str, int]] = Counter()
    result: list[dict[str, Any]] = []
    for source_row_number, record in enumerate(records, start=2):
        city = str(record.get("City") or "").strip()
        original_species = str(record.get("Species") or "").strip()
        species = SPECIES_CORRECTIONS.get(original_species, original_species)
        try:
            tree_number = int(record.get("Ttree"))
        except (TypeError, ValueError):
            tree_number = None
        key = (city, species, tree_number or -1)
        sequences[key] += 1
        result.append(
            {
                "source_row_number": source_row_number,
                "city": city,
                "species_name_original": original_species,
                "species_name": species,
                "tree_number": tree_number,
                "ring_sequence": sequences[key],
                "tree_ring_width_mm": _finite_float(record.get("TRW")),
                "basal_area_increment_cm2_year": _finite_float(record.get("BAI")),
            }
        )
    return result


CLIMATE_COLUMNS = ("AP", "PDM", "PWM", "PDQ", "MTWM", "MAT", "MTCM", "IDM", "IP")


def normalise_climate_rows(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse exact duplicates but retain and flag conflicting city-year variants."""

    counts: Counter[tuple[Any, ...]] = Counter()
    for record in records:
        city = str(record.get("City") or "").strip()
        try:
            year = int(record.get("Year"))
        except (TypeError, ValueError):
            year = None
        values = tuple(_finite_float(record.get(column)) for column in CLIMATE_COLUMNS)
        counts[(city, year, *values)] += 1

    grouped: defaultdict[tuple[str, int | None], list[tuple[Any, ...]]] = defaultdict(list)
    for key in counts:
        grouped[(key[0], key[1])].append(key)

    result: list[dict[str, Any]] = []
    source_row_number = 1
    for city_year in sorted(grouped, key=lambda key: (key[0], key[1] or -1)):
        variants = sorted(grouped[city_year], key=lambda key: tuple(-math.inf if v is None else v for v in key[2:]))
        ambiguous = len(variants) > 1
        for variant_number, key in enumerate(variants, start=1):
            source_row_number += 1
            row = {
                "source_row_number": source_row_number,
                "city": key[0],
                "year": key[1],
                "variant_number": variant_number,
                "source_occurrence_count": counts[key],
                "city_year_ambiguous": ambiguous,
            }
            row.update(dict(zip(CLIMATE_COLUMNS, key[2:])))
            result.append(row)
    return result
