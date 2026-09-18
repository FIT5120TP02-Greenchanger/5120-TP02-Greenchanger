import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.main import app


@pytest.fixture(autouse=True)
def _not_a_listed_species(monkeypatch):
    # get_tree_costs maps a listed common name through _popular_species(), which uses the
    # real pool; tests opt in to that path explicitly below.
    monkeypatch.setattr(main, "_listed_scientific_name", lambda name: None)


CATALOG_ROW = {
    "scientific_name": "Lophostemon confertus",
    "tree_type": "Lophostemon Confertus Queensland Box",
    "supply_min_cost_aud": 74.95,
    "supply_max_cost_aud": 795.0,
    "currency": "AUD",
    "cost_valid_to": "2026-12-14",
    "cost_source_names": ["Online Plants"],
    "cost_status": "species_specific_current_source_range",
    "size_price_status": "species_price_size_unmapped",
    "cost_limitation": "Confirm current stock, delivery and site suitability with the supplier.",
}


def test_listed_species_gets_its_catalog_supply_range(monkeypatch, override_db):
    monkeypatch.setattr(main, "_listed_scientific_name", lambda name: "Lophostemon confertus")
    override_db([[CATALOG_ROW]])
    response = TestClient(app).get("/api/trees/costs", params={"tree_type": "Box Brush"})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["minimum_cost"] == 74.95
    assert body[0]["maximum_cost"] == 795.0
    assert body[0]["botanical_name"] == "Lophostemon confertus"
    assert body[0]["source_name"] == "Online Plants"
    assert body[0]["display_disclaimer"].startswith("Confirm current stock")
    assert body[0]["is_generic_estimate"] is False


def test_listed_species_without_a_catalog_price_falls_back_as_before(monkeypatch, override_db):
    monkeypatch.setattr(main, "_listed_scientific_name", lambda name: "Platanus x acerifolia")
    container = {"option_code": "container_tree", "tree_type": None, "minimum_cost": 67.99}
    override_db([[], [], [container]])
    response = TestClient(app).get("/api/trees/costs", params={"tree_type": "London Plane"})
    body = response.json()
    assert [row["option_code"] for row in body] == ["container_tree"]
    assert body[0]["is_generic_estimate"] is True


def test_listed_scientific_name_maps_the_species_list_common_name(monkeypatch):
    listed = [
        {"common_name": "Box Brush", "scientific_name": "Lophostemon confertus"},
        {"common_name": "Spotted Gum", "scientific_name": "Corymbia maculata"},
    ]
    monkeypatch.undo()  # drop the autouse stub for the real helper
    monkeypatch.setattr(main, "_popular_species", lambda: listed)
    assert main._listed_scientific_name("Spotted Gum") == "Corymbia maculata"
    assert main._listed_scientific_name("Water Gum") is None


def test_get_tree_costs_carries_the_disclaimer(override_db):
    override_db(
        [
            [
                {
                    "option_code": "container_tree",
                    "tree_type": "container",
                    "minimum_cost": 67.99,
                    "maximum_cost": 185.68,
                    "estimate_status": "indicative_not_quote",
                    "display_disclaimer": (
                        "Indicative source-backed range only; confirm current price, "
                        "availability, site conditions, delivery, installation and "
                        "maintenance with the supplier."
                    ),
                }
            ]
        ]
    )
    response = TestClient(app).get("/api/trees/costs")
    assert response.status_code == 200
    body = response.json()
    assert body[0]["estimate_status"] == "indicative_not_quote"
    assert "confirm current price" in body[0]["display_disclaimer"]


def test_get_tree_costs_filters_by_tree_type(override_db):
    override_db([[{"option_code": "backyard_tree_diy", "tree_type": "Crepe Myrtle"}]])
    response = TestClient(app).get("/api/trees/costs", params={"tree_type": "Crepe Myrtle"})
    assert response.status_code == 200
    assert response.json()[0]["tree_type"] == "Crepe Myrtle"


def test_get_tree_costs_filters_by_option_code(override_db):
    override_db([[{"option_code": "container_tree", "tree_type": None}]])
    response = TestClient(app).get("/api/trees/costs", params={"option_code": "container_tree"})
    assert response.status_code == 200
    assert response.json()[0]["option_code"] == "container_tree"


def test_tree_type_with_a_price_is_not_a_generic_estimate(override_db):
    override_db([[{"option_code": "backyard_tree_diy", "tree_type": "Water Gum"}]])
    response = TestClient(app).get("/api/trees/costs", params={"tree_type": "Water Gum"})
    assert [row["is_generic_estimate"] for row in response.json()] == [False]


def test_tree_type_without_a_price_falls_back_to_the_container_tree(override_db):
    container = {"option_code": "container_tree", "tree_type": None, "minimum_cost": 67.99}
    override_db([[], [container]])
    response = TestClient(app).get("/api/trees/costs", params={"tree_type": "Dwarf Yellow Gum"})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["option_code"] == "container_tree"
    assert body[0]["minimum_cost"] == 67.99
    assert body[0]["is_generic_estimate"] is True


def test_no_fallback_when_an_option_code_is_also_given(override_db):
    container = {"option_code": "container_tree", "tree_type": None}
    override_db([[], [container]])
    response = TestClient(app).get(
        "/api/trees/costs",
        params={"tree_type": "Dwarf Yellow Gum", "option_code": "backyard_tree_installed"},
    )
    assert response.json() == []
