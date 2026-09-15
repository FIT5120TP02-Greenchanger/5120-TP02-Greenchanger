import pytest
from fastapi.testclient import TestClient

from app.main import app

TREE_EXAMPLE = {
    "quantity": 1,
    "projected_canopy_per_tree_m2": {"minimum": 6.6, "maximum": 43.7},
    "maturity_horizon_years": 10,
    "survival_probability": {"minimum": 0.5, "maximum": 1.0},
    "site_suitability_factor": {"minimum": 0.5, "maximum": 1.0},
    "overlap_factor": {"minimum": 1.0, "maximum": 1.0},
    "site_area_m2": 100.0,
}


def test_simulate_tree_returns_indicative_range():
    response = TestClient(app).post(
        "/api/scenario/simulate", json={"action_type": "tree", "inputs": TREE_EXAMPLE}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "indicative_range"
    assert body["guaranteed_outcome"] is False


def test_simulate_rejects_unsupported_action_type():
    response = TestClient(app).post(
        "/api/scenario/simulate", json={"action_type": "unicorn", "inputs": {}}
    )
    assert response.status_code == 422


TREE_WITH_SPECIES = {
    "quantity": 1,
    "species": "Platanus x acerifolia",
    "size": "M",
    "maturity_horizon_years": 10,
    "survival_probability": {"minimum": 0.5, "maximum": 1.0},
    "site_suitability_factor": {"minimum": 0.5, "maximum": 1.0},
    "overlap_factor": {"minimum": 1.0, "maximum": 1.0},
    "site_area_m2": 100.0,
}


def test_simulate_tree_with_species_and_size_uses_growth_model():
    response = TestClient(app).post(
        "/api/scenario/simulate", json={"action_type": "tree", "inputs": TREE_WITH_SPECIES}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "indicative_range"
    # the flat iteration-1 default (6.6-43.7) should be gone once a real species is given
    assert body["projected_canopy_range_m2"] != {"minimum": 6.6, "maximum": 43.7}


def test_simulate_accepts_full_word_size():
    inputs = {**TREE_WITH_SPECIES, "size": "Medium"}
    response = TestClient(app).post(
        "/api/scenario/simulate", json={"action_type": "tree", "inputs": inputs}
    )
    assert response.status_code == 200


def test_simulate_rejects_unsupported_species():
    inputs = {**TREE_WITH_SPECIES, "species": "not a real tree"}
    response = TestClient(app).post(
        "/api/scenario/simulate", json={"action_type": "tree", "inputs": inputs}
    )
    assert response.status_code == 422


@pytest.mark.parametrize("species", [None, 42, ["a"], {"a": 1}, "", "   "])
def test_simulate_rejects_non_string_or_blank_species_with_422_not_500(species):
    inputs = {**TREE_WITH_SPECIES, "species": species}
    response = TestClient(app).post(
        "/api/scenario/simulate", json={"action_type": "tree", "inputs": inputs}
    )
    assert response.status_code == 422


def test_simulate_rejects_bad_size_with_species():
    inputs = {**TREE_WITH_SPECIES, "size": "XL"}
    response = TestClient(app).post(
        "/api/scenario/simulate", json={"action_type": "tree", "inputs": inputs}
    )
    assert response.status_code == 422


def test_simulate_species_without_maturity_horizon_years_is_422_not_500():
    inputs = {k: v for k, v in TREE_WITH_SPECIES.items() if k != "maturity_horizon_years"}
    response = TestClient(app).post(
        "/api/scenario/simulate", json={"action_type": "tree", "inputs": inputs}
    )
    assert response.status_code == 422
