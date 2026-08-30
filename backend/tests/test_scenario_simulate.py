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
