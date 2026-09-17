"""Add verified open GBIF or Wikimedia Commons tree images with checkpoints."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from difflib import SequenceMatcher
from html import unescape
import json
from pathlib import Path
import re
import threading
import time
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen

try:
    from . import db
except ImportError:
    import db


API = "https://api.gbif.org/v1"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
OPEN_LICENCES = (
    ("CC_BY_4_0", "https://creativecommons.org/licenses/by/4.0/", "CC BY 4.0"),
    ("CC0_1_0", "https://creativecommons.org/publicdomain/zero/1.0/", "CC0 1.0"),
)
GBIF_MEDIA_LICENCES = {
    "cc_by_4_0": ("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/"),
    "cc by 4.0": ("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/"),
    "https://creativecommons.org/licenses/by/4.0": (
        "CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/",
    ),
    "cc0_1_0": ("CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/"),
    "cc0 1.0": ("CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/"),
    "https://creativecommons.org/publicdomain/zero/1.0": (
        "CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/",
    ),
}
# Source review overrides provider metadata when the displayed asset itself
# carries incompatible copyright wording. Keep exact URLs here so future
# refreshes cannot reintroduce a manually rejected image.
BLOCKED_IMAGE_URLS = {
    "https://ibss-images.calacademy.org/static/botany/originals/be/99/be990872-82ef-450e-ba57-cb784cbfdffb.JPG",
    "https://media.canadensys.net/mt-specimens/large/MT00194244.jpg",
    "https://mediaphoto.mnhn.fr/media/1446828003557tuBw6250az1DTVL5",
    "https://sweetgum.nybg.org/images3/1967/024/02513824.jpg",
}
BLOCKED_IMAGE_URL_PATTERN = re.compile(r"(?:/manifest(?:[?#]|$)|\.dzi(?:[?#]|$))", re.IGNORECASE)
USER_AGENT = (
    "GreenChanger/1.0 tree catalogue enrichment "
    "(https://github.com/FIT5120TP02-Greenchanger/5120-TP02-Greenchanger)"
)
COMMONS_LICENCES = {
    "public domain": ("Public domain", "https://creativecommons.org/publicdomain/mark/1.0/"),
    "gfdl 1.2": ("GFDL 1.2", "https://www.gnu.org/licenses/old-licenses/fdl-1.2.html"),
    "cc0 1.0": ("CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/"),
    "cc by 2.0": ("CC BY 2.0", "https://creativecommons.org/licenses/by/2.0/"),
    "cc by 2.5": ("CC BY 2.5", "https://creativecommons.org/licenses/by/2.5/"),
    "cc by 3.0": ("CC BY 3.0", "https://creativecommons.org/licenses/by/3.0/"),
    "cc by 4.0": ("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/"),
    "cc by-sa 2.0": ("CC BY-SA 2.0", "https://creativecommons.org/licenses/by-sa/2.0/"),
    "cc by-sa 2.5": ("CC BY-SA 2.5", "https://creativecommons.org/licenses/by-sa/2.5/"),
    "cc by-sa 3.0": ("CC BY-SA 3.0", "https://creativecommons.org/licenses/by-sa/3.0/"),
    "cc by-sa 4.0": ("CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/"),
}
CATALOG_TAXON_CORRECTIONS = {
    # User-confirmed against the linked Wikipedia taxon page and its Wikidata P225 claim.
    "Acacia ficifolia": "Acacia filicifolia",
    "Flinders Range Wattle, Acacia iteaphylla": "Acacia iteaphylla",
    "Leptospermum obavatum": "Leptospermum obovatum",
    "Weeping tea tree, Leptospermum madidum": "Leptospermum madidum",
    # Kew and Wikipedia use Platanus × hispanica as the accepted name; the
    # council inventories and application model use the synonym below.
    "Platanus x acerifolia": "Platanus × hispanica",
}
WIKIMEDIA_REQUEST_INTERVAL_SECONDS = 0.5
_wikimedia_request_lock = threading.Lock()
_last_wikimedia_request = 0.0

FULL_TREE_TERMS = {
    "adult", "habit", "habitus", "mature", "street tree", "tree", "whole tree",
}
DETAIL_IMAGE_TERMS = {
    "bark", "branch", "bud", "close-up", "closeup", "flower", "foliage", "fruit",
    "herbarium", "leaf", "leaves", "seed", "seedling", "specimen", "twig",
}
DETAIL_FILE_PATTERN = re.compile(
    r"(?:\b(bark|branch|bud|close[ -]?up|distribution|flower|flowers|foliage|fruit|"
    r"herbarium|leaf|leaves|map|range|seed|seedling|sapling|specimen|twig)\b|"
    r"dist(?:map|[a-z]?\d+))",
    re.IGNORECASE,
)
WHOLE_TREE_FILE_PATTERN = re.compile(
    r"\b(adult tree|habit|habitus|mature specimen|mature tree|street tree|whole tree)\b",
    re.IGNORECASE,
)


def get_api_json(api_url: str, parameters: dict, retries: int = 3) -> dict:
    url = f"{api_url}?{urlencode(parameters)}"
    for attempt in range(retries):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            if attempt == retries - 1:
                raise
            retry_after = error.headers.get("Retry-After") if error.headers else None
            delay = 2 ** (attempt + 1)
            if retry_after:
                try:
                    delay = float(retry_after)
                except ValueError:
                    # Retry-After may be an HTTP date instead of delay seconds.
                    pass
            time.sleep(delay)
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError("unreachable")


def get_json(path: str, parameters: dict, retries: int = 3) -> dict:
    return get_api_json(f"{API}/{path}", parameters, retries)


def get_wikimedia_json(api_url: str, parameters: dict) -> dict:
    global _last_wikimedia_request
    with _wikimedia_request_lock:
        elapsed = time.monotonic() - _last_wikimedia_request
        if elapsed < WIKIMEDIA_REQUEST_INTERVAL_SECONDS:
            time.sleep(WIKIMEDIA_REQUEST_INTERVAL_SECONDS - elapsed)
        _last_wikimedia_request = time.monotonic()
    return get_api_json(api_url, parameters, retries=6)


def clean_https(value):
    if not value:
        return None
    value = str(value).strip().replace("http://", "https://", 1)
    return value if value.startswith("https://") else None


def clean_metadata_text(value):
    if not value:
        return None
    text = re.sub(r"<[^>]+>", " ", unescape(str(value)))
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def normalized_gbif_media_licence(value) -> tuple[str, str] | None:
    """Return an approved media-level licence, never an occurrence search filter."""
    if not value:
        return None
    normalized = clean_metadata_text(value)
    if not normalized:
        return None
    key = normalized.strip().casefold().replace("http://", "https://", 1).rstrip("/")
    return GBIF_MEDIA_LICENCES.get(key)


def image_is_blocked(value) -> bool:
    """Return whether source review has explicitly rejected this image URL."""
    url = clean_https(value)
    return bool(url and (url in BLOCKED_IMAGE_URLS or BLOCKED_IMAGE_URL_PATTERN.search(url)))


def claim_value(entity: dict, property_id: str):
    for claim in entity.get("claims", {}).get(property_id, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if value is not None:
            return value
    return None


def exact_wikidata_taxon(name: str) -> tuple[str, dict] | None:
    search = get_wikimedia_json(
        WIKIDATA_API,
        {
            "action": "wbsearchentities", "search": name, "language": "en",
            "format": "json", "limit": 8,
        },
    )
    entity_ids = [item.get("id") for item in search.get("search", []) if item.get("id")]
    if not entity_ids:
        return None
    entities = get_wikimedia_json(
        WIKIDATA_API,
        {
            "action": "wbgetentities", "ids": "|".join(entity_ids),
            "props": "claims", "format": "json",
        },
    ).get("entities", {})
    normalized_name = " ".join(name.split()).casefold()
    for entity_id in entity_ids:
        entity = entities.get(entity_id, {})
        taxon_name = claim_value(entity, "P225")
        if taxon_name and " ".join(taxon_name.split()).casefold() == normalized_name:
            return entity_id, entity
    return None


def exact_wikidata_label_or_alias_taxon(name: str) -> tuple[str, str, dict] | None:
    search = get_wikimedia_json(
        WIKIDATA_API,
        {
            "action": "wbsearchentities", "search": name, "language": "en",
            "format": "json", "limit": 8,
        },
    )
    normalized_name = " ".join(name.split()).casefold()
    exact_items = [
        item for item in search.get("search", [])
        if " ".join(item.get("match", {}).get("text", "").split()).casefold() == normalized_name
        and item.get("id")
    ]
    if not exact_items:
        return None
    entity_ids = [item["id"] for item in exact_items]
    entities = get_wikimedia_json(
        WIKIDATA_API,
        {
            "action": "wbgetentities", "ids": "|".join(entity_ids),
            "props": "claims", "format": "json",
        },
    ).get("entities", {})
    for entity_id in entity_ids:
        entity = entities.get(entity_id, {})
        taxon_name = claim_value(entity, "P225")
        if taxon_name:
            return entity_id, " ".join(taxon_name.split()), entity
    return None


def normalized_taxon_words(name: str) -> list[str]:
    return re.findall(r"[a-z]+", name.casefold())


def deterministic_taxon_candidates(name: str) -> list[tuple[str, str]]:
    candidates = []
    for match in re.finditer(r"\b([A-Z][a-z]{2,})\s+([a-z][a-z-]{2,})\b", name):
        candidate = f"{match.group(1)} {match.group(2)}"
        if candidate.casefold() != " ".join(name.split()).casefold():
            candidates.append((candidate, "embedded_scientific_name"))
    nothospecies = re.match(r"^([A-Z][a-z]+)\s+[xX×]\s*([a-z]+)\b", name)
    if nothospecies:
        candidates.append((
            f"{nothospecies.group(1)} × {nothospecies.group(2)}",
            "normalized_hybrid_name",
        ))
    return candidates


def wikipedia_title_candidate(name: str) -> str | None:
    original = re.match(r"^([A-Z][a-z]+)\s+([a-z][A-Za-z-]{3,})\b", name)
    if not original or original.group(2).casefold() in {"species"}:
        return None
    genus, epithet = original.groups()
    result = get_wikimedia_json(
        WIKIPEDIA_API,
        {
            "action": "query", "format": "json", "list": "prefixsearch",
            "pssearch": f"{genus} {epithet[:2]}", "psnamespace": 0, "pslimit": 50,
        },
    )
    original_binomial = f"{genus} {epithet}".casefold()
    scored = []
    for item in result.get("query", {}).get("prefixsearch", []):
        title_match = re.match(r"^([A-Z][a-z]+)\s+(×\s*)?([a-z][a-z-]+)\b", item.get("title", ""))
        if not title_match or title_match.group(1).casefold() != genus.casefold():
            continue
        candidate = f"{title_match.group(1)} " + (
            f"× {title_match.group(3)}" if title_match.group(2) else title_match.group(3)
        )
        similarity = SequenceMatcher(None, original_binomial, candidate.casefold()).ratio()
        if candidate.casefold() != original_binomial and similarity >= 0.94:
            scored.append((similarity, candidate))
    scored.sort(reverse=True)
    if not scored or (len(scored) > 1 and scored[0][0] - scored[1][0] < 0.003):
        return None
    return scored[0][1]


def commons_search_file_titles(name: str) -> list[str]:
    result = get_wikimedia_json(
        COMMONS_API,
        {
            "action": "query", "format": "json", "list": "search",
            "srsearch": f'intitle:"{name}"', "srnamespace": 6, "srlimit": 20,
        },
    )
    taxon_words = normalized_taxon_words(name)[:2]
    rejected_words = {"distribution", "map", "range", "herbarium", "specimen"}
    titles = []
    for item in result.get("query", {}).get("search", []):
        title = item.get("title", "")
        title_words = normalized_taxon_words(title.removeprefix("File:"))
        if (
            taxon_words
            and all(word in title_words for word in taxon_words)
            and not rejected_words.intersection(title_words)
        ):
            titles.append(title)
    return titles


def wikipedia_lead_file_title(taxon_name: str) -> str | None:
    result = get_wikimedia_json(
        WIKIPEDIA_API,
        {
            "action": "query", "format": "json", "titles": taxon_name,
            "prop": "pageimages", "piprop": "name", "redirects": 1,
        },
    )
    page = next(iter(result.get("query", {}).get("pages", {}).values()), {})
    filename = page.get("pageimage")
    return f"File:{filename.replace('_', ' ')}" if filename else None


def commons_file_titles(
    entity: dict, taxon_name: str, prefer_full_tree: bool = False,
) -> list[str]:
    titles = []
    if prefer_full_tree:
        wikipedia_lead = wikipedia_lead_file_title(taxon_name)
        if wikipedia_lead:
            titles.append(wikipedia_lead)
    featured_image = claim_value(entity, "P18")
    if featured_image:
        titles.append(f"File:{featured_image}")
    # Wikipedia's lead image is editorially selected to represent the taxon.
    # In full-tree mode, avoid an expensive and less deterministic category
    # crawl when a lead image is available; P18 remains the licence fallback.
    if prefer_full_tree and titles:
        return list(dict.fromkeys(titles))
    category = claim_value(entity, "P373")
    if category:
        result = get_wikimedia_json(
            COMMONS_API,
            {
                "action": "query", "format": "json", "list": "categorymembers",
                "cmtitle": f"Category:{category}", "cmnamespace": 6,
                "cmtype": "file", "cmlimit": 20,
            },
        )
        titles.extend(item["title"] for item in result.get("query", {}).get("categorymembers", []))
    if not titles:
        titles.extend(commons_search_file_titles(taxon_name))
    return list(dict.fromkeys(titles))


def commons_image_preference(page: dict, preferred_title: str | None = None) -> int:
    """Rank a Commons image for catalogue use, favouring a mature whole-tree view."""
    info = next(iter(page.get("imageinfo", [])), {})
    metadata = info.get("extmetadata", {})
    searchable = " ".join(filter(None, (
        page.get("title"),
        clean_metadata_text(metadata.get("ObjectName", {}).get("value")),
        clean_metadata_text(metadata.get("ImageDescription", {}).get("value")),
        clean_metadata_text(metadata.get("Categories", {}).get("value")),
    ))).casefold()
    score = 300 if preferred_title and page.get("title") == preferred_title else 0
    score += 80 * sum(term in searchable for term in FULL_TREE_TERMS)
    score -= 120 * sum(term in searchable for term in DETAIL_IMAGE_TERMS)
    return score


def file_title_is_detail_only(title: str | None) -> bool:
    text = (title or "").replace("_", " ")
    return bool(DETAIL_FILE_PATTERN.search(text)) and not bool(
        WHOLE_TREE_FILE_PATTERN.search(text)
    )


def commons_page_row(
    name: str, image_taxon_name: str, base_row: dict, entity_id: str,
    page: dict, match_basis: str,
) -> dict | None:
    info = next(iter(page.get("imageinfo", [])), {})
    if not str(info.get("mime", "")).startswith("image/"):
        return None
    if file_title_is_detail_only(page.get("title")):
        return None
    metadata = info.get("extmetadata", {})
    licence_key = clean_metadata_text(metadata.get("LicenseShortName", {}).get("value"))
    licence = COMMONS_LICENCES.get((licence_key or "").casefold())
    if not licence:
        return None
    licence_label, licence_url = licence
    creator = clean_metadata_text(metadata.get("Artist", {}).get("value"))
    rights_holder = clean_metadata_text(metadata.get("Credit", {}).get("value")) or creator
    if licence_label not in {"Public domain", "CC0 1.0"} and not creator:
        return None
    creator = creator or rights_holder or "Wikimedia Commons contributor"
    image_url = clean_https(info.get("thumburl") or info.get("url"))
    page_url = clean_https(info.get("descriptionurl"))
    if not image_url or image_is_blocked(image_url) or not page_url:
        return None
    file_title = page.get("title")
    return {
        **base_row,
        "matched_scientific_name": image_taxon_name,
        "taxonomic_status": "WIKIDATA_EXACT_P225",
        "match_type": "EXACT",
        "match_confidence": 100,
        "image_url": image_url,
        "image_page_url": page_url,
        "image_alt_text": (
            f"Representative photograph of the genus {image_taxon_name} for unresolved record {name}."
            if match_basis == "genus_representative"
            else f"Reference photograph of {image_taxon_name} for {name}."
        ),
        "image_creator": creator,
        "image_rights_holder": rights_holder or creator,
        "image_licence": licence_label,
        "image_licence_url": licence_url,
        "image_attribution": (
            f"{image_taxon_name} reference image by {creator}, {licence_label}, "
            f"via Wikimedia Commons ({file_title})."
        ),
        "gbif_occurrence_key": None,
        "image_source_name": "Wikimedia Commons",
        "taxon_verification_id": entity_id,
        "commons_file_title": file_title,
        "enrichment_status": "verified_open_image",
        "limitation": (
            f"Wikimedia Commons reference image for {image_taxon_name}, selected with preference for "
            "the Wikipedia lead image and metadata indicating a mature, whole-tree view. The Wikidata item "
            "whose P225 taxon name exactly matches the displayed image taxon. "
            + {
                "exact_name": "The Wikidata taxon exactly matches the catalogue name.",
                "gbif_exact_canonical": "GBIF supplied this exact canonical taxon for the catalogue name.",
                "parent_species": "This is the verified parent species; it is not necessarily the named cultivar/form.",
                "corrected_spelling": "GBIF supplied this high-confidence spelling correction within the same genus.",
                "genus_representative": "This is a genus-level representative only because the catalogue record is explicitly unidentified to species.",
                "wikidata_exact_label_alias": "The catalogue name exactly matches an English Wikidata label or alias on this taxon item.",
                "embedded_scientific_name": "The image taxon is an explicit botanical binomial embedded in the catalogue value.",
                "normalized_hybrid_name": "The image taxon exactly matches the catalogue hybrid after normalising the multiplication symbol.",
                "user_confirmed_wikipedia_correction": "The catalogue spelling was corrected to the taxon on the user-confirmed Wikipedia page and exact Wikidata P225 item.",
                "wikipedia_title_correction": "A uniquely close Wikipedia binomial title supplied this spelling correction and the Wikidata P225 item exactly verifies it.",
            }[match_basis]
            + " It is illustrative, not exact nursery stock; appearance varies with age, season, cultivar and conditions."
        ),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def commons_images(
    name: str, image_taxon_name: str, base_row: dict,
    entity_id: str, file_titles: list[str], match_basis: str,
) -> dict | None:
    if not file_titles:
        return None
    result = get_wikimedia_json(
        COMMONS_API,
        {
            "action": "query", "format": "json", "titles": "|".join(file_titles),
            "prop": "imageinfo", "iiprop": "url|extmetadata|mime", "iiurlwidth": 1200,
        },
    )
    pages = result.get("query", {}).get("pages", {})
    preferred_title = file_titles[0] if file_titles else None
    ranked_pages = sorted(
        pages.values(),
        key=lambda page: commons_image_preference(page, preferred_title),
        reverse=True,
    )
    for page in ranked_pages:
        row = commons_page_row(
            name, image_taxon_name, base_row, entity_id, page, match_basis,
        )
        if row:
            return row
    return None


def mediawiki_title_key(value: str | None) -> str:
    return " ".join((value or "").replace("_", " ").split()).casefold()


def mediawiki_pages_by_requested_title(result: dict, requested: list[str]) -> dict[str, dict]:
    query = result.get("query", {})
    aliases = {}
    for group in ("normalized", "redirects"):
        for item in query.get(group, []):
            aliases[mediawiki_title_key(item.get("from"))] = mediawiki_title_key(item.get("to"))
    pages = {
        mediawiki_title_key(page.get("title")): page
        for page in query.get("pages", {}).values()
    }
    resolved = {}
    for title in requested:
        key = mediawiki_title_key(title)
        seen = set()
        while key in aliases and key not in seen:
            seen.add(key)
            key = aliases[key]
        if key in pages:
            resolved[title] = pages[key]
    return resolved


def enrich_full_tree_batch(names: list[str], completed: dict[str, dict]) -> list[dict]:
    """Replace a batch with exact Wikidata-verified Wikipedia lead images."""
    wikipedia = get_wikimedia_json(
        WIKIPEDIA_API,
        {
            "action": "query", "format": "json", "titles": "|".join(names),
            "prop": "pageimages|pageprops", "piprop": "name",
            "ppprop": "wikibase_item", "redirects": 1,
        },
    )
    wikipedia_pages = mediawiki_pages_by_requested_title(wikipedia, names)
    candidates = {}
    for name, page in wikipedia_pages.items():
        entity_id = page.get("pageprops", {}).get("wikibase_item")
        filename = page.get("pageimage")
        if entity_id and filename and "missing" not in page:
            candidates[name] = {
                "entity_id": entity_id,
                "file_title": f"File:{filename.replace('_', ' ')}",
            }

    entity_ids = list(dict.fromkeys(
        candidate["entity_id"] for candidate in candidates.values()
    ))
    entities = {}
    if entity_ids:
        entities = get_wikimedia_json(
            WIKIDATA_API,
            {
                "action": "wbgetentities", "ids": "|".join(entity_ids),
                "props": "claims", "format": "json",
            },
        ).get("entities", {})

    verified = {}
    for name, candidate in candidates.items():
        taxon_name = claim_value(entities.get(candidate["entity_id"], {}), "P225")
        original_words = normalized_taxon_words(name)
        taxon_words = normalized_taxon_words(taxon_name or "")
        if not taxon_name or len(taxon_words) < 2 or original_words[:2] != taxon_words[:2]:
            continue
        candidate["taxon_name"] = taxon_name
        candidate["match_basis"] = (
            "exact_name"
            if " ".join(name.split()).casefold() == " ".join(taxon_name.split()).casefold()
            else "parent_species"
        )
        verified[name] = candidate

    file_titles = list(dict.fromkeys(
        candidate["file_title"] for candidate in verified.values()
    ))
    commons_pages = {}
    if file_titles:
        commons = get_wikimedia_json(
            COMMONS_API,
            {
                "action": "query", "format": "json", "titles": "|".join(file_titles),
                "prop": "imageinfo", "iiprop": "url|extmetadata|mime", "iiurlwidth": 1200,
            },
        )
        commons_pages = mediawiki_pages_by_requested_title(commons, file_titles)

    rows = []
    for name in names:
        base_row = completed[name]
        candidate = verified.get(name)
        page = commons_pages.get(candidate["file_title"]) if candidate else None
        row = None
        if candidate and page:
            row = commons_page_row(
                name, candidate["taxon_name"], base_row, candidate["entity_id"],
                page, candidate["match_basis"],
            )
        if not row:
            row = {
                **base_row,
                "limitation": (
                    (base_row.get("limitation") or "").rstrip()
                    + " Mature full-tree preference checked; no approved exact-taxon "
                    "Wikipedia lead image was available, so the existing licensed image was retained."
                ).strip(),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        rows.append(row)
    return rows


def commons_taxon_candidates(name: str, base_row: dict, broader: bool = False) -> list[tuple[str, str]]:
    candidates = []
    if name in CATALOG_TAXON_CORRECTIONS:
        candidates.append((
            CATALOG_TAXON_CORRECTIONS[name],
            "user_confirmed_wikipedia_correction",
        ))
    taxon_key = base_row.get("gbif_taxon_key")
    if taxon_key and base_row.get("match_type") == "EXACT":
        taxon = get_json(f"species/{taxon_key}", {})
        canonical_name = taxon.get("canonicalName")
        if canonical_name:
            basis = "gbif_exact_canonical" if canonical_name.casefold() == name.casefold() else "parent_species"
            candidates.append((canonical_name, basis))
            if (taxon.get("rank") or base_row.get("taxon_rank") or "").upper() in {
                "FORM", "VARIETY", "SUBSPECIES",
            }:
                parent_words = normalized_taxon_words(canonical_name)[:2]
                if len(parent_words) == 2:
                    candidates.append((" ".join(parent_words).capitalize(), "parent_species"))
    if broader and taxon_key and base_row.get("match_type") in {"HIGHERRANK", "FUZZY"}:
        taxon = get_json(f"species/{taxon_key}", {})
        canonical_name = " ".join((taxon.get("canonicalName") or "").split())
        rank = (taxon.get("rank") or base_row.get("taxon_rank") or "").upper()
        original_words = normalized_taxon_words(name)
        canonical_words = normalized_taxon_words(canonical_name)
        if base_row.get("match_type") == "HIGHERRANK" and rank == "SPECIES":
            if len(canonical_words) >= 2 and original_words[:2] == canonical_words[:2]:
                candidates.append((canonical_name, "parent_species"))
        elif base_row.get("match_type") == "FUZZY" and rank == "SPECIES":
            confidence = int(base_row.get("match_confidence") or 0)
            original_binomial = " ".join(original_words[:2])
            canonical_binomial = " ".join(canonical_words[:2])
            same_genus = original_words and canonical_words and original_words[0] == canonical_words[0]
            similarity = SequenceMatcher(None, original_binomial, canonical_binomial).ratio()
            if (
                (confidence >= 93 and same_genus and similarity >= 0.93)
                or similarity >= 0.94
            ):
                candidates.append((canonical_name, "corrected_spelling"))
        elif (
            base_row.get("match_type") == "HIGHERRANK"
            and rank == "GENUS"
            and re.search(r"\bsp\.?\b", name, re.IGNORECASE)
            and original_words and canonical_words and original_words[0] == canonical_words[0]
        ):
            candidates.append((canonical_name, "genus_representative"))
    if broader:
        candidates.extend(deterministic_taxon_candidates(name))
        if not candidates:
            wikipedia_candidate = wikipedia_title_candidate(name)
            if wikipedia_candidate:
                candidates.append((wikipedia_candidate, "wikipedia_title_correction"))
    candidates.append((name, "exact_name"))
    return list(dict.fromkeys(
        (" ".join(candidate.split()), basis)
        for candidate, basis in candidates if candidate
    ))


def enrich_species_with_commons(
    name: str, base_row: dict, broader: bool = False, prefer_full_tree: bool = False,
) -> dict:
    for image_taxon_name, match_basis in commons_taxon_candidates(name, base_row, broader):
        if broader and match_basis == "exact_name":
            alias_taxon = exact_wikidata_label_or_alias_taxon(image_taxon_name)
            if alias_taxon:
                entity_id, image_taxon_name, entity = alias_taxon
                row = commons_images(
                    name, image_taxon_name, base_row, entity_id,
                    commons_file_titles(entity, image_taxon_name, prefer_full_tree),
                    "wikidata_exact_label_alias",
                )
                if row:
                    return row
            continue
        taxon = exact_wikidata_taxon(image_taxon_name)
        if not taxon:
            continue
        entity_id, entity = taxon
        row = commons_images(
            name, image_taxon_name, base_row, entity_id,
            commons_file_titles(entity, image_taxon_name, prefer_full_tree), match_basis,
        )
        if row:
            return row
    return base_row


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
        "image_source_name": None,
        "taxon_verification_id": None,
        "commons_file_title": None,
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

        for licence_code, _requested_url, _requested_label in OPEN_LICENCES:
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
                    if image_is_blocked(image_url):
                        continue
                    approved_licence = normalized_gbif_media_licence(media.get("license"))
                    if not approved_licence:
                        # The occurrence search filter does not establish the media
                        # item's reuse rights. Missing, NC, ND, custom and
                        # all-rights-reserved media licences are rejected.
                        continue
                    licence_label, licence_url = approved_licence
                    creator = media.get("creator") or media.get("rightsHolder")
                    rights_holder = media.get("rightsHolder") or creator
                    if not image_url or (licence_label != "CC0 1.0" and not creator):
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
                        "image_source_name": "GBIF occurrence media API",
                        "taxon_verification_id": str(match.get("usageKey")),
                        "commons_file_title": None,
                        "enrichment_status": "verified_open_image",
                        "limitation": (
                            "GBIF occurrence reference image matched through an exact high-confidence taxon result. "
                            "It is illustrative, not the exact nursery stock; appearance varies with age, season, cultivar and conditions."
                        ),
                    }
        return unresolved(
            name, "no_open_image",
            "GBIF returned no still image with a media-level CC0 1.0 or CC BY 4.0 licence for the exact matched taxon; no image was published.",
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
                    if not row.get("image_source_name"):
                        row["image_source_name"] = "GBIF occurrence media API"
                    if not row.get("taxon_verification_id") and row.get("gbif_taxon_key"):
                        row["taxon_verification_id"] = str(row["gbif_taxon_key"])
                    row.setdefault("taxon_verification_id", None)
                    row.setdefault("commons_file_title", None)
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
    image_source_name, taxon_verification_id, commons_file_title,
    enrichment_status, limitation, checked_at
) VALUES (
    %(scientific_name)s, %(gbif_taxon_key)s, %(matched_scientific_name)s,
    %(taxon_rank)s, %(taxonomic_status)s, %(match_type)s,
    %(match_confidence)s, %(image_url)s, %(image_page_url)s,
    %(image_alt_text)s, %(image_creator)s, %(image_rights_holder)s,
    %(image_licence)s, %(image_licence_url)s, %(image_attribution)s,
    %(gbif_occurrence_key)s, %(image_source_name)s,
    %(taxon_verification_id)s, %(commons_file_title)s,
    %(enrichment_status)s, %(limitation)s,
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
    image_source_name = EXCLUDED.image_source_name,
    taxon_verification_id = EXCLUDED.taxon_verification_id,
    commons_file_title = EXCLUDED.commons_file_title,
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
    parser.add_argument(
        "--species", action="append", default=[],
        help="process only this scientific name; may be supplied more than once",
    )
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument(
        "--commons-fallback", action="store_true",
        help="retry missing images through an exact Wikidata taxon and Wikimedia Commons",
    )
    parser.add_argument(
        "--commons-broader-fallback", action="store_true",
        help=(
            "retry all missing rows using exact Wikidata names plus audited parent-species, "
            "spelling-correction and explicit genus-placeholder fallbacks"
        ),
    )
    parser.add_argument(
        "--retry-failed", action="store_true",
        help="retry only checkpoint rows whose last request failed",
    )
    parser.add_argument(
        "--revalidate-gbif-licences", action="store_true",
        help=(
            "re-enrich every published GBIF image and replace or quarantine records "
            "that lack an approved media-level licence"
        ),
    )
    parser.add_argument(
        "--prefer-full-tree", action="store_true",
        help=(
            "replace existing images, where possible, with an exact-taxon Wikimedia Commons image "
            "ranked to prefer a mature whole-tree view; keep the current image as fallback"
        ),
    )
    parser.add_argument("--load-only", action="store_true")
    parser.add_argument("--fetch-only", action="store_true")
    parser.add_argument("--confirm-shared", action="store_true")
    args = parser.parse_args()
    if args.load_only and args.fetch_only:
        parser.error("--load-only and --fetch-only are mutually exclusive")

    completed = read_checkpoint(args.checkpoint)
    if not args.load_only:
        commons_mode = (
            args.commons_fallback or args.commons_broader_fallback or args.prefer_full_tree
        )
        checkpoint_only_mode = commons_mode or args.revalidate_gbif_licences
        names = list(completed) if checkpoint_only_mode else species_names(args.max_species)
        if args.species:
            missing_names = [name for name in args.species if name not in completed]
            if checkpoint_only_mode and missing_names:
                parser.error(
                    "--species is not present in the checkpoint: " + ", ".join(missing_names)
                )
            names = args.species
        if commons_mode and args.max_species:
            names = names[:args.max_species]
        if args.revalidate_gbif_licences:
            names = list(completed)
            if args.max_species:
                names = names[:args.max_species]
            pending = [
                name for name in names
                if completed.get(name, {}).get("enrichment_status") == "verified_open_image"
                and completed.get(name, {}).get("image_source_name") == "GBIF occurrence media API"
            ]
        elif args.prefer_full_tree:
            pending = [
                name for name in names
                if completed.get(name, {}).get("enrichment_status") == "verified_open_image"
                and completed.get(name, {}).get("match_type") == "EXACT"
                and completed.get(name, {}).get("gbif_taxon_key")
                and "selected with preference for" not in (
                    completed.get(name, {}).get("limitation") or ""
                )
                and "Mature full-tree preference checked" not in (
                    completed.get(name, {}).get("limitation") or ""
                )
            ]
        elif args.commons_broader_fallback:
            pending = [
                name for name in names
                if completed.get(name, {}).get("enrichment_status") != "verified_open_image"
            ]
        elif args.commons_fallback:
            pending = [
                name for name in names
                if completed.get(name, {}).get("enrichment_status") != "verified_open_image"
                and completed.get(name, {}).get("match_type") == "EXACT"
                and completed.get(name, {}).get("gbif_taxon_key")
            ]
        elif args.refresh:
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
            if args.prefer_full_tree:
                for start in range(0, len(pending), 40):
                    batch_names = pending[start:start + 40]
                    for row in enrich_full_tree_batch(batch_names, completed):
                        completed[row["scientific_name"]] = row
                        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                    stream.flush()
                    print(f"enriched {min(start + len(batch_names), len(pending))}/{len(pending)}")
                pending = []
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                worker = (
                    lambda name: enrich_species_with_commons(
                        name, completed[name], args.commons_broader_fallback,
                        args.prefer_full_tree,
                    )
                    if commons_mode else enrich_species(name)
                )
                futures = {pool.submit(worker, name): name for name in pending}
                for index, future in enumerate(as_completed(futures), 1):
                    row = future.result()
                    completed[row["scientific_name"]] = row
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                    stream.flush()
                    if index % 25 == 0 or index == len(pending):
                        print(f"enriched {index}/{len(pending)}")

    rows = list(completed.values())
    if args.species:
        selected = set(args.species)
        rows = [row for row in rows if row["scientific_name"] in selected]
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
