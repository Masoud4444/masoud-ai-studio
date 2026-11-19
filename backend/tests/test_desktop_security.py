import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture
def desktop_client(monkeypatch):
    monkeypatch.setenv("MASOUD_STUDIO_DESKTOP_MODE", "true")
    monkeypatch.setenv("MASOUD_STUDIO_PORT", "8000")
    return TestClient(app)


def test_desktop_allows_same_origin_loopback_request(desktop_client):
    response = desktop_client.get(
        "/health",
        headers={"host": "127.0.0.1:8000", "origin": "http://127.0.0.1:8000"},
    )
    assert response.status_code == 200


def test_desktop_rejects_dns_rebinding_host(desktop_client):
    response = desktop_client.get("/health", headers={"host": "attacker.example:8000"})
    assert response.status_code == 421


def test_desktop_rejects_cross_origin_browser_request(desktop_client):
    response = desktop_client.post(
        "/api/v1/projects",
        headers={"host": "127.0.0.1:8000", "origin": "https://attacker.example"},
        json={"name": "should-not-be-created", "description": "blocked"},
    )
    assert response.status_code == 403


def test_desktop_allows_originless_local_cli_request(desktop_client):
    response = desktop_client.get("/health", headers={"host": "127.0.0.1:8000"})
    assert response.status_code == 200
