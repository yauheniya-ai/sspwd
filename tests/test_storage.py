"""Tests for the SQLite storage backend — targets 100% storage coverage."""

import pytest
from pathlib import Path
from datetime import datetime

from sspwd.storage.sqlite import SQLiteStorage
from sspwd.storage.base import BaseStorage, Company, CompanyAddress, PasswordEntry


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


def _company(**kwargs) -> Company:
    defaults = dict(id=None, name="Acme Corp")
    defaults.update(kwargs)
    return Company(**defaults)


# ---------------------------------------------------------------------------
# CompanyAddress dataclass
# ---------------------------------------------------------------------------


class TestCompanyAddress:
    def test_to_dict_full(self) -> None:
        a = CompanyAddress(
            country="United States", country_code="us",
            street="1 Main St", city="Springfield", state="IL", postcode="62701",
        )
        d = a.to_dict()
        assert d["country"] == "United States"
        assert d["countryCode"] == "us"
        assert d["street"] == "1 Main St"
        assert d["city"] == "Springfield"
        assert d["state"] == "IL"
        assert d["postcode"] == "62701"

    def test_to_dict_minimal(self) -> None:
        a = CompanyAddress(country="Germany", country_code="de")
        d = a.to_dict()
        assert d["country"] == "Germany"
        assert d["street"] is None

    def test_from_dict_round_trip(self) -> None:
        original = CompanyAddress(
            country="France", country_code="fr",
            street="1 Rue de Rivoli", city="Paris", postcode="75001",
        )
        restored = CompanyAddress.from_dict(original.to_dict())
        assert restored.country == original.country
        assert restored.country_code == original.country_code
        assert restored.street == original.street
        assert restored.city == original.city

    def test_from_dict_missing_keys(self) -> None:
        a = CompanyAddress.from_dict({"country": "Japan", "countryCode": "jp"})
        assert a.street is None
        assert a.state is None


# ---------------------------------------------------------------------------
# Company dataclass
# ---------------------------------------------------------------------------


class TestCompanyDataclass:
    def test_to_dict_with_address(self) -> None:
        addr = CompanyAddress(country="US", country_code="us", city="NYC")
        c = Company(id=1, name="Acme", icon={"type": "letter", "value": "A"},
                    address=addr, revenue=1_000_000.0)
        d = c.to_dict()
        assert d["name"] == "Acme"
        assert d["address"]["city"] == "NYC"
        assert d["revenue"] == 1_000_000.0
        assert d["icon"]["type"] == "letter"

    def test_to_dict_no_address(self) -> None:
        c = Company(id=2, name="NoAddr")
        d = c.to_dict()
        assert d["address"] is None
        assert d["revenue"] is None

    def test_from_dict_round_trip(self) -> None:
        addr = CompanyAddress(country="Canada", country_code="ca", city="Toronto")
        c = Company(id=5, name="CanadaCo", icon={"type": "url", "value": "https://x.com/logo.svg"},
                    address=addr, revenue=5_000_000.0)
        restored = Company.from_dict(c.to_dict())
        assert restored.name == "CanadaCo"
        assert restored.revenue == 5_000_000.0
        assert restored.address is not None
        assert restored.address.country == "Canada"

    def test_from_dict_no_address(self) -> None:
        c = Company.from_dict({"id": 1, "name": "Plain"})
        assert c.address is None
        assert c.icon is None


# ---------------------------------------------------------------------------
# BaseStorage abstract NotImplementedError methods
# ---------------------------------------------------------------------------


class TestBaseStorageDefaults:
    """Verify that the default company methods raise NotImplementedError."""

    def test_add_company_not_implemented(self, tmp_path: Path) -> None:
        s = SQLiteStorage.__new__(SQLiteStorage)
        with pytest.raises(NotImplementedError):
            BaseStorage.add_company(s, _company())

    def test_get_company_not_implemented(self, tmp_path: Path) -> None:
        s = SQLiteStorage.__new__(SQLiteStorage)
        with pytest.raises(NotImplementedError):
            BaseStorage.get_company(s, 1)

    def test_list_companies_not_implemented(self, tmp_path: Path) -> None:
        s = SQLiteStorage.__new__(SQLiteStorage)
        with pytest.raises(NotImplementedError):
            BaseStorage.list_companies(s)

    def test_update_company_not_implemented(self, tmp_path: Path) -> None:
        s = SQLiteStorage.__new__(SQLiteStorage)
        with pytest.raises(NotImplementedError):
            BaseStorage.update_company(s, _company(id=1))

    def test_delete_company_not_implemented(self, tmp_path: Path) -> None:
        s = SQLiteStorage.__new__(SQLiteStorage)
        with pytest.raises(NotImplementedError):
            BaseStorage.delete_company(s, 1)


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
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        s = SQLiteStorage(master_password="pw")
        assert s._vault_dir == tmp_path / ".sspwd" / "default"

    def test_vault_dir_property(self, tmp_path: Path) -> None:
        s = SQLiteStorage(master_password="pw", vault_dir=tmp_path)
        assert s.vault_dir == tmp_path

    def test_migration_adds_missing_entry_columns(self, tmp_path: Path) -> None:
        """Migration runs ALTER TABLE for any column absent in an older vault."""
        import sqlite3
        # Create a minimal old-style DB with only legacy columns
        db = tmp_path / "vault.db"
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE entries (id INTEGER PRIMARY KEY, title TEXT NOT NULL,"
            " username TEXT, password TEXT, url TEXT, notes TEXT,"
            " created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE companies (id INTEGER PRIMARY KEY, name TEXT NOT NULL)"
        )
        conn.commit()
        conn.close()
        # Initialising against this old DB should apply the migration
        (tmp_path / "salt.bin").write_bytes(b"\x00" * 32)
        s = SQLiteStorage(master_password="pw", vault_dir=tmp_path)
        cols = {row[1] for row in s._connect().execute("PRAGMA table_info(entries)")}
        assert "email" in cols
        assert "category" in cols
        assert "tags" in cols


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

    def test_email_round_trip(self, storage: SQLiteStorage) -> None:
        entry = storage.add(_entry(email="alice@example.com"))
        assert storage.get(entry.id).email == "alice@example.com"

    def test_notes_round_trip(self, storage: SQLiteStorage) -> None:
        entry = storage.add(_entry(notes="personal account"))
        assert storage.get(entry.id).notes == "personal account"

    def test_category_stored(self, storage: SQLiteStorage) -> None:
        entry = storage.add(_entry(category="Finance"))
        assert storage.get(entry.id).category == "Finance"

    def test_tags_round_trip(self, storage: SQLiteStorage) -> None:
        entry = storage.add(_entry(tags=["work", "critical"]))
        assert storage.get(entry.id).tags == ["work", "critical"]

    def test_login_methods_round_trip(self, storage: SQLiteStorage) -> None:
        entry = storage.add(_entry(login_methods=["Google", "Email / Password"]))
        assert storage.get(entry.id).login_methods == ["Google", "Email / Password"]

    def test_optional_fields_none(self, storage: SQLiteStorage) -> None:
        entry = storage.add(_entry(url=None, notes=None, email=None))
        fetched = storage.get(entry.id)
        assert fetched.url is None
        assert fetched.notes is None
        assert fetched.email is None

    def test_timestamps_set(self, storage: SQLiteStorage) -> None:
        entry = storage.add(_entry())
        assert isinstance(entry.created_at, datetime)
        assert isinstance(entry.updated_at, datetime)

    def test_title_only_entry(self, storage: SQLiteStorage) -> None:
        """All fields except title are optional."""
        e = storage.add(PasswordEntry(id=None, title="Bare"))
        fetched = storage.get(e.id)
        assert fetched.title == "Bare"
        assert fetched.username is None
        assert fetched.password is None


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

    def test_updates_email(self, storage: SQLiteStorage) -> None:
        entry = storage.add(_entry(email="old@example.com"))
        entry.email = "new@example.com"
        storage.update(entry)
        assert storage.get(entry.id).email == "new@example.com"

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
        with pytest.raises(ValueError, match="without id"):
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
# Company CRUD
# ---------------------------------------------------------------------------


