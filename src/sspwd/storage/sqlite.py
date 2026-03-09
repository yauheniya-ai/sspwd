"""
SQLite storage backend with Argon2id key derivation and AES-256-GCM encryption.

Vault layout:
    ~/.sspwd/{project}/vault.db    — encrypted entries
    ~/.sspwd/{project}/salt.bin    — Argon2id salt (32 bytes, random, fixed per vault)
    ~/.sspwd/{project}/verify.bin  — encrypted sentinel; verifies master password on open
    ~/.sspwd/{project}/icons/      — user-uploaded company icons

Security design:
    - KDF:    Argon2id (OWASP 2024 recommended parameters)
    - Cipher: AES-256-GCM (authenticated encryption; 12-byte random nonce per message)
    - Salt:   32 bytes, generated once with os.urandom(), never regenerated
    - Key:    32 bytes; held in RAM only, never written to disk
    - Format: nonce (12 B) || ciphertext+tag stored as base64 text in SQLite
"""

from __future__ import annotations

import base64
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .base import BaseStorage, PasswordEntry

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DB_FILENAME        = "vault.db"
_SALT_FILENAME      = "salt.bin"
_SENTINEL_FILENAME  = "verify.bin"
_SENTINEL_PLAINTEXT = b"sspwd-ok"
_ICONS_DIRNAME      = "icons"
_DEFAULT_PROJECT    = "default"

# AES-GCM nonce length (96-bit is the standard recommendation)
_NONCE_LEN = 12

# Argon2id parameters — OWASP 2024 recommended minimum:
#   memory ≥ 19 MiB, iterations ≥ 2, parallelism ≥ 1
# Using slightly above minimum for a comfortable security margin.
_ARGON2_TIME_COST   = 3          # number of iterations
_ARGON2_MEMORY_COST = 65536      # 64 MiB (in KiB)
_ARGON2_PARALLELISM = 2
_ARGON2_HASH_LEN    = 32         # 256-bit output key for AES-256


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _derive_key(master_password: str, salt: bytes) -> bytes:
    """
    Derive a 256-bit key from the master password using Argon2id.
    Returns raw bytes (not base64) — used directly with AESGCM.
    """
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
    """Return the vault directory for a given project, e.g. ~/.sspwd/default/"""
    root = base or (Path.home() / ".sspwd")
    return root / project


# ---------------------------------------------------------------------------
# Storage class
# ---------------------------------------------------------------------------


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
        Override the full path to the vault directory (ignores project).
        Useful for tests.
    """

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

        salt       = self._load_or_create_salt()
        key        = _derive_key(master_password, salt)
        self._aesgcm = AESGCM(key)

        self._write_or_verify_sentinel()
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

    def _write_or_verify_sentinel(self) -> None:
        """
        First open: encrypt a known plaintext and write to verify.bin.
        Subsequent opens: decrypt it — raises InvalidTag on wrong password.
        """
        if self._sentinel_path.exists():
            raw = self._sentinel_path.read_bytes()
            nonce, blob = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
            # Raises cryptography.exceptions.InvalidTag on wrong key
            self._aesgcm.decrypt(nonce, blob, None)
        else:
            nonce = os.urandom(_NONCE_LEN)
            blob  = self._aesgcm.encrypt(nonce, _SENTINEL_PLAINTEXT, None)
            self._sentinel_path.write_bytes(nonce + blob)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _encrypt(self, plaintext: str) -> str:
        """Encrypt a string → base64(nonce + ciphertext+tag)."""
        nonce      = os.urandom(_NONCE_LEN)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode(), None)
        return base64.urlsafe_b64encode(nonce + ciphertext).decode()

    def _decrypt(self, token: str) -> str:
        """Decrypt a base64(nonce + ciphertext+tag) token → plaintext string."""
        raw        = base64.urlsafe_b64decode(token.encode())
        nonce, blob = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
        return self._aesgcm.decrypt(nonce, blob, None).decode()

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
            entry.id        = cur.lastrowid
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
        dest = self._icons_dir / filename
        dest.write_bytes(data)
        return dest

    def list_icons(self) -> list[str]:
        return [f.name for f in self._icons_dir.iterdir() if f.is_file()]