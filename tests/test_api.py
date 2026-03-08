"""Integration tests for the REST API."""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from sspwd.storage.sqlite import SQLiteStorage
from sspwd.ui.server import UIServer


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    storage = SQLiteStorage(master_password="test", vault_dir=tmp_path)
    server = UIServer(storage=storage, open_browser=False)
    return TestClient(server.app)


def test_health(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_and_list(client: TestClient) -> None:
    payload = {"title": "GitHub", "username": "alice", "password": "s3cr3t"}
    r = client.post("/api/v1/entries", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert data["id"] is not None
    assert data["title"] == "GitHub"

    r2 = client.get("/api/v1/entries")
    assert r2.status_code == 200
    assert len(r2.json()) == 1


def test_get_entry(client: TestClient) -> None:
    payload = {"title": "AWS", "username": "bob", "password": "pass"}
    created = client.post("/api/v1/entries", json=payload).json()

    r = client.get(f"/api/v1/entries/{created['id']}")
    assert r.status_code == 200
    assert r.json()["username"] == "bob"


def test_get_not_found(client: TestClient) -> None:
    r = client.get("/api/v1/entries/9999")
    assert r.status_code == 404


def test_update_entry(client: TestClient) -> None:
    created = client.post(
        "/api/v1/entries",
        json={"title": "Old", "username": "u", "password": "p"},
    ).json()

    r = client.put(
        f"/api/v1/entries/{created['id']}",
        json={"title": "New", "username": "u2", "password": "p2"},
    )
    assert r.status_code == 200
    assert r.json()["title"] == "New"


def test_delete_entry(client: TestClient) -> None:
    created = client.post(
        "/api/v1/entries",
        json={"title": "X", "username": "x", "password": "x"},
    ).json()

    r = client.delete(f"/api/v1/entries/{created['id']}")
    assert r.status_code == 204

    r2 = client.get(f"/api/v1/entries/{created['id']}")
    assert r2.status_code == 404


def test_search(client: TestClient) -> None:
    client.post("/api/v1/entries", json={"title": "GitHub", "username": "a", "password": "p"})
    client.post("/api/v1/entries", json={"title": "GitLab", "username": "b", "password": "p"})
    client.post("/api/v1/entries", json={"title": "AWS", "username": "c", "password": "p"})

    r = client.get("/api/v1/entries?search=Git")
    assert r.status_code == 200
    assert len(r.json()) == 2