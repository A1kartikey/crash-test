"""
Unit tests for crashtest/api.py endpoints.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from crashtest.api import app


@pytest.fixture
def client():
    return TestClient(app)


def test_api_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "offline_capable": True}


def test_api_list_cassettes(client):
    response = client.get("/api/cassettes")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    item = data[0]
    assert "id" in item
    assert "kind" in item
    assert "title" in item
    assert "turn_count" in item


def test_api_get_cassette(client):
    response = client.get("/api/cassettes/sc-01")
    assert response.status_code == 200
    data = response.json()
    assert data["cassette_id"] == "sc-01"


def test_api_get_cassette_not_found(client):
    response = client.get("/api/cassettes/nonexistent-cassette-99")
    assert response.status_code == 404


def test_api_post_replay_frozen(client):
    response = client.post(
        "/api/replay/sc-01",
        json={"mode": "frozen", "runs": 5},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["cassette_id"] == "sc-01"
    assert data["mode"] == "frozen"
    assert data["runs"] == 5
    assert data["summary"] == "CRASH 5/5"
    assert data["network_calls"] == 0


def test_api_post_replay_not_found(client):
    response = client.post(
        "/api/replay/nonexistent-99",
        json={"mode": "frozen", "runs": 1},
    )
    assert response.status_code == 404


def test_api_get_root(client):
    response = client.get("/")
    assert response.status_code == 200
