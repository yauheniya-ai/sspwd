"""
SQLite storage backend — Argon2id + AES-256-GCM.

entries table columns:
    id, title, username*, email*, password*, url, notes*, category,
    tags (JSON), login_methods (JSON), company_id, user_created_at,
    created_at, updated_at
    (* encrypted with AES-256-GCM)

companies table columns:
    id, name, icon (JSON), address (JSON), revenue (REAL)
"""
from __future__ import annotations

import base64
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .base import BaseStorage, Company, CompanyAddress, PasswordEntry

# ── constants ────────────────────────────────────────────────────────────────

_DB_FILENAME        = "vault.db"
_SALT_FILENAME      = "salt.bin"
_SENTINEL_FILENAME  = "verify.bin"
_SENTINEL_PLAINTEXT = b"sspwd-ok"
_ICONS_DIRNAME      = "icons"
_DEFAULT_PROJECT    = "default"
_NONCE_LEN          = 12

_ARGON2_TIME_COST   = 3
_ARGON2_MEMORY_COST = 65536
_ARGON2_PARALLELISM = 2
_ARGON2_HASH_LEN    = 32

# Columns that are AES-encrypted in the entries table
_ENCRYPTED_ENTRY_COLS = {"password", "email", "notes"}


# ── module helpers ────────────────────────────────────────────────────────────

def _derive_key(master_password: str, salt: bytes) -> bytes:
    return hash_secret_raw(
        secret=master_password.encode(),
        salt=salt,
        time_cost=_ARGON2_TIME_COST,
        memory_cost=_ARGON2_MEMORY_COST,
        parallelism=_ARGON2_PARALLELISM,
        hash_len=_ARGON2_HASH_LEN,
        type=Type.ID,
    )


def project_dir(project: str = _DEFAULT_PROJECT, base: Optional[Path] = None) -> Path:
    root = base or (Path.home() / ".sspwd")
    return root / project


# ── storage class ─────────────────────────────────────────────────────────────

class SQLiteStorage(BaseStorage):

    def __init__(
        self,
        master_password: str,
        project: str = _DEFAULT_PROJECT,
        vault_dir: Optional[Path] = None,
    ) -> None:
        self._vault_dir = Path(vault_dir) if vault_dir else project_dir(project)
        self._vault_dir.mkdir(parents=True, exist_ok=True)

        self._icons_dir     = self._vault_dir / _ICONS_DIRNAME
        self._icons_dir.mkdir(exist_ok=True)
        self._db_path       = self._vault_dir / _DB_FILENAME
        self._salt_path     = self._vault_dir / _SALT_FILENAME
        self._sentinel_path = self._vault_dir / _SENTINEL_FILENAME

        salt         = self._load_or_create_salt()
        key          = _derive_key(master_password, salt)
        self._aesgcm = AESGCM(key)

        self._write_or_verify_sentinel()
        self.initialize()

    # ── properties ───────────────────────────────────────────────────────────

    @property
    def icons_dir(self) -> Path:
        return self._icons_dir

    @property
    def vault_dir(self) -> Path:
        return self._vault_dir

    # ── crypto helpers ────────────────────────────────────────────────────────

    def _load_or_create_salt(self) -> bytes:
        if self._salt_path.exists():
            return self._salt_path.read_bytes()
        salt = os.urandom(32)
        self._salt_path.write_bytes(salt)
        return salt

    def _write_or_verify_sentinel(self) -> None:
        if self._sentinel_path.exists():
            raw = self._sentinel_path.read_bytes()
            self._aesgcm.decrypt(raw[:_NONCE_LEN], raw[_NONCE_LEN:], None)
        else:
            nonce = os.urandom(_NONCE_LEN)
            self._sentinel_path.write_bytes(
                nonce + self._aesgcm.encrypt(nonce, _SENTINEL_PLAINTEXT, None)
            )

    def _encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(_NONCE_LEN)
        ct    = self._aesgcm.encrypt(nonce, plaintext.encode(), None)
        return base64.urlsafe_b64encode(nonce + ct).decode()

    def _decrypt(self, token: str) -> str:
        raw = base64.urlsafe_b64decode(token.encode())
        return self._aesgcm.decrypt(raw[:_NONCE_LEN], raw[_NONCE_LEN:], None).decode()

    # ── db helpers ────────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Add any columns that did not exist in older vault versions."""
        entry_existing  = {row[1] for row in conn.execute("PRAGMA table_info(entries)")}
        company_existing = {row[1] for row in conn.execute("PRAGMA table_info(companies)")}

        entry_new_cols = [
            ("email",           "TEXT"),
            ("category",        "TEXT DEFAULT 'Other'"),
            ("tags",            "TEXT DEFAULT '[]'"),
            ("login_methods",   "TEXT DEFAULT '[]'"),
            ("company_id",      "INTEGER"),
            ("user_created_at", "TEXT"),
        ]
        for col, defn in entry_new_cols:
            if col not in entry_existing:
                conn.execute(f"ALTER TABLE entries ADD COLUMN {col} {defn}")

        company_new_cols = [
            ("icon",    "TEXT"),
            ("address", "TEXT"),
            ("revenue", "REAL"),
        ]
        for col, defn in company_new_cols:
            if col not in company_existing:
                conn.execute(f"ALTER TABLE companies ADD COLUMN {col} {defn}")

    # ── schema ────────────────────────────────────────────────────────────────

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS companies (
                    id      INTEGER PRIMARY KEY AUTOINCREMENT,
                    name    TEXT    NOT NULL,
                    icon    TEXT,           -- JSON {type, value}
                    address TEXT,           -- JSON CompanyAddress
                    revenue REAL            -- raw USD number
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS entries (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    title           TEXT    NOT NULL,
                    username        TEXT,
                    email           TEXT,   -- AES-encrypted
                    password        TEXT,   -- AES-encrypted
                    url             TEXT,
                    notes           TEXT,   -- AES-encrypted
                    category        TEXT    NOT NULL DEFAULT 'Other',
                    tags            TEXT    NOT NULL DEFAULT '[]',  -- JSON array
                    login_methods   TEXT    NOT NULL DEFAULT '[]',  -- JSON array
                    company_id      INTEGER REFERENCES companies(id) ON DELETE SET NULL,
                    user_created_at TEXT,
                    created_at      TEXT    NOT NULL,
                    updated_at      TEXT    NOT NULL
                )
            """)
            self._migrate(conn)

    # ── entries CRUD ──────────────────────────────────────────────────────────

    def _enc_opt(self, v: Optional[str]) -> Optional[str]:
        """Encrypt if not None, else return None."""
        return self._encrypt(v) if v is not None else None

    def _dec_opt(self, v: Optional[str]) -> Optional[str]:
        """Decrypt if not None, else return None."""
        return self._decrypt(v) if v is not None else None

    def _row_to_entry(self, row: sqlite3.Row) -> PasswordEntry:
        return PasswordEntry(
            id              = row["id"],
            title           = row["title"],
            username        = row["username"] if row["username"] else None,
            email           = self._dec_opt(row["email"]),
            password        = self._dec_opt(row["password"]),
            url             = row["url"],
            notes           = self._dec_opt(row["notes"]),
            category        = row["category"] or "Other",
            tags            = json.loads(row["tags"]) if row["tags"] else [],
            login_methods   = json.loads(row["login_methods"]) if row["login_methods"] else [],
            company_id      = row["company_id"],
            user_created_at = datetime.fromisoformat(row["user_created_at"]) if row["user_created_at"] else None,
            created_at      = datetime.fromisoformat(row["created_at"]),
            updated_at      = datetime.fromisoformat(row["updated_at"]),
        )

    def add(self, entry: PasswordEntry) -> PasswordEntry:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO entries
                   (title, username, email, password, url, notes, category, tags,
                    login_methods, company_id, user_created_at, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    entry.title,
                    entry.username,
                    self._enc_opt(entry.email),
                    self._enc_opt(entry.password),
                    entry.url,
                    self._enc_opt(entry.notes),
                    entry.category or "Other",
                    json.dumps(entry.tags),
                    json.dumps(entry.login_methods),
                    entry.company_id,
                    entry.user_created_at.isoformat() if entry.user_created_at else None,
                    now, now,
                ),
            )
            entry.id         = cur.lastrowid
            entry.created_at = datetime.fromisoformat(now)
            entry.updated_at = entry.created_at
        return entry

    def get(self, entry_id: int) -> Optional[PasswordEntry]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
        return self._row_to_entry(row) if row else None

    def list(self, search: Optional[str] = None) -> list[PasswordEntry]:
        with self._connect() as conn:
            if search:
                p = f"%{search}%"
                rows = conn.execute(
                    """SELECT * FROM entries
                       WHERE title LIKE ? OR username LIKE ?
                          OR (url IS NOT NULL AND url LIKE ?)
                          OR category LIKE ?
                       ORDER BY title""",
                    (p, p, p, p),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM entries ORDER BY title").fetchall()
        return [self._row_to_entry(r) for r in rows]

    def update(self, entry: PasswordEntry) -> PasswordEntry:
        if entry.id is None:
            raise ValueError("Cannot update entry without id.")
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            rc = conn.execute(
                """UPDATE entries
                   SET title=?, username=?, email=?, password=?, url=?, notes=?,
                       category=?, tags=?, login_methods=?, company_id=?,
                       user_created_at=?, updated_at=?
                   WHERE id=?""",
                (
                    entry.title,
                    entry.username,
                    self._enc_opt(entry.email),
                    self._enc_opt(entry.password),
                    entry.url,
                    self._enc_opt(entry.notes),
                    entry.category or "Other",
                    json.dumps(entry.tags),
                    json.dumps(entry.login_methods),
                    entry.company_id,
                    entry.user_created_at.isoformat() if entry.user_created_at else None,
                    now, entry.id,
                ),
            ).rowcount
        if rc == 0:
            raise KeyError(f"No entry with id={entry.id}")
        entry.updated_at = datetime.fromisoformat(now)
        return entry

    def delete(self, entry_id: int) -> None:
        with self._connect() as conn:
            rc = conn.execute("DELETE FROM entries WHERE id=?", (entry_id,)).rowcount
        if rc == 0:
            raise KeyError(f"No entry with id={entry_id}")

    # ── companies CRUD ────────────────────────────────────────────────────────

    def _row_to_company(self, row: sqlite3.Row) -> Company:
        icon_raw    = row["icon"]
        address_raw = row["address"]
        return Company(
            id      = row["id"],
            name    = row["name"],
            icon    = json.loads(icon_raw)    if icon_raw    else None,
            address = CompanyAddress.from_dict(json.loads(address_raw)) if address_raw else None,
            revenue = row["revenue"],
        )

    def add_company(self, company: Company) -> Company:
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO companies (name, icon, address, revenue) VALUES (?,?,?,?)",
                (
                    company.name,
                    json.dumps(company.icon)             if company.icon    else None,
                    json.dumps(company.address.to_dict()) if company.address else None,
                    company.revenue,
                ),
            )
            company.id = cur.lastrowid
        return company

    def get_company(self, company_id: int) -> Optional[Company]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM companies WHERE id=?", (company_id,)).fetchone()
        return self._row_to_company(row) if row else None

    def list_companies(self) -> list[Company]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM companies ORDER BY name").fetchall()
        return [self._row_to_company(r) for r in rows]

    def update_company(self, company: Company) -> Company:
        if company.id is None:
            raise ValueError("Cannot update company without id.")
        with self._connect() as conn:
            rc = conn.execute(
                "UPDATE companies SET name=?, icon=?, address=?, revenue=? WHERE id=?",
                (
                    company.name,
                    json.dumps(company.icon)             if company.icon    else None,
                    json.dumps(company.address.to_dict()) if company.address else None,
                    company.revenue,
                    company.id,
                ),
            ).rowcount
        if rc == 0:
            raise KeyError(f"No company with id={company.id}")
        return company

    def delete_company(self, company_id: int) -> None:
        with self._connect() as conn:
            rc = conn.execute("DELETE FROM companies WHERE id=?", (company_id,)).rowcount
        if rc == 0:
            raise KeyError(f"No company with id={company_id}")

    # ── icons ─────────────────────────────────────────────────────────────────

    def save_icon(self, filename: str, data: bytes) -> Path:
        dest = self._icons_dir / filename
        dest.write_bytes(data)
        return dest

    def list_icons(self) -> list[str]:
        return [f.name for f in self._icons_dir.iterdir() if f.is_file()]