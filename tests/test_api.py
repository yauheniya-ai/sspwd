"""Integration tests for the REST API — targets 100% api.py coverage."""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from sspwd.storage.sqlite import SQLiteStorage
from sspwd.ui.server import UIServer
import sspwd.ui.api as api_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    storage = SQLiteStorage(master_password="test", vault_dir=tmp_path)
    server = UIServer(storage=storage, open_browser=False)
    return TestClient(server.app)


@pytest.fixture
def client_with_entry(client: TestClient) -> tuple[TestClient, dict]:
    """Client that already has one entry created."""
    payload = {"title": "GitHub", "username": "alice", "password": "s3cr3t", "url": "https://github.com"}
    entry = client.post("/api/v1/entries", json=payload).json()
    return client, entry


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# GET /entries
# ---------------------------------------------------------------------------


def test_list_empty(client: TestClient) -> None:
    r = client.get("/api/v1/entries")
    assert r.status_code == 200
    assert r.json() == []


def test_list_returns_all(client: TestClient) -> None:
    for title in ("Alpha", "Beta", "Gamma"):
        client.post("/api/v1/entries", json={"title": title, "username": "u", "password": "p"})
    r = client.get("/api/v1/entries")
    assert len(r.json()) == 3


def test_list_search_by_title(client: TestClient) -> None:
    client.post("/api/v1/entries", json={"title": "GitHub", "username": "u", "password": "p"})
    client.post("/api/v1/entries", json={"title": "GitLab", "username": "u", "password": "p"})
    client.post("/api/v1/entries", json={"title": "AWS",    "username": "u", "password": "p"})

    r = client.get("/api/v1/entries?search=Git")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_list_search_by_username(client: TestClient) -> None:
    client.post("/api/v1/entries", json={"title": "A", "username": "alice@example.com", "password": "p"})
    client.post("/api/v1/entries", json={"title": "B", "username": "bob@example.com",   "password": "p"})

    r = client.get("/api/v1/entries?search=alice")
    assert len(r.json()) == 1
    assert r.json()[0]["username"] == "alice@example.com"


def test_list_search_no_results(client: TestClient) -> None:
    client.post("/api/v1/entries", json={"title": "GitHub", "username": "u", "password": "p"})
    r = client.get("/api/v1/entries?search=zzznomatch")
    assert r.json() == []


# ---------------------------------------------------------------------------
# POST /entries
# ---------------------------------------------------------------------------


def test_create_minimal(client: TestClient) -> None:
    r = client.post("/api/v1/entries", json={"title": "T", "username": "u", "password": "p"})
    assert r.status_code == 201
    data = r.json()
    assert data["id"] is not None
    assert data["title"] == "T"
    assert data["url"] is None
    assert data["notes"] is None


def test_create_full(client: TestClient) -> None:
    payload = {
        "title": "AWS",
        "username": "admin",
        "password": "hunter2",
        "url": "https://aws.amazon.com",
        "notes": "root account",
    }
    r = client.post("/api/v1/entries", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert data["url"] == "https://aws.amazon.com"
    assert data["notes"] == "root account"


def test_create_missing_required_fields(client: TestClient) -> None:
    r = client.post("/api/v1/entries", json={"title": "only title"})
    assert r.status_code == 422


def test_create_timestamps_present(client: TestClient) -> None:
    r = client.post("/api/v1/entries", json={"title": "T", "username": "u", "password": "p"})
    data = r.json()
    assert "created_at" in data
    assert "updated_at" in data


# ---------------------------------------------------------------------------
# GET /entries/{id}
# ---------------------------------------------------------------------------


def test_get_entry(client_with_entry) -> None:
    client, entry = client_with_entry
    r = client.get(f"/api/v1/entries/{entry['id']}")
    assert r.status_code == 200
    assert r.json()["username"] == "alice"


def test_get_entry_not_found(client: TestClient) -> None:
    r = client.get("/api/v1/entries/99999")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# PUT /entries/{id}
# ---------------------------------------------------------------------------


def test_update_entry(client_with_entry) -> None:
    client, entry = client_with_entry
    r = client.put(
        f"/api/v1/entries/{entry['id']}",
        json={"title": "GitHub Pro", "username": "alice2", "password": "newpass"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "GitHub Pro"
    assert data["username"] == "alice2"


def test_update_entry_not_found(client: TestClient) -> None:
    """Covers api.py lines 103-104 (KeyError → 404)."""
    r = client.put(
        "/api/v1/entries/99999",
        json={"title": "X", "username": "x", "password": "x"},
    )
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


def test_update_persists(client_with_entry) -> None:
    """Verify the update is actually stored, not just returned."""
    client, entry = client_with_entry
    client.put(
        f"/api/v1/entries/{entry['id']}",
        json={"title": "Updated", "username": "u", "password": "p"},
    )
    fetched = client.get(f"/api/v1/entries/{entry['id']}").json()
    assert fetched["title"] == "Updated"


# ---------------------------------------------------------------------------
# DELETE /entries/{id}
# ---------------------------------------------------------------------------


def test_delete_entry(client_with_entry) -> None:
    client, entry = client_with_entry
    r = client.delete(f"/api/v1/entries/{entry['id']}")
    assert r.status_code == 204

    r2 = client.get(f"/api/v1/entries/{entry['id']}")
    assert r2.status_code == 404


def test_delete_entry_not_found(client: TestClient) -> None:
    """Covers api.py lines 113-114 (KeyError → 404)."""
    r = client.delete("/api/v1/entries/99999")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


def test_delete_reduces_list(client: TestClient) -> None:
    ids = [
        client.post("/api/v1/entries", json={"title": f"E{i}", "username": "u", "password": "p"}).json()["id"]
        for i in range(3)
    ]
    client.delete(f"/api/v1/entries/{ids[0]}")
    assert len(client.get("/api/v1/entries").json()) == 2


# ---------------------------------------------------------------------------
# Storage-not-initialised guard (api.py line 28)
# ---------------------------------------------------------------------------


def test_get_storage_raises_when_uninitialised() -> None:
    """Directly call _get_storage with _storage set to None."""
    original = api_module._storage
    try:
        api_module._storage = None
        with pytest.raises(RuntimeError, match="Storage has not been initialised"):
            api_module._get_storage()
    finally:
        api_module._storage = original