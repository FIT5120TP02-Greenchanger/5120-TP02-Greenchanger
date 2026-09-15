from fastapi.testclient import TestClient

from app.main import app


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
