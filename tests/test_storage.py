"""Tests for the SQLite storage backend — targets 100% storage coverage."""

import pytest
from pathlib import Path
from datetime import datetime

from sspwd.storage.sqlite import SQLiteStorage
from sspwd.storage.base import PasswordEntry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def storage(tmp_path: Path) -> SQLiteStorage:
    return SQLiteStorage(master_password="test-master", vault_dir=tmp_path)


def _entry(**kwargs) -> PasswordEntry:
    defaults = dict(id=None, title="GitHub", username="alice", password="s3cr3t")
    defaults.update(kwargs)
    return PasswordEntry(**defaults)


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


class TestInit:
    def test_creates_vault_dir(self, tmp_path: Path) -> None:
        vault = tmp_path / "nested" / "vault"
        SQLiteStorage(master_password="pw", vault_dir=vault)
        assert vault.is_dir()

    def test_creates_db_file(self, tmp_path: Path) -> None:
        SQLiteStorage(master_password="pw", vault_dir=tmp_path)
        assert (tmp_path / "vault.db").exists()

    def test_creates_salt_file(self, tmp_path: Path) -> None:
        SQLiteStorage(master_password="pw", vault_dir=tmp_path)
        assert (tmp_path / "salt.bin").exists()

    def test_salt_reused_on_second_init(self, tmp_path: Path) -> None:
        SQLiteStorage(master_password="pw", vault_dir=tmp_path)
        salt1 = (tmp_path / "salt.bin").read_bytes()
        SQLiteStorage(master_password="pw", vault_dir=tmp_path)
        salt2 = (tmp_path / "salt.bin").read_bytes()
        assert salt1 == salt2

    def test_default_vault_dir_is_home_sspwd(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        s = SQLiteStorage(master_password="pw")
        # default project is "default", so vault lives at ~/.sspwd/default/
        assert s._vault_dir == tmp_path / ".sspwd" / "default"


# ---------------------------------------------------------------------------
# Add
# ---------------------------------------------------------------------------


class TestAdd:
    def test_returns_entry_with_id(self, storage: SQLiteStorage) -> None:
        entry = storage.add(_entry())
        assert entry.id is not None and entry.id > 0

    def test_increments_ids(self, storage: SQLiteStorage) -> None:
        e1 = storage.add(_entry(title="A"))
        e2 = storage.add(_entry(title="B"))
        assert e1.id != e2.id

    def test_password_round_trip(self, storage: SQLiteStorage) -> None:
        entry = storage.add(_entry(password="super-secret"))
        assert storage.get(entry.id).password == "super-secret"

    def test_notes_round_trip(self, storage: SQLiteStorage) -> None:
        entry = storage.add(_entry(notes="personal account"))
        assert storage.get(entry.id).notes == "personal account"

    def test_optional_fields_none(self, storage: SQLiteStorage) -> None:
        entry = storage.add(_entry(url=None, notes=None))
        fetched = storage.get(entry.id)
        assert fetched.url is None
        assert fetched.notes is None

    def test_timestamps_set(self, storage: SQLiteStorage) -> None:
        entry = storage.add(_entry())
        assert isinstance(entry.created_at, datetime)
        assert isinstance(entry.updated_at, datetime)


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


class TestGet:
    def test_returns_none_for_missing(self, storage: SQLiteStorage) -> None:
        assert storage.get(99999) is None

    def test_returns_correct_entry(self, storage: SQLiteStorage) -> None:
        added = storage.add(_entry(title="Notion", username="bob"))
        fetched = storage.get(added.id)
        assert fetched.title == "Notion"
        assert fetched.username == "bob"

    def test_fields_complete(self, storage: SQLiteStorage) -> None:
        added = storage.add(_entry(url="https://example.com", notes="note"))
        fetched = storage.get(added.id)
        assert fetched.url == "https://example.com"
        assert fetched.notes == "note"


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


class TestList:
    def test_empty(self, storage: SQLiteStorage) -> None:
        assert storage.list() == []

    def test_returns_all(self, storage: SQLiteStorage) -> None:
        for t in ("A", "B", "C"):
            storage.add(_entry(title=t))
        assert len(storage.list()) == 3

    def test_ordered_by_title(self, storage: SQLiteStorage) -> None:
        for t in ("Zebra", "Apple", "Mango"):
            storage.add(_entry(title=t))
        titles = [e.title for e in storage.list()]
        assert titles == sorted(titles)

    def test_search_by_title(self, storage: SQLiteStorage) -> None:
        storage.add(_entry(title="GitHub"))
        storage.add(_entry(title="GitLab"))
        storage.add(_entry(title="AWS"))
        assert len(storage.list(search="Git")) == 2

    def test_search_by_username(self, storage: SQLiteStorage) -> None:
        storage.add(_entry(username="alice@example.com"))
        storage.add(_entry(username="bob@example.com"))
        assert len(storage.list(search="alice")) == 1

    def test_search_by_url(self, storage: SQLiteStorage) -> None:
        storage.add(_entry(title="ServiceA", username="u", url="https://github.com"))
        storage.add(_entry(title="ServiceB", username="u", url="https://gitlab.com"))
        assert len(storage.list(search="github")) == 1

    def test_search_no_results(self, storage: SQLiteStorage) -> None:
        storage.add(_entry(title="GitHub"))
        assert storage.list(search="zzznomatch") == []

    def test_search_none_returns_all(self, storage: SQLiteStorage) -> None:
        storage.add(_entry(title="A"))
        storage.add(_entry(title="B"))
        assert len(storage.list(search=None)) == 2


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


class TestUpdate:
    def test_updates_title(self, storage: SQLiteStorage) -> None:
        entry = storage.add(_entry(title="Old"))
        entry.title = "New"
        storage.update(entry)
        assert storage.get(entry.id).title == "New"

    def test_updates_password(self, storage: SQLiteStorage) -> None:
        entry = storage.add(_entry(password="old-pw"))
        entry.password = "new-pw"
        storage.update(entry)
        assert storage.get(entry.id).password == "new-pw"

    def test_updates_notes(self, storage: SQLiteStorage) -> None:
        entry = storage.add(_entry(notes="old note"))
        entry.notes = "new note"
        storage.update(entry)
        assert storage.get(entry.id).notes == "new note"

    def test_updated_at_changes(self, storage: SQLiteStorage) -> None:
        entry = storage.add(_entry())
        original_ts = entry.updated_at
        entry.title = "Changed"
        updated = storage.update(entry)
        assert updated.updated_at >= original_ts

    def test_raises_key_error_for_unknown_id(self, storage: SQLiteStorage) -> None:
        with pytest.raises(KeyError):
            storage.update(_entry(id=99999))

    def test_raises_value_error_for_none_id(self, storage: SQLiteStorage) -> None:
        """Covers sqlite.py line 170."""
        with pytest.raises(ValueError, match="without an id"):
            storage.update(_entry(id=None))


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


class TestDelete:
    def test_deletes_entry(self, storage: SQLiteStorage) -> None:
        entry = storage.add(_entry())
        storage.delete(entry.id)
        assert storage.get(entry.id) is None

    def test_raises_key_error_for_unknown_id(self, storage: SQLiteStorage) -> None:
        with pytest.raises(KeyError):
            storage.delete(99999)

    def test_other_entries_unaffected(self, storage: SQLiteStorage) -> None:
        e1 = storage.add(_entry(title="Keep"))
        e2 = storage.add(_entry(title="Delete"))
        storage.delete(e2.id)
        assert storage.get(e1.id) is not None
        assert len(storage.list()) == 1


# ---------------------------------------------------------------------------
# Encryption
# ---------------------------------------------------------------------------


class TestEncryption:
    def test_wrong_master_fails_on_get(self, tmp_path: Path) -> None:
        s1 = SQLiteStorage(master_password="correct", vault_dir=tmp_path)
        s1.add(_entry(password="secret"))
        # Wrong password raises InvalidToken at __init__ time (sentinel check)
        with pytest.raises(Exception):
            SQLiteStorage(master_password="wrong", vault_dir=tmp_path)

    def test_wrong_master_fails_on_list(self, tmp_path: Path) -> None:
        s1 = SQLiteStorage(master_password="correct", vault_dir=tmp_path)
        s1.add(_entry(password="secret"))
        # Wrong password raises InvalidToken at __init__ time (sentinel check)
        with pytest.raises(Exception):
            SQLiteStorage(master_password="wrong", vault_dir=tmp_path)

    def test_correct_master_decrypts(self, tmp_path: Path) -> None:
        s1 = SQLiteStorage(master_password="correct", vault_dir=tmp_path)
        entry = s1.add(_entry(password="plaintext"))

        s2 = SQLiteStorage(master_password="correct", vault_dir=tmp_path)
        assert s2.get(entry.id).password == "plaintext"

    def test_to_dict_contains_all_keys(self, storage: SQLiteStorage) -> None:
        entry = storage.add(_entry(url="https://x.com", notes="n"))
        d = entry.to_dict()
        for key in ("id", "title", "username", "password", "url", "notes", "created_at", "updated_at"):
            assert key in d