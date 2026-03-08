"""Basic tests for the SQLite storage backend."""

import pytest
from pathlib import Path

from sspwd.storage.sqlite import SQLiteStorage
from sspwd.storage.base import PasswordEntry


@pytest.fixture
def storage(tmp_path: Path) -> SQLiteStorage:
    return SQLiteStorage(master_password="test-master", vault_dir=tmp_path)


def _make_entry(**kwargs) -> PasswordEntry:
    defaults = dict(id=None, title="GitHub", username="alice", password="s3cr3t")
    defaults.update(kwargs)
    return PasswordEntry(**defaults)


class TestAdd:
    def test_returns_entry_with_id(self, storage: SQLiteStorage) -> None:
        entry = storage.add(_make_entry())
        assert entry.id is not None
        assert entry.id > 0

    def test_password_round_trip(self, storage: SQLiteStorage) -> None:
        entry = storage.add(_make_entry(password="my-password"))
        fetched = storage.get(entry.id)
        assert fetched is not None
        assert fetched.password == "my-password"

    def test_notes_round_trip(self, storage: SQLiteStorage) -> None:
        entry = storage.add(_make_entry(notes="personal account"))
        fetched = storage.get(entry.id)
        assert fetched is not None
        assert fetched.notes == "personal account"


class TestList:
    def test_empty(self, storage: SQLiteStorage) -> None:
        assert storage.list() == []

    def test_returns_all(self, storage: SQLiteStorage) -> None:
        storage.add(_make_entry(title="A"))
        storage.add(_make_entry(title="B"))
        assert len(storage.list()) == 2

    def test_search_filters_by_title(self, storage: SQLiteStorage) -> None:
        storage.add(_make_entry(title="GitHub"))
        storage.add(_make_entry(title="GitLab"))
        storage.add(_make_entry(title="AWS"))
        results = storage.list(search="Git")
        assert len(results) == 2


class TestUpdate:
    def test_updates_fields(self, storage: SQLiteStorage) -> None:
        entry = storage.add(_make_entry())
        entry.title = "GitHub (work)"
        entry.password = "new-password"
        storage.update(entry)

        fetched = storage.get(entry.id)
        assert fetched.title == "GitHub (work)"
        assert fetched.password == "new-password"

    def test_raises_for_unknown_id(self, storage: SQLiteStorage) -> None:
        with pytest.raises(KeyError):
            storage.update(_make_entry(id=9999))


class TestDelete:
    def test_deletes_entry(self, storage: SQLiteStorage) -> None:
        entry = storage.add(_make_entry())
        storage.delete(entry.id)
        assert storage.get(entry.id) is None

    def test_raises_for_unknown_id(self, storage: SQLiteStorage) -> None:
        with pytest.raises(KeyError):
            storage.delete(9999)


class TestEncryption:
    def test_wrong_master_fails(self, tmp_path: Path) -> None:
        """Data written with one password cannot be read with another."""
        s1 = SQLiteStorage(master_password="correct", vault_dir=tmp_path)
        entry = s1.add(_make_entry(password="secret"))

        s2 = SQLiteStorage(master_password="wrong", vault_dir=tmp_path)
        with pytest.raises(Exception):
            s2.get(entry.id)