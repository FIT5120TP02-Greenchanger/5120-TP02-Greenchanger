from fastapi.testclient import TestClient

from app.main import app


def test_search_addresses_returns_matches(override_db):
    override_db(
        [
            [
                {
                    "address_id": "e157547f-65b0-42bf-9b63-5d7d4a6d1330",
                    "full_address": "15 SEASCAPE STREET CLAYTON 3168",
                    "locality_name": "CLAYTON",
                    "postcode": "3168",
                    "parcel_area_m2": 1343.9,
                    "lot_size_category": "large",
                }
            ]
        ]
    )
    response = TestClient(app).get("/api/addresses?q=15 Seascape")
    assert response.status_code == 200
    assert response.json()[0]["full_address"] == "15 SEASCAPE STREET CLAYTON 3168"


def test_search_addresses_rejects_short_query(override_db):
    override_db([[]])
    response = TestClient(app).get("/api/addresses?q=15")
    assert response.status_code == 422
