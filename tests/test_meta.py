from __future__ import annotations

from fastapi.testclient import TestClient

from src.app import app

client = TestClient(app)


def test_get_meta():
    response = client.get("/meta")
    assert response.status_code == 200
    data = response.json()

    assert "name" in data
    assert "version" in data
    assert "description" in data
    assert "docs_url" in data
    assert "redoc_url" in data
    assert "openapi_url" in data


def test_get_health():
    response = client.get("/meta/health")
    assert response.status_code == 200
    data = response.json()

    assert "status" in data
    assert data["status"] == "healthy"


def test_get_version():
    response = client.get("/meta/version")
    assert response.status_code == 200
    data = response.json()

    assert "version" in data
    assert data["version"] == app.version


def test_get_ping():
    response = client.get("/meta/ping")
    assert response.status_code == 200
    data = response.json()

    assert "ping" in data
    assert data["ping"] == "pong"
    # Uncomment when Redis and MongoDB pings are implemented
    # assert "redis" in data
    # assert "mongo" in data
