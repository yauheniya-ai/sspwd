"""Integration tests for the REST API — targets 100% api.py coverage."""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from sspwd.storage.sqlite import SQLiteStorage
from sspwd.storage.base import Company, CompanyAddress
import sspwd.ui.api as api_module
from sspwd.ui.server import UIServer

PROJECT = "testproject"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """Build a TestClient with one project pre-unlocked in _sessions."""
    storage = SQLiteStorage(master_password="test", vault_dir=tmp_path)
    api_module._sessions[PROJECT] = storage
    server = UIServer(open_browser=False)
    c = TestClient(server.app)
    yield c
    api_module._sessions.pop(PROJECT, None)


@pytest.fixture
def client_with_entry(client: TestClient) -> tuple[TestClient, dict]:
    """Client that already has one entry created."""
    payload = {"title": "GitHub", "username": "alice", "password": "s3cr3t",
               "url": "https://github.com"}
    entry = client.post(f"/api/v1/entries?project={PROJECT}", json=payload).json()
    return client, entry


@pytest.fixture
def client_with_company(client: TestClient) -> tuple[TestClient, dict]:
    """Client that already has one company created."""
    payload = {
        "name": "Acme Corp",
        "icon": {"type": "letter", "value": "A"},
        "address": {
            "street": "1 Main St", "city": "Springfield",
            "state": "IL", "postcode": "62701",
            "country": "United States", "countryCode": "us",
        },
        "revenue": 1_000_000.0,
    }
    company = client.post(f"/api/v1/companies?project={PROJECT}", json=payload).json()
    return client, company


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# set_storage helper (covers api.py line 30)
# ---------------------------------------------------------------------------


def test_set_storage(tmp_path: Path) -> None:
    storage = SQLiteStorage(master_password="pw", vault_dir=tmp_path)
    api_module.set_storage(storage)
    assert api_module._sessions["default"] is storage
    api_module._sessions.pop("default", None)


# ---------------------------------------------------------------------------
# GET /entries
# ---------------------------------------------------------------------------


def test_list_empty(client: TestClient) -> None:
    r = client.get(f"/api/v1/entries?project={PROJECT}")
    assert r.status_code == 200
    assert r.json() == []


def test_list_returns_all(client: TestClient) -> None:
    for title in ("Alpha", "Beta", "Gamma"):
        client.post(f"/api/v1/entries?project={PROJECT}",
                    json={"title": title, "username": "u", "password": "p"})
    r = client.get(f"/api/v1/entries?project={PROJECT}")
    assert len(r.json()) == 3


def test_list_search_by_title(client: TestClient) -> None:
    for title in ("GitHub", "GitLab", "AWS"):
        client.post(f"/api/v1/entries?project={PROJECT}",
                    json={"title": title, "username": "u", "password": "p"})
    r = client.get(f"/api/v1/entries?project={PROJECT}&search=Git")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_list_search_by_username(client: TestClient) -> None:
    client.post(f"/api/v1/entries?project={PROJECT}",
                json={"title": "A", "username": "alice@example.com", "password": "p"})
    client.post(f"/api/v1/entries?project={PROJECT}",
                json={"title": "B", "username": "bob@example.com", "password": "p"})
    r = client.get(f"/api/v1/entries?project={PROJECT}&search=alice")
    assert len(r.json()) == 1
    assert r.json()[0]["username"] == "alice@example.com"


def test_list_search_no_results(client: TestClient) -> None:
    client.post(f"/api/v1/entries?project={PROJECT}",
                json={"title": "GitHub", "username": "u", "password": "p"})
    r = client.get(f"/api/v1/entries?project={PROJECT}&search=zzznomatch")
    assert r.json() == []


# ---------------------------------------------------------------------------
# POST /entries
# ---------------------------------------------------------------------------


def test_create_title_only(client: TestClient) -> None:
    """Only title is required — all other fields are optional."""
    r = client.post(f"/api/v1/entries?project={PROJECT}", json={"title": "Bare"})
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "Bare"
    assert data["username"] is None
    assert data["password"] is None


def test_create_missing_title_returns_422(client: TestClient) -> None:
    """Omitting title (the only required field) must return 422."""
    r = client.post(f"/api/v1/entries?project={PROJECT}", json={})
    assert r.status_code == 422


def test_create_full(client: TestClient) -> None:
    payload = {
        "title": "AWS", "username": "admin", "email": "admin@example.com",
        "password": "hunter2", "url": "https://aws.amazon.com",
        "notes": "root account", "category": "Cloud",
        "tags": ["work", "critical"],
        "login_methods": ["Email / Password"],
        "user_created_at": "2020-01-01T00:00:00",
    }
    r = client.post(f"/api/v1/entries?project={PROJECT}", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert data["url"] == "https://aws.amazon.com"
    assert data["notes"] == "root account"
    assert data["email"] == "admin@example.com"
    assert data["category"] == "Cloud"
    assert data["tags"] == ["work", "critical"]
    assert data["login_methods"] == ["Email / Password"]


def test_create_timestamps_present(client: TestClient) -> None:
    r = client.post(f"/api/v1/entries?project={PROJECT}",
                    json={"title": "T", "username": "u", "password": "p"})
    data = r.json()
    assert "created_at" in data
    assert "updated_at" in data


def test_create_with_invalid_user_created_at(client: TestClient) -> None:
    """Malformed user_created_at is silently ignored (parsed as None)."""
    r = client.post(f"/api/v1/entries?project={PROJECT}",
                    json={"title": "T", "user_created_at": "not-a-date"})
    assert r.status_code == 201
    assert r.json()["user_created_at"] is None


# ---------------------------------------------------------------------------
# GET /entries/{id}
# ---------------------------------------------------------------------------


def test_get_entry(client_with_entry) -> None:
    client, entry = client_with_entry
    r = client.get(f"/api/v1/entries/{entry['id']}?project={PROJECT}")
    assert r.status_code == 200
    assert r.json()["username"] == "alice"


def test_get_entry_not_found(client: TestClient) -> None:
    r = client.get(f"/api/v1/entries/99999?project={PROJECT}")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# PUT /entries/{id}
# ---------------------------------------------------------------------------


def test_update_entry(client_with_entry) -> None:
    client, entry = client_with_entry
    r = client.put(f"/api/v1/entries/{entry['id']}?project={PROJECT}",
                   json={"title": "GitHub Pro", "username": "alice2", "password": "newpass"})
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "GitHub Pro"
    assert data["username"] == "alice2"


def test_update_entry_not_found(client: TestClient) -> None:
    r = client.put(f"/api/v1/entries/99999?project={PROJECT}",
                   json={"title": "X", "username": "x", "password": "x"})
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


def test_update_persists(client_with_entry) -> None:
    client, entry = client_with_entry
    client.put(f"/api/v1/entries/{entry['id']}?project={PROJECT}",
               json={"title": "Updated", "username": "u", "password": "p"})
    fetched = client.get(f"/api/v1/entries/{entry['id']}?project={PROJECT}").json()
    assert fetched["title"] == "Updated"


# ---------------------------------------------------------------------------
# DELETE /entries/{id}
# ---------------------------------------------------------------------------


def test_delete_entry(client_with_entry) -> None:
    client, entry = client_with_entry
    r = client.delete(f"/api/v1/entries/{entry['id']}?project={PROJECT}")
    assert r.status_code == 204
    r2 = client.get(f"/api/v1/entries/{entry['id']}?project={PROJECT}")
    assert r2.status_code == 404


def test_delete_entry_not_found(client: TestClient) -> None:
    r = client.delete(f"/api/v1/entries/99999?project={PROJECT}")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


def test_delete_reduces_list(client: TestClient) -> None:
    ids = [
        client.post(f"/api/v1/entries?project={PROJECT}",
                    json={"title": f"E{i}", "username": "u", "password": "p"}).json()["id"]
        for i in range(3)
    ]
    client.delete(f"/api/v1/entries/{ids[0]}?project={PROJECT}")
    assert len(client.get(f"/api/v1/entries?project={PROJECT}").json()) == 2


# ---------------------------------------------------------------------------
# Companies CRUD
# ---------------------------------------------------------------------------


def test_list_companies_empty(client: TestClient) -> None:
    r = client.get(f"/api/v1/companies?project={PROJECT}")
    assert r.status_code == 200
    assert r.json() == []


def test_create_company_minimal(client: TestClient) -> None:
    r = client.post(f"/api/v1/companies?project={PROJECT}",
                    json={"name": "Bare Corp"})
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Bare Corp"
    assert data["id"] is not None


def test_create_company_full(client_with_company) -> None:
    client, company = client_with_company
    assert company["name"] == "Acme Corp"
    assert company["address"]["city"] == "Springfield"
    assert company["revenue"] == 1_000_000.0
    assert company["icon"]["type"] == "letter"


def test_get_company(client_with_company) -> None:
    client, company = client_with_company
    r = client.get(f"/api/v1/companies/{company['id']}?project={PROJECT}")
    assert r.status_code == 200
    assert r.json()["name"] == "Acme Corp"


def test_get_company_not_found(client: TestClient) -> None:
    r = client.get(f"/api/v1/companies/99999?project={PROJECT}")
    assert r.status_code == 404


def test_update_company(client_with_company) -> None:
    client, company = client_with_company
    r = client.put(f"/api/v1/companies/{company['id']}?project={PROJECT}",
                   json={"name": "Acme Global", "revenue": 5_000_000.0})
    assert r.status_code == 200
    assert r.json()["name"] == "Acme Global"


def test_update_company_not_found(client: TestClient) -> None:
    r = client.put(f"/api/v1/companies/99999?project={PROJECT}",
                   json={"name": "Ghost"})
    assert r.status_code == 404


def test_delete_company(client_with_company) -> None:
    client, company = client_with_company
    r = client.delete(f"/api/v1/companies/{company['id']}?project={PROJECT}")
    assert r.status_code == 204
    assert client.get(f"/api/v1/companies/{company['id']}?project={PROJECT}").status_code == 404


def test_delete_company_not_found(client: TestClient) -> None:
    r = client.delete(f"/api/v1/companies/99999?project={PROJECT}")
    assert r.status_code == 404


def test_create_company_no_address_country(client: TestClient) -> None:
    """address dict without country → address stored as None (covers _company_in_to_obj branch)."""
    r = client.post(f"/api/v1/companies?project={PROJECT}",
                    json={"name": "NoCountry", "address": {"street": "123 Main"}})
    assert r.status_code == 201
    assert r.json()["address"] is None


# ---------------------------------------------------------------------------
# Session / lock guard
# ---------------------------------------------------------------------------


def test_require_raises_when_project_locked() -> None:
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        api_module._require("__nonexistent_project__")
    assert exc_info.value.status_code == 401


def test_unlock_wrong_password(tmp_path: Path) -> None:
    vault_path = tmp_path / "myproject"
    SQLiteStorage(master_password="correct", vault_dir=vault_path)
    server = UIServer(open_browser=False)
    client = TestClient(server.app)
    from unittest.mock import patch
    with patch("sspwd.ui.api.project_dir", return_value=vault_path), \
         patch("sspwd.storage.sqlite.project_dir", return_value=vault_path):
        r = client.post("/api/v1/projects/myproject/unlock",
                        json={"password": "wrongpassword"})
    assert r.status_code == 401


def test_unlock_project_not_found(tmp_path: Path) -> None:
    server = UIServer(open_browser=False)
    client = TestClient(server.app)
    r = client.post("/api/v1/projects/__ghost__/unlock", json={"password": "pw"})
    assert r.status_code == 404


def test_create_project_and_list(tmp_path: Path) -> None:
    server = UIServer(open_browser=False)
    client = TestClient(server.app)
    from unittest.mock import patch
    fake_dir = tmp_path / "newproj"
    with patch("sspwd.ui.api.project_dir", return_value=fake_dir), \
         patch("sspwd.ui.api.SQLiteStorage") as MockStorage:
        instance = MockStorage.return_value
        instance.list.return_value = []
        r = client.post("/api/v1/projects", json={"name": "newproj", "password": "pw"})
    assert r.status_code == 201
    assert r.json()["project"] == "newproj"


def test_create_project_invalid_name() -> None:
    server = UIServer(open_browser=False)
    client = TestClient(server.app)
    r = client.post("/api/v1/projects", json={"name": "bad/name", "password": "pw"})
    assert r.status_code == 400


def test_create_project_already_exists(tmp_path: Path) -> None:
    vault_path = tmp_path / "exists"
    SQLiteStorage(master_password="pw", vault_dir=vault_path)
    server = UIServer(open_browser=False)
    client = TestClient(server.app)
    from unittest.mock import patch
    with patch("sspwd.ui.api.project_dir", return_value=vault_path):
        r = client.post("/api/v1/projects", json={"name": "exists", "password": "pw"})
    assert r.status_code == 409


def test_list_unlocked(client: TestClient) -> None:
    r = client.get("/api/v1/projects/unlocked")
    assert r.status_code == 200
    assert PROJECT in r.json()


def test_lock_project(client: TestClient) -> None:
    api_module._sessions["to_lock"] = api_module._sessions[PROJECT]
    r = client.delete("/api/v1/projects/to_lock/lock")
    assert r.status_code == 200
    assert "to_lock" not in api_module._sessions


def test_unlock_success(tmp_path: Path) -> None:
    vault_path = tmp_path / "goodproject"
    SQLiteStorage(master_password="correct", vault_dir=vault_path)
    server = UIServer(open_browser=False)
    client = TestClient(server.app)
    from unittest.mock import patch
    with patch("sspwd.ui.api.project_dir", return_value=vault_path), \
         patch("sspwd.storage.sqlite.project_dir", return_value=vault_path):
        r = client.post("/api/v1/projects/goodproject/unlock",
                        json={"password": "correct"})
    assert r.status_code == 200
    assert r.json()["status"] == "unlocked"
    api_module._sessions.pop("goodproject", None)


def test_list_projects_no_sspwd_dir(tmp_path: Path, monkeypatch) -> None:
    import pathlib
    empty_home = tmp_path / "empty_home"
    empty_home.mkdir()
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: empty_home))
    server = UIServer(open_browser=False)
    client = TestClient(server.app)
    r = client.get("/api/v1/projects")
    assert r.status_code == 200
    assert r.json() == []


# ---------------------------------------------------------------------------
# Icons
# ---------------------------------------------------------------------------


def test_icon_upload_and_serve(client: TestClient) -> None:
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
        b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
        b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    r = client.post(
        f"/api/v1/icons?project={PROJECT}",
        files={"file": ("test.png", png_bytes, "image/png")},
    )
    assert r.status_code == 201
    icon_url = r.json()["url"]
    assert icon_url.startswith("/api/v1/icons/")
    r2 = client.get(icon_url)
    assert r2.status_code == 200


def test_icon_upload_jpeg_extension(client: TestClient) -> None:
    """JPEG uploads get a .jpg extension (covers the .jpe/.jfif normalisation branch)."""
    # Minimal JPEG header
    jpeg_bytes = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"\x00" * 16
    r = client.post(
        f"/api/v1/icons?project={PROJECT}",
        files={"file": ("photo.jpg", jpeg_bytes, "image/jpeg")},
    )
    assert r.status_code == 201
    assert r.json()["filename"].endswith(".jpg")


def test_icon_upload_unsupported_type(client: TestClient) -> None:
    r = client.post(
        f"/api/v1/icons?project={PROJECT}",
        files={"file": ("bad.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 415


def test_icon_upload_too_large(client: TestClient) -> None:
    big = b"x" * (2 * 1024 * 1024 + 1)
    r = client.post(
        f"/api/v1/icons?project={PROJECT}",
        files={"file": ("big.png", big, "image/png")},
    )
    assert r.status_code == 413


def test_icon_serve_not_found(client: TestClient) -> None:
    r = client.get(f"/api/v1/icons/nonexistent.png?project={PROJECT}")
    assert r.status_code == 404


def test_icon_list(client: TestClient) -> None:
    r = client.get(f"/api/v1/icons?project={PROJECT}")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_icon_list_after_upload(client: TestClient) -> None:
    """GET /icons returns the uploaded file after a successful upload."""
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
    client.post(f"/api/v1/icons?project={PROJECT}",
                files={"file": ("x.png", png, "image/png")})
    r = client.get(f"/api/v1/icons?project={PROJECT}")
    assert len(r.json()) >= 1