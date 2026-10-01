"""_popular_species() talks to pool.connection() directly (see main.py for why),
so it doesn't go through the get_db dependency override conftest.py sets up for
everything else -- these tests monkeypatch pool.connection() instead.
"""

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.main import POPULAR_SPECIES_QUERY, _popular_species, app, pool
from tests.conftest import FakeConnection


@pytest.fixture(autouse=True)
def _clear_cache():
    # @lru_cache(maxsize=1) means the first test to call this would otherwise
    # poison every test after it with its own mocked result.
    _popular_species.cache_clear()
    yield
    _popular_species.cache_clear()


def _fake_pool_connection(resultsets):
    @contextmanager
    def _connection():
        yield FakeConnection(resultsets)

    return _connection


def test_returns_species_with_limitations_and_growth_flag(monkeypatch):
    monkeypatch.setattr(
        pool,
        "connection",
        _fake_pool_connection(
            [
                [
                    {
                        "species_key": "platanus x acerifolia",
                        "scientific_name": "Platanus x acerifolia",
                        "common_name": "London Plane",
                        "tree_count": 14684,
                        "image_url": "https://example.org/plane.jpg",
                        "image_page_url": "https://example.org/plane",
                        "image_alt_text": "A London Plane tree.",
                        "image_creator": "Jane Doe",
                        "image_licence": "CC BY 4.0",
                        "image_licence_url": "https://creativecommons.org/licenses/by/4.0/",
                        "image_attribution": "Photo by Jane Doe, CC BY 4.0.",
                        "image_status": "curated_reference_image",
                        "image_limitation": "Illustrative only; appearance varies.",
                    }
                ]
            ]
        ),
    )
    response = TestClient(app).get(
        "/api/trees/species", params={"address": "15 Seascape Street Clayton"}
    )
    assert response.status_code == 200
    body = response.json()
    assert "limitations" in body and body["limitations"]
    # the "please display image_attribution" note is developer-facing (see the
    # _popular_species docstring), not something end users should see here
    assert "attribution" not in body["limitations"].lower()
    species = body["species"][0]
    assert species["scientific_name"] == "Platanus x acerifolia"
    # a real species in the trained growth model -- see test_tree_growth.py
    assert species["has_growth_model"] is True
    assert species["image_url"] == "https://example.org/plane.jpg"
    assert species["image_attribution"] == "Photo by Jane Doe, CC BY 4.0."
    assert species["image_status"] == "curated_reference_image"


def test_species_without_a_matching_image_gets_null_image_fields(monkeypatch):
    monkeypatch.setattr(
        pool,
        "connection",
        _fake_pool_connection(
            [
                [
                    {
                        "species_key": "chinese elm",
                        "scientific_name": "Chinese Elm",
                        "common_name": None,
                        "tree_count": 9976,
                        "image_url": None,
                        "image_page_url": None,
                        "image_alt_text": None,
                        "image_creator": None,
                        "image_licence": None,
                        "image_licence_url": None,
                        "image_attribution": None,
                        "image_status": None,
                        "image_limitation": None,
                    }
                ]
            ]
        ),
    )
    response = TestClient(app).get(
        "/api/trees/species", params={"address": "15 Seascape Street Clayton"}
    )
    assert response.json()["species"][0]["image_url"] is None


def test_problem_tree_names_and_verified_images_are_normalized(monkeypatch):
    monkeypatch.setattr(
        pool,
        "connection",
        _fake_pool_connection(
            [
                [
                    {
                        "species_key": "lophostemon confertus",
                        "scientific_name": "Lophostemon confertus",
                        "common_name": "Box Brush",
                        "tree_count": 22579,
                        "image_status": "verified_wikimedia_commons_image",
                        "image_url": "https://example.org/brush-box.jpg",
                    },
                    {
                        "species_key": "platanus x acerifolia",
                        "scientific_name": "Platanus x acerifolia",
                        "common_name": "London Plane",
                        "tree_count": 14684,
                        "image_status": "verified_wikimedia_commons_image",
                        "image_url": "https://example.org/london-plane.jpg",
                    },
                    {
                        "species_key": "eucalyptus leucoxylon",
                        "scientific_name": "Eucalyptus leucoxylon",
                        "common_name": "Dwarf Yellow Gum",
                        "tree_count": 14560,
                        "image_status": "verified_wikimedia_commons_image",
                        "image_url": "https://example.org/yellow-gum.jpg",
                    },
                ]
            ]
        ),
    )

    response = TestClient(app).get(
        "/api/trees/species", params={"address": "15 Seascape Street Clayton"}
    )

    assert response.status_code == 200
    species = response.json()["species"]
    assert [row["common_name"] for row in species] == [
        "Brush Box",
        "London Plane",
        "Yellow Gum",
    ]
    assert all(row["image_url"] for row in species)
    assert all(row["image_status"] == "verified_wikimedia_commons_image" for row in species)


def test_popular_species_query_uses_ranked_names_and_licensed_image_view():
    normalized_query = " ".join(POPULAR_SPECIES_QUERY.lower().split())

    assert "row_number() over" in normalized_query
    assert "order by count(*) desc, common_name" in normalized_query
    assert "application_ready_tree_species_image" in normalized_query
    assert "lower(img.scientific_name) = species_counts.species_key" in normalized_query
    assert "inaturalist-open-data" not in normalized_query


def test_flags_species_without_a_growth_model(monkeypatch):
    monkeypatch.setattr(
        pool,
        "connection",
        _fake_pool_connection(
            [
                [
                    {
                        "species_key": "not a real species",
                        "scientific_name": "Not A Real Species",
                        "common_name": None,
                        "tree_count": 1,
                    }
                ]
            ]
        ),
    )
    response = TestClient(app).get(
        "/api/trees/species", params={"address": "15 Seascape Street Clayton"}
    )
    assert response.json()["species"][0]["has_growth_model"] is False


def test_result_is_cached_after_the_first_request(monkeypatch):
    calls = 0
    row = [{"species_key": "x", "scientific_name": "X", "common_name": None, "tree_count": 1}]

    def _connection():
        nonlocal calls
        calls += 1
        return _fake_pool_connection([row])()

    monkeypatch.setattr(pool, "connection", _connection)

    client = TestClient(app)
    client.get("/api/trees/species", params={"address": "15 Seascape Street Clayton"})
    client.get("/api/trees/species", params={"address": "1 Swanston Street Melbourne"})

    assert calls == 1


def test_rejects_short_address():
    response = TestClient(app).get("/api/trees/species", params={"address": "15"})
    assert response.status_code == 422
