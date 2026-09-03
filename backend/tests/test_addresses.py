from fastapi.testclient import TestClient

from app.main import _prefix_candidates, app


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


def test_prefix_candidates_expand_street_types():
    assert _prefix_candidates("15 seascape st clayton") == [
        "15 SEASCAPE ST CLAYTON",
        "15 SEASCAPE STREET CLAYTON",
    ]
    assert _prefix_candidates("1 centre rd") == ["1 CENTRE RD", "1 CENTRE ROAD"]


def test_prefix_candidates_keep_the_typed_form_first():
    # "ST" is also SAINT, so "1 st kilda rd" must still be able to match ST KILDA ROAD.
    candidates = _prefix_candidates("1 st kilda rd")
    assert candidates[0] == "1 ST KILDA RD"
    assert "1 ST KILDA ROAD" in candidates
    assert "1 STREET KILDA ROAD" in candidates


def test_prefix_candidates_leave_plain_text_alone():
    assert _prefix_candidates("15 Seascape") == ["15 SEASCAPE"]


def test_prefix_candidates_are_capped():
    assert len(_prefix_candidates("st st st st st st")) == 8


def test_search_addresses_accepts_abbreviated_query(override_db):
    override_db(
        [
            [
                {
                    "address_id": "e157547f-65b0-42bf-9b63-5d7d4a6d1330",
                    "full_address": "1 CENTRE ROAD BRIGHTON 3186",
                    "locality_name": "BRIGHTON",
                    "postcode": "3186",
                    "parcel_area_m2": 610.2,
                    "lot_size_category": "medium",
                }
            ]
        ]
    )
    response = TestClient(app).get("/api/addresses?q=1 centre rd")
    assert response.status_code == 200
    assert response.json()[0]["full_address"] == "1 CENTRE ROAD BRIGHTON 3186"
