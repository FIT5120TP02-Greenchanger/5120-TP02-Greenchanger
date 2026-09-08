"""Source registry and file-provenance utilities."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any


def load_source_registry(path: Path) -> dict[str, Any]:
    """Read and minimally validate config/datasets.json."""

    registry = json.loads(path.read_text(encoding="utf-8"))
    datasets = registry.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        raise ValueError("source registry must contain a non-empty datasets list")

    required = {
        "key", "name", "publisher", "url", "category", "coverage",
        "licence", "licence_status",
    }
    allowed_licence_statuses = {
        "open_confirmed", "public_domain", "review_required", "restricted"
    }
    seen: set[str] = set()
    for dataset in datasets:
        missing = required - dataset.keys()
        if missing:
            raise ValueError(
                f"dataset {dataset.get('key', '<unknown>')} is missing: {sorted(missing)}"
            )
        if dataset["key"] in seen:
            raise ValueError(f"duplicate dataset key: {dataset['key']}")
        if dataset["licence_status"] not in allowed_licence_statuses:
            raise ValueError(
                f"dataset {dataset['key']} has unsupported licence_status: "
                f"{dataset['licence_status']}"
            )
        seen.add(dataset["key"])

    return registry


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Calculate a reproducible SHA-256 checksum for a downloaded source file."""

    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