class TestCompanyCRUD:
    def test_add_and_get(self, storage: SQLiteStorage) -> None:
        c = storage.add_company(_company(name="OpenAI"))
        assert c.id is not None
        fetched = storage.get_company(c.id)
        assert fetched.name == "OpenAI"

    def test_add_with_full_details(self, storage: SQLiteStorage) -> None:
        addr = CompanyAddress(country="United States", country_code="us",
                              street="1 Infinite Loop", city="Cupertino", state="CA",
                              postcode="95014")
        c = storage.add_company(Company(
            id=None, name="Apple Inc.",
            icon={"type": "iconify", "value": "logos:apple"},
            address=addr,
            revenue=383_000_000_000.0,
        ))
        fetched = storage.get_company(c.id)
        assert fetched.revenue == 383_000_000_000.0
        assert fetched.address.country == "United States"
        assert fetched.address.city == "Cupertino"
        assert fetched.icon["value"] == "logos:apple"

    def test_add_company_no_address(self, storage: SQLiteStorage) -> None:
        c = storage.add_company(_company(name="Bare Corp"))
        fetched = storage.get_company(c.id)
        assert fetched.address is None
        assert fetched.revenue is None
        assert fetched.icon is None

    def test_get_missing_returns_none(self, storage: SQLiteStorage) -> None:
        assert storage.get_company(99999) is None

    def test_list_companies_empty(self, storage: SQLiteStorage) -> None:
        assert storage.list_companies() == []

    def test_list_companies_ordered_by_name(self, storage: SQLiteStorage) -> None:
        storage.add_company(_company(name="Zebra"))
        storage.add_company(_company(name="Apple"))
        storage.add_company(_company(name="Meta"))
        names = [c.name for c in storage.list_companies()]
        assert names == sorted(names)

    def test_update_company(self, storage: SQLiteStorage) -> None:
        c = storage.add_company(_company(name="OldName"))
        c.name = "NewName"
        storage.update_company(c)
        assert storage.get_company(c.id).name == "NewName"

    def test_update_company_revenue(self, storage: SQLiteStorage) -> None:
        c = storage.add_company(_company(revenue=1_000_000.0))
        c.revenue = 2_000_000.0
        storage.update_company(c)
        assert storage.get_company(c.id).revenue == 2_000_000.0

    def test_update_company_raises_for_none_id(self, storage: SQLiteStorage) -> None:
        with pytest.raises(ValueError, match="without id"):
            storage.update_company(_company(id=None))

    def test_update_company_raises_for_unknown_id(self, storage: SQLiteStorage) -> None:
        with pytest.raises(KeyError):
            storage.update_company(_company(id=99999))

    def test_delete_company(self, storage: SQLiteStorage) -> None:
        c = storage.add_company(_company())
        storage.delete_company(c.id)
        assert storage.get_company(c.id) is None

    def test_delete_company_raises_for_unknown_id(self, storage: SQLiteStorage) -> None:
        with pytest.raises(KeyError):
            storage.delete_company(99999)

    def test_entry_company_id_set_null_on_delete(self, storage: SQLiteStorage) -> None:
        c = storage.add_company(_company(name="Parent"))
        e = storage.add(_entry(company_id=c.id))
        storage.delete_company(c.id)
        # ON DELETE SET NULL
        assert storage.get(e.id).company_id is None


# ---------------------------------------------------------------------------
# Icons
# ---------------------------------------------------------------------------


class TestIcons:
    def test_save_and_list(self, storage: SQLiteStorage) -> None:
        storage.save_icon("logo.svg", b"<svg/>")
        assert "logo.svg" in storage.list_icons()

    def test_icons_dir_property(self, storage: SQLiteStorage, tmp_path: Path) -> None:
        assert storage.icons_dir == tmp_path / "icons"


# ---------------------------------------------------------------------------
# Encryption
# ---------------------------------------------------------------------------


class TestEncryption:
    def test_wrong_master_fails_on_get(self, tmp_path: Path) -> None:
        s1 = SQLiteStorage(master_password="correct", vault_dir=tmp_path)
        s1.add(_entry(password="secret"))
        with pytest.raises(Exception):
            SQLiteStorage(master_password="wrong", vault_dir=tmp_path)

    def test_wrong_master_fails_on_list(self, tmp_path: Path) -> None:
        s1 = SQLiteStorage(master_password="correct", vault_dir=tmp_path)
        s1.add(_entry(password="secret"))
        with pytest.raises(Exception):
            SQLiteStorage(master_password="wrong", vault_dir=tmp_path)

    def test_correct_master_decrypts(self, tmp_path: Path) -> None:
        s1 = SQLiteStorage(master_password="correct", vault_dir=tmp_path)
        entry = s1.add(_entry(password="plaintext"))
        s2 = SQLiteStorage(master_password="correct", vault_dir=tmp_path)
        assert s2.get(entry.id).password == "plaintext"

    def test_to_dict_contains_all_keys(self, storage: SQLiteStorage) -> None:
        entry = storage.add(_entry(url="https://x.com", notes="n",
                                   email="x@x.com", category="Tech",
                                   tags=["a"], login_methods=["Google"]))
        d = entry.to_dict()
        for key in ("id", "title", "username", "email", "password", "url",
                    "notes", "category", "tags", "login_methods",
                    "created_at", "updated_at"):
            assert key in d


class TestReencrypt:
    """Tests for SQLiteStorage.reencrypt() — master password change."""

    def test_data_survives_reencrypt(self, tmp_path: Path) -> None:
        """All plaintext values are preserved after re-encryption."""
        s = SQLiteStorage(master_password="old-pass", vault_dir=tmp_path)
        e = s.add(_entry(password="s3cr3t", email="x@x.com", notes="my note"))
        s.reencrypt("new-pass")
        fetched = s.get(e.id)
        assert fetched.password == "s3cr3t"
        assert fetched.email    == "x@x.com"
        assert fetched.notes    == "my note"

    def test_new_master_opens_vault(self, tmp_path: Path) -> None:
        """A fresh SQLiteStorage instance opened with the new password works."""
        s = SQLiteStorage(master_password="old-pass", vault_dir=tmp_path)
        e = s.add(_entry(password="hunter2"))
        s.reencrypt("new-pass")

        s2 = SQLiteStorage(master_password="new-pass", vault_dir=tmp_path)
        assert s2.get(e.id).password == "hunter2"

    def test_old_master_rejected_after_reencrypt(self, tmp_path: Path) -> None:
        """Opening the vault with the old password raises after re-encryption."""
        s = SQLiteStorage(master_password="old-pass", vault_dir=tmp_path)
        s.add(_entry())
        s.reencrypt("new-pass")

        with pytest.raises(Exception):
            SQLiteStorage(master_password="old-pass", vault_dir=tmp_path)

    def test_reencrypt_multiple_entries(self, tmp_path: Path) -> None:
        """Re-encryption works correctly for multiple entries."""
        s = SQLiteStorage(master_password="pwd", vault_dir=tmp_path)
        entries = [
            s.add(_entry(title=f"Entry {i}", password=f"pass{i}", email=f"u{i}@x.com"))
            for i in range(5)
        ]
        s.reencrypt("new-pwd")
        s2 = SQLiteStorage(master_password="new-pwd", vault_dir=tmp_path)
        for i, e in enumerate(entries):
            fetched = s2.get(e.id)
            assert fetched.password == f"pass{i}"
            assert fetched.email    == f"u{i}@x.com"

    def test_reencrypt_handles_null_encrypted_fields(self, tmp_path: Path) -> None:
        """Entries with None email/notes/password are preserved as None."""
        s = SQLiteStorage(master_password="pwd", vault_dir=tmp_path)
        e = s.add(_entry(password=None, email=None, notes=None))
        s.reencrypt("new-pwd")
        s2 = SQLiteStorage(master_password="new-pwd", vault_dir=tmp_path)
        fetched = s2.get(e.id)
        assert fetched.password is None
        assert fetched.email    is None
        assert fetched.notes    is None