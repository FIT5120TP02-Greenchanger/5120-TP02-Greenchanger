"""Resumably add verified open GBIF images for every database tree species."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    from . import db
except ImportError:
    import db


API = "https://api.gbif.org/v1"
OPEN_LICENCES = (
    ("CC_BY_4_0", "https://creativecommons.org/licenses/by/4.0/", "CC BY 4.0"),
    ("CC0_1_0", "https://creativecommons.org/publicdomain/zero/1.0/", "CC0 1.0"),
)
USER_AGENT = "GreenChanger/1.0 tree catalogue enrichment (educational project)"


def get_json(path: str, parameters: dict, retries: int = 3) -> dict:
    url = f"{API}/{path}?{urlencode(parameters)}"
    for attempt in range(retries):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def clean_https(value):
    if not value:
        return None
    value = str(value).strip().replace("http://", "https://", 1)
    return value if value.startswith("https://") else None


def unresolved(name: str, status: str, limitation: str, match=None) -> dict:
    match = match or {}
    return {
        "scientific_name": name,
        "gbif_taxon_key": match.get("usageKey"),
        "matched_scientific_name": match.get("scientificName"),
        "taxon_rank": match.get("rank"),
        "taxonomic_status": match.get("status"),
        "match_type": match.get("matchType"),
        "match_confidence": match.get("confidence"),
        "image_url": None,
        "image_page_url": None,
        "image_alt_text": None,
        "image_creator": None,
        "image_rights_holder": None,
        "image_licence": None,
        "image_licence_url": None,
        "image_attribution": None,
        "gbif_occurrence_key": None,
        "enrichment_status": status,
        "limitation": limitation,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def enrich_species(name: str) -> dict:
    try:
        match = get_json("species/match", {"name": name, "verbose": "true"})
        if (
            match.get("matchType") != "EXACT"
            or int(match.get("confidence") or 0) < 95
            or match.get("kingdom") != "Plantae"
            or not match.get("usageKey")
        ):
            return unresolved(
                name, "taxon_unresolved",
                "GBIF did not return an exact Plantae match with confidence >=95; no image was published.",
                match,
            )

        for licence_code, licence_url, licence_label in OPEN_LICENCES:
            result = get_json(
                "occurrence/search",
                {
                    "taxon_key": match["usageKey"],
                    "media_type": "StillImage",
                    "license": licence_code,
                    "limit": 10,
                },
            )
            for occurrence in result.get("results", []):
                if occurrence.get("speciesKey") not in {
                    match.get("speciesKey"), match.get("usageKey")
                }:
                    continue
                for media in occurrence.get("media", []):
                    image_url = clean_https(media.get("identifier"))
                    creator = media.get("creator") or media.get("rightsHolder")
                    rights_holder = media.get("rightsHolder") or creator
                    if not image_url or (licence_code != "CC0_1_0" and not creator):
                        continue
                    occurrence_key = occurrence.get("key")
                    page_url = clean_https(media.get("references")) or (
                        f"https://www.gbif.org/occurrence/{occurrence_key}"
                        if occurrence_key else None
                    )
                    if not page_url:
                        continue
                    credited_to = creator or rights_holder or "GBIF contributor"
                    return {
                        **unresolved(name, "verified_open_image", "", match),
                        "image_url": image_url,
                        "image_page_url": page_url,
                        "image_alt_text": f"Reference photograph of {name}.",
                        "image_creator": credited_to,
                        "image_rights_holder": rights_holder,
                        "image_licence": licence_label,
                        "image_licence_url": licence_url,
                        "image_attribution": (
                            f"{name} photograph by {credited_to}, {licence_label}, "
                            f"via GBIF occurrence {occurrence_key}."
                        ),
                        "gbif_occurrence_key": occurrence_key,
                        "enrichment_status": "verified_open_image",
                        "limitation": (
                            "GBIF occurrence reference image matched through an exact high-confidence taxon result. "
                            "It is illustrative, not the exact nursery stock; appearance varies with age, season, cultivar and conditions."
                        ),
                    }
        return unresolved(
            name, "no_open_image",
            "GBIF returned no usable CC0 or CC BY 4.0 still image for the exact matched taxon; no image was published.",
            match,
        )
    except Exception as error:
        return unresolved(
            name, "request_failed",
            f"GBIF enrichment request failed ({type(error).__name__}); retry before publishing an image.",
        )


def read_checkpoint(path: Path) -> dict[str, dict]:
    rows = {}
    if path.exists():
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    row = json.loads(line)
                    rows[row["scientific_name"]] = row
    return rows


def species_names(max_species: int | None) -> list[str]:
    with db.connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT MIN(BTRIM(scientific_name)) AS scientific_name
               FROM species_profile
               WHERE NULLIF(BTRIM(scientific_name), '') IS NOT NULL
               GROUP BY LOWER(BTRIM(scientific_name))
               ORDER BY scientific_name"""
        )
        names = [row["scientific_name"] for row in cursor.fetchall()]
    return names[:max_species] if max_species else names


UPSERT = """
INSERT INTO tree_species_image_enrichment (
    scientific_name, gbif_taxon_key, matched_scientific_name, taxon_rank,
    taxonomic_status, match_type, match_confidence, image_url, image_page_url,
    image_alt_text, image_creator, image_rights_holder, image_licence,
    image_licence_url, image_attribution, gbif_occurrence_key,
    enrichment_status, limitation, checked_at
) VALUES (
    %(scientific_name)s, %(gbif_taxon_key)s, %(matched_scientific_name)s,
    %(taxon_rank)s, %(taxonomic_status)s, %(match_type)s,
    %(match_confidence)s, %(image_url)s, %(image_page_url)s,
    %(image_alt_text)s, %(image_creator)s, %(image_rights_holder)s,
    %(image_licence)s, %(image_licence_url)s, %(image_attribution)s,
    %(gbif_occurrence_key)s, %(enrichment_status)s, %(limitation)s,
    %(checked_at)s
)
ON CONFLICT (scientific_name) DO UPDATE SET
    gbif_taxon_key = EXCLUDED.gbif_taxon_key,
    matched_scientific_name = EXCLUDED.matched_scientific_name,
    taxon_rank = EXCLUDED.taxon_rank,
    taxonomic_status = EXCLUDED.taxonomic_status,
    match_type = EXCLUDED.match_type,
    match_confidence = EXCLUDED.match_confidence,
    image_url = EXCLUDED.image_url,
    image_page_url = EXCLUDED.image_page_url,
    image_alt_text = EXCLUDED.image_alt_text,
    image_creator = EXCLUDED.image_creator,
    image_rights_holder = EXCLUDED.image_rights_holder,
    image_licence = EXCLUDED.image_licence,
    image_licence_url = EXCLUDED.image_licence_url,
    image_attribution = EXCLUDED.image_attribution,
    gbif_occurrence_key = EXCLUDED.gbif_occurrence_key,
    enrichment_status = EXCLUDED.enrichment_status,
    limitation = EXCLUDED.limitation,
    checked_at = EXCLUDED.checked_at,
    updated_at = CURRENT_TIMESTAMP
"""


def load_rows(rows: list[dict], confirm_shared: bool) -> None:
    if not db.is_local() and not confirm_shared:
        raise SystemExit("Refusing to update shared RDS without --confirm-shared")
    with db.connect() as connection, connection.cursor() as cursor:
        cursor.executemany(UPSERT, rows)
        connection.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--checkpoint", type=Path,
        default=Path("data/interim/tree_catalog/gbif_species_images.jsonl"),
    )
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--max-species", type=int)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument(
        "--retry-failed", action="store_true",
        help="retry only checkpoint rows whose last request failed",
    )
    parser.add_argument("--load-only", action="store_true")
    parser.add_argument("--fetch-only", action="store_true")
    parser.add_argument("--confirm-shared", action="store_true")
    args = parser.parse_args()
    if args.load_only and args.fetch_only:
        parser.error("--load-only and --fetch-only are mutually exclusive")

    completed = read_checkpoint(args.checkpoint)
    if not args.load_only:
        names = species_names(args.max_species)
        if args.refresh:
            pending = names
        elif args.retry_failed:
            pending = [
                name for name in names
                if completed.get(name, {}).get("enrichment_status") == "request_failed"
            ]
        else:
            pending = [name for name in names if name not in completed]
        args.checkpoint.parent.mkdir(parents=True, exist_ok=True)
        with args.checkpoint.open("a", encoding="utf-8") as stream:
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                futures = {pool.submit(enrich_species, name): name for name in pending}
                for index, future in enumerate(as_completed(futures), 1):
                    row = future.result()
                    completed[row["scientific_name"]] = row
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                    stream.flush()
                    if index % 25 == 0 or index == len(pending):
                        print(f"enriched {index}/{len(pending)}")

    rows = list(completed.values())
    if args.max_species:
        rows = rows[: args.max_species]
    if not args.fetch_only:
        load_rows(rows, args.confirm_shared)

    counts = {}
    for row in rows:
        counts[row["enrichment_status"]] = counts.get(row["enrichment_status"], 0) + 1
    print(json.dumps({"rows": len(rows), "status_counts": counts}, indent=2))


if __name__ == "__main__":
    main()
