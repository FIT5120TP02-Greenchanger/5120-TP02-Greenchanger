"""CORS is what lets the Vite dev server read this API from its own port.

Production is same-origin behind nginx, so none of this applies there — these
tests exist so a future change to the middleware does not silently break local
development, where the failure shows up only as a browser console message.

/api/health is used throughout because it needs no database.
"""

from fastapi.testclient import TestClient

from app.main import app

DEV_ORIGIN = "http://localhost:5173"

client = TestClient(app)


def test_allowed_origin_may_read_the_response():
    response = client.get("/api/health", headers={"Origin": DEV_ORIGIN})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == DEV_ORIGIN


def test_unlisted_origin_gets_no_permission_header():
    """Without the header the browser withholds the body from page JavaScript."""
    response = client.get("/api/health", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in response.headers


def test_preflight_allows_the_methods_the_api_actually_serves():
    """Browsers send OPTIONS first for anything beyond a simple request."""
    response = client.options(
        "/api/scenario/simulate",
        headers={
            "Origin": DEV_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == DEV_ORIGIN
    assert "POST" in response.headers["access-control-allow-methods"]


def test_requests_without_an_origin_are_untouched():
    """curl, the deploy healthcheck and server-to-server calls send no Origin."""
    response = client.get("/api/health")

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
