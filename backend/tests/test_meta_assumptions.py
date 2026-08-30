from fastapi.testclient import TestClient

from app.main import app


def test_get_model_assumptions(override_db):
    override_db(
        [
            [{"action_type": "tree", "parameter_code": "temperature_evidence_bound"}],
            [{"citation_key": "ossola_2021_adelaide_vegetated_patches"}],
        ]
    )
    response = TestClient(app).get("/api/meta/assumptions")
    assert response.status_code == 200
    body = response.json()
    assert body["model_parameters"][0]["action_type"] == "tree"
    assert body["evidence"][0]["citation_key"] == "ossola_2021_adelaide_vegetated_patches"
    # File-backed scenario-input contract, not DB-backed -- covers the tree
    # action's example ranges the frontend needs to call /api/scenario/simulate.
    tree_example = body["scenario_inputs"]["actions"]["tree"]["iteration_1_example"]
    assert tree_example["projected_canopy_per_tree_m2"] == {"minimum": 6.6, "maximum": 43.7}
