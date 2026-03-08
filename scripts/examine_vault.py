#!/usr/bin/env python3
"""
examine_vault.py
----------------
Inspect the raw contents of ~/.sspwd/vault.db.

Two modes:
  1. RAW   — show the encrypted bytes as stored on disk (no password needed)
  2. DECRYPTED — show plaintext passwords (master password required)

Usage:
    python examine_vault.py              # raw view
    python examine_vault.py --decrypt    # decrypted view (will prompt for password)
    python examine_vault.py --schema     # print the SQL schema
    python examine_vault.py --db /custom/path/vault.db --decrypt
"""

import argparse
import hashlib
import base64
import sqlite3
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        print(f"[ERROR] Database not found: {db_path}")
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def derive_fernet(master_password: str, salt: bytes):
    from cryptography.fernet import Fernet
    dk = hashlib.pbkdf2_hmac("sha256", master_password.encode(), salt, iterations=390_000, dklen=32)
    return Fernet(base64.urlsafe_b64encode(dk))


def decrypt_field(fernet, value: str | None) -> str:
    if value is None:
        return "-"
    try:
        return fernet.decrypt(value.encode()).decode()
    except Exception:
        return "[decryption failed — wrong master password?]"


def separator(char: str = "─", width: int = 80) -> str:
    return char * width


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

def show_metadata(conn: sqlite3.Connection, db_path: Path) -> None:
    print(separator("═"))
    print(f"  DATABASE : {db_path}")
    print(f"  SIZE     : {db_path.stat().st_size:,} bytes")

    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    print(f"  TABLES   : {', '.join(r['name'] for r in tables)}")

    count = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    print(f"  ENTRIES  : {count}")
    print(separator("═"))


def show_raw(conn: sqlite3.Connection) -> None:
    print("\n  RAW ENCRYPTED CONTENTS\n")
    rows = conn.execute("SELECT * FROM entries ORDER BY id").fetchall()

    if not rows:
        print("  (no entries found)")
        return

    for row in rows:
        print(separator())
        print(f"  ID         : {row['id']}")
        print(f"  title      : {row['title']}")
        print(f"  username   : {row['username']}")
        print(f"  password   : {row['password'][:60]}…")   # truncated — it's long ciphertext
        print(f"  url        : {row['url'] or '-'}")
        print(f"  notes      : {(row['notes'] or '-')[:60]}")
        print(f"  created_at : {row['created_at']}")
        print(f"  updated_at : {row['updated_at']}")

    print(separator())


def show_decrypted(conn: sqlite3.Connection, vault_dir: Path) -> None:
    import getpass
    master = getpass.getpass("  Master password: ")

    salt_path = vault_dir / "salt.bin"
    if not salt_path.exists():
        print(f"[ERROR] Salt file not found: {salt_path}")
        sys.exit(1)

    salt = salt_path.read_bytes()
    fernet = derive_fernet(master, salt)

    print("\n  DECRYPTED CONTENTS\n")
    rows = conn.execute("SELECT * FROM entries ORDER BY id").fetchall()

    if not rows:
        print("  (no entries found)")
        return

    for row in rows:
        print(separator())
        print(f"  ID         : {row['id']}")
        print(f"  title      : {row['title']}")
        print(f"  username   : {row['username']}")
        print(f"  password   : {decrypt_field(fernet, row['password'])}")
        print(f"  url        : {row['url'] or '-'}")
        print(f"  notes      : {decrypt_field(fernet, row['notes'])}")
        print(f"  created_at : {row['created_at']}")
        print(f"  updated_at : {row['updated_at']}")

    print(separator())


def show_schema(conn: sqlite3.Connection) -> None:
    print("\n  SCHEMA\n")
    rows = conn.execute("SELECT sql FROM sqlite_master WHERE type='table'").fetchall()
    for row in rows:
        print(" ", row["sql"])
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Examine the contents of an sspwd vault.db file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path.home() / ".sspwd" / "vault.db",
        help="Path to vault.db (default: ~/.sspwd/vault.db)",
    )
    parser.add_argument(
        "--decrypt",
        action="store_true",
        help="Decrypt and show plaintext passwords (prompts for master password)",
    )
    parser.add_argument(
        "--schema",
        action="store_true",
        help="Print the CREATE TABLE schema and exit",
    )
    args = parser.parse_args()

    db_path: Path = args.db
    vault_dir = db_path.parent
    conn = connect(db_path)

    show_metadata(conn, db_path)

    if args.schema:
        show_schema(conn)
        return

    if args.decrypt:
        try:
            from cryptography.fernet import Fernet  # noqa: F401
        except ImportError:
            print("[ERROR] cryptography package not installed.")
            print("        Run: pip install cryptography")
            sys.exit(1)
        show_decrypted(conn, vault_dir)
    else:
        show_raw(conn)
        print("\n  Tip: run with --decrypt to reveal plaintext passwords.\n")


if __name__ == "__main__":
    main()