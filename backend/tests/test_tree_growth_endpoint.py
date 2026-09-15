from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get_tree_growth_returns_indicative_range():
    response = client.get(
        "/api/trees/growth",
        params={"species": "Platanus x acerifolia", "size": "M", "years": 10},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["canopy_m2_min"] < body["canopy_m2_median"] < body["canopy_m2_max"]


def test_get_tree_growth_accepts_full_word_size():
    response = client.get(
        "/api/trees/growth",
        params={"species": "Platanus x acerifolia", "size": "Medium", "years": 10},
    )
    assert response.status_code == 200


def test_get_tree_growth_rejects_bad_size():
    response = client.get(
        "/api/trees/growth",
        params={"species": "Platanus x acerifolia", "size": "XL", "years": 10},
    )
    assert response.status_code == 422


def test_get_tree_growth_rejects_unsupported_species():
    response = client.get(
        "/api/trees/growth", params={"species": "not a real tree", "size": "S", "years": 5}
    )
    assert response.status_code == 422


def test_get_tree_growth_rejects_negative_years():
    response = client.get(
        "/api/trees/growth",
        params={"species": "Platanus x acerifolia", "size": "S", "years": -1},
    )
    assert response.status_code == 422
