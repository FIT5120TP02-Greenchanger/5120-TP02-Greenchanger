from fastapi.testclient import TestClient

from app.main import app

# Test the health check endpoint

def test_health_returns_ok():
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}