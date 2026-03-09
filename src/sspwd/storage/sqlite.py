"""
SQLite storage backend with Fernet symmetric encryption.

Vault layout:
    ~/.sspwd/{project}/vault.db   — encrypted entries
    ~/.sspwd/{project}/salt.bin   — PBKDF2 salt (never changes once created)
    ~/.sspwd/{project}/icons/     — user-uploaded company icons

The master password is used to derive an AES-128 key via PBKDF2.
The derived key is never stored on disk.
"""

from __future__ import annotations

import base64
import hashlib
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet

from .base import BaseStorage, PasswordEntry

_DB_FILENAME   = "vault.db"
_SALT_FILENAME = "salt.bin"
_ICONS_DIRNAME = "icons"
_DEFAULT_PROJECT = "default"


def _derive_key(master_password: str, salt: bytes) -> bytes:
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        master_password.encode(),
        salt,
        iterations=390_000,
        dklen=32,
    )
    return base64.urlsafe_b64encode(dk)


def project_dir(project: str = _DEFAULT_PROJECT, base: Optional[Path] = None) -> Path:
    """Return the directory for a given project, e.g. ~/.sspwd/default/"""
    root = base or (Path.home() / ".sspwd")
    return root / project


class SQLiteStorage(BaseStorage):
    """
    Parameters
    ----------
    master_password:
        The user's master password used to derive the encryption key.
    project:
        Project/workspace name. Determines the subdirectory used.
        Defaults to ``"default"``.
    vault_dir:
        Override the full path to the vault directory (ignores project + base).
        Useful for tests.
    """

    def __init__(
        self,
        master_password: str,
        project: str = _DEFAULT_PROJECT,
        vault_dir: Optional[Path] = None,
    ) -> None:
        if vault_dir:
            self._vault_dir = Path(vault_dir)
        else:
            self._vault_dir = project_dir(project)

        self._vault_dir.mkdir(parents=True, exist_ok=True)
        self._icons_dir = self._vault_dir / _ICONS_DIRNAME
        self._icons_dir.mkdir(exist_ok=True)

        self._db_path   = self._vault_dir / _DB_FILENAME
        self._salt_path = self._vault_dir / _SALT_FILENAME

        salt = self._load_or_create_salt()
        key  = _derive_key(master_password, salt)
        self._fernet = Fernet(key)

        self.initialize()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def icons_dir(self) -> Path:
        return self._icons_dir

    @property
    def vault_dir(self) -> Path:
        return self._vault_dir

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_or_create_salt(self) -> bytes:
        if self._salt_path.exists():
            return self._salt_path.read_bytes()
        salt = os.urandom(32)
        self._salt_path.write_bytes(salt)
        return salt

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def _decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode()).decode()

    def _row_to_entry(self, row: sqlite3.Row) -> PasswordEntry:
        return PasswordEntry(
            id=row["id"],
            title=row["title"],
            username=row["username"],
            password=self._decrypt(row["password"]),
            url=row["url"],
            notes=self._decrypt(row["notes"]) if row["notes"] else None,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    # ------------------------------------------------------------------
    # BaseStorage implementation
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    title       TEXT    NOT NULL,
                    username    TEXT    NOT NULL,
                    password    TEXT    NOT NULL,
                    url         TEXT,
                    notes       TEXT,
                    created_at  TEXT    NOT NULL,
                    updated_at  TEXT    NOT NULL
                )
                """
            )

    def add(self, entry: PasswordEntry) -> PasswordEntry:
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO entries (title, username, password, url, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.title,
                    entry.username,
                    self._encrypt(entry.password),
                    entry.url,
                    self._encrypt(entry.notes) if entry.notes else None,
                    now,
                    now,
                ),
            )
            entry.id = cur.lastrowid
            entry.created_at = datetime.fromisoformat(now)
            entry.updated_at = entry.created_at
        return entry

    def get(self, entry_id: int) -> Optional[PasswordEntry]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM entries WHERE id = ?", (entry_id,)
            ).fetchone()
        return self._row_to_entry(row) if row else None

    def list(self, search: Optional[str] = None) -> list[PasswordEntry]:
        with self._connect() as conn:
            if search:
                pattern = f"%{search}%"
                rows = conn.execute(
                    """SELECT * FROM entries
                       WHERE title LIKE ?
                          OR username LIKE ?
                          OR (url IS NOT NULL AND url LIKE ?)
                       ORDER BY title""",
                    (pattern, pattern, pattern),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM entries ORDER BY title"
                ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def update(self, entry: PasswordEntry) -> PasswordEntry:
        if entry.id is None:
            raise ValueError("Cannot update an entry without an id.")
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            rowcount = conn.execute(
                """
                UPDATE entries
                SET title=?, username=?, password=?, url=?, notes=?, updated_at=?
                WHERE id=?
                """,
                (
                    entry.title,
                    entry.username,
                    self._encrypt(entry.password),
                    entry.url,
                    self._encrypt(entry.notes) if entry.notes else None,
                    now,
                    entry.id,
                ),
            ).rowcount
        if rowcount == 0:
            raise KeyError(f"No entry with id={entry.id}")
        entry.updated_at = datetime.fromisoformat(now)
        return entry

    def delete(self, entry_id: int) -> None:
        with self._connect() as conn:
            rowcount = conn.execute(
                "DELETE FROM entries WHERE id=?", (entry_id,)
            ).rowcount
        if rowcount == 0:
            raise KeyError(f"No entry with id={entry_id}")

    # ------------------------------------------------------------------
    # Icon helpers
    # ------------------------------------------------------------------

    def save_icon(self, filename: str, data: bytes) -> Path:
        """Write icon bytes to the icons directory. Returns the saved path."""
        dest = self._icons_dir / filename
        dest.write_bytes(data)
        return dest

    def list_icons(self) -> list[str]:
        return [f.name for f in self._icons_dir.iterdir() if f.is_file()]