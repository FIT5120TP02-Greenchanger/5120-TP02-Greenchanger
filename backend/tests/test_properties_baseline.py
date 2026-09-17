from fastapi.testclient import TestClient

from app.main import app


def test_baseline_found(override_db):
    override_db(
        [[{"full_address": "15 SEASCAPE STREET CLAYTON 3168", "data_quality_status": "passed"}]]
    )
    response = TestClient(app).get(
        "/api/properties/baseline?address=15 Seascape Street Clayton"
    )
    assert response.status_code == 200
    assert response.json()["data_quality_status"] == "passed"


def test_baseline_not_found(override_db):
    override_db([[]])
    response = TestClient(app).get("/api/properties/baseline?address=nonexistent street")
    assert response.status_code == 404
