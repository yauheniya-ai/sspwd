#!/usr/bin/env python3
"""
examine_vault.py
----------------
Inspect the contents of an sspwd vault.

Two modes:
  RAW       — show encrypted bytes as stored (no password needed)
  DECRYPTED — show plaintext fields (master password required)

Usage:
    # By project name  (looks in ~/.sspwd/<project>/vault.db)
    python examine_vault.py --project demo
    python examine_vault.py --project demo --decrypt
    python examine_vault.py --project demo --schema
    python examine_vault.py --project demo --companies
    python examine_vault.py --project demo --icons

    # By explicit path
    python examine_vault.py --db /path/to/vault.db --decrypt

    # List all local projects
    python examine_vault.py --list
"""

from __future__ import annotations

import argparse
import base64
import json
import sqlite3
import sys
from pathlib import Path


# ── crypto ───────────────────────────────────────────────────────────────────

def _derive_key(master_password: str, salt: bytes) -> bytes:
    try:
        from argon2.low_level import Type, hash_secret_raw
    except ImportError:
        print("[ERROR] argon2-cffi not installed.  Run: pip install argon2-cffi")
        sys.exit(1)
    return hash_secret_raw(
        secret=master_password.encode(),
        salt=salt,
        time_cost=3,
        memory_cost=65536,
        parallelism=2,
        hash_len=32,
        type=Type.ID,
    )


def _make_aesgcm(master_password: str, vault_dir: Path):
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        print("[ERROR] cryptography not installed.  Run: pip install cryptography")
        sys.exit(1)
    salt_path = vault_dir / "salt.bin"
    if not salt_path.exists():
        print(f"[ERROR] salt.bin not found in {vault_dir}")
        sys.exit(1)
    return AESGCM(_derive_key(master_password, salt_path.read_bytes()))


def _verify_password(master_password: str, vault_dir: Path) -> bool:
    """Return True if master password is correct, False otherwise."""
    sentinel = vault_dir / "verify.bin"
    if not sentinel.exists():
        return True   # old vault without sentinel — can't verify
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        salt = (vault_dir / "salt.bin").read_bytes()
        raw  = sentinel.read_bytes()
        AESGCM(_derive_key(master_password, salt)).decrypt(raw[:12], raw[12:], None)
        return True
    except Exception:
        return False


def _decrypt(aesgcm, token: str | None) -> str:
    if not token:
        return "—"
    try:
        raw = base64.urlsafe_b64decode(token.encode())
        return aesgcm.decrypt(raw[:12], raw[12:], None).decode()
    except Exception:
        return "[decryption failed — wrong password?]"


# ── db helpers ────────────────────────────────────────────────────────────────

def _connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        print(f"[ERROR] vault.db not found: {db_path}")
        sys.exit(1)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.OperationalError:
        return set()


def _fmt_json_list(raw: str | None) -> str:
    if not raw:
        return "—"
    try:
        items = json.loads(raw)
        return ", ".join(items) if items else "—"
    except Exception:
        return raw


def _fmt_revenue(r: float | None) -> str:
    if r is None:
        return "—"
    if r >= 1_000_000_000:
        s = f"{r / 1_000_000_000:.1f}"
        s = s.rstrip("0").rstrip(".")
        return f"${s}B"
    if r >= 1_000_000:
        return f"${r / 1_000_000:.0f}M"
    if r >= 1_000:
        return f"${r / 1_000:.0f}K"
    return f"${r:.0f}"


def _sep(char: str = "─", width: int = 84) -> str:
    return char * width


# ── views ─────────────────────────────────────────────────────────────────────

def show_metadata(conn: sqlite3.Connection, db_path: Path) -> None:
    print(_sep("═"))
    print(f"  PROJECT   : {db_path.parent.name}")
    print(f"  DATABASE  : {db_path}")
    print(f"  SIZE      : {db_path.stat().st_size:,} bytes")
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    print(f"  TABLES    : {', '.join(r['name'] for r in tables)}")
    entry_count = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    print(f"  ENTRIES   : {entry_count}")
    try:
        company_count = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        print(f"  COMPANIES : {company_count}")
    except sqlite3.OperationalError:
        pass
    try:
        ic_count = conn.execute("SELECT COUNT(*) FROM icon_catalogue").fetchone()[0]
        print(f"  ICONS     : {ic_count}")
    except sqlite3.OperationalError:
        pass
    print(_sep("═"))


def show_schema(conn: sqlite3.Connection) -> None:
    print("\n  SCHEMA\n")
    rows = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    for row in rows:
        if row["sql"]:
            print("  " + row["sql"].replace("\n", "\n  "))
            print()


def show_raw(conn: sqlite3.Connection) -> None:
    cols = _columns(conn, "entries")
    rows = conn.execute("SELECT * FROM entries ORDER BY id").fetchall()
    print(f"\n  RAW ENTRIES — {len(rows)} total  (sensitive fields shown as ciphertext)\n")
    if not rows:
        print("  (no entries)")
        print()
        return
    for row in rows:
        print(_sep())
        print(f"  id              : {row['id']}")
        print(f"  title           : {row['title']}")
        print(f"  username        : {row['username'] or '—'}")
        if "email" in cols:
            v = row["email"] or "—"
            print(f"  email           : {v[:72]}{'…' if len(v) > 72 else ''}")
        v = row["password"] or "—"
        print(f"  password        : {v[:72]}{'…' if len(v) > 72 else ''}")
        print(f"  url             : {row['url'] or '—'}")
        if "category" in cols:
            print(f"  category        : {row['category'] or '—'}")
        if "tags" in cols:
            print(f"  tags            : {_fmt_json_list(row['tags'])}")
        if "login_methods" in cols:
            print(f"  login_methods   : {_fmt_json_list(row['login_methods'])}")
        if "company_id" in cols:
            print(f"  company_id      : {row['company_id'] or '—'}")
        if "user_created_at" in cols:
            print(f"  user_created_at : {row['user_created_at'] or '—'}")
        print(f"  created_at      : {row['created_at']}")
        print(f"  updated_at      : {row['updated_at']}")
        if "notes" in cols and row["notes"]:
            v = row["notes"]
            print(f"  notes           : {v[:72]}{'…' if len(v) > 72 else ''}  (encrypted)")
    print(_sep())
    print("\n  Tip: run with --decrypt to reveal passwords, emails and notes.\n")


def show_decrypted(conn: sqlite3.Connection, vault_dir: Path) -> None:
    import getpass
    master = getpass.getpass("  Master password: ")

    if not _verify_password(master, vault_dir):
        print("\n  [ERROR] Wrong master password.\n")
        sys.exit(1)

    aesgcm = _make_aesgcm(master, vault_dir)
    cols   = _columns(conn, "entries")
    rows   = conn.execute("SELECT * FROM entries ORDER BY id").fetchall()

    print(f"\n  DECRYPTED ENTRIES — {len(rows)} total\n")
    if not rows:
        print("  (no entries)")
        print()
        return
    for row in rows:
        print(_sep())
        print(f"  id              : {row['id']}")
        print(f"  title           : {row['title']}")
        print(f"  username        : {row['username'] or '—'}")
        if "email" in cols:
            print(f"  email           : {_decrypt(aesgcm, row['email'])}")
        print(f"  password        : {_decrypt(aesgcm, row['password'])}")
        print(f"  url             : {row['url'] or '—'}")
        if "category" in cols:
            print(f"  category        : {row['category'] or '—'}")
        if "tags" in cols:
            print(f"  tags            : {_fmt_json_list(row['tags'])}")
        if "login_methods" in cols:
            print(f"  login_methods   : {_fmt_json_list(row['login_methods'])}")
        if "company_id" in cols:
            print(f"  company_id      : {row['company_id'] or '—'}")
        if "user_created_at" in cols:
            print(f"  user_created_at : {row['user_created_at'] or '—'}")
        print(f"  created_at      : {row['created_at']}")
        print(f"  updated_at      : {row['updated_at']}")
        if "notes" in cols:
            print(f"  notes           : {_decrypt(aesgcm, row['notes'])}")
    print(_sep())


def show_companies(conn: sqlite3.Connection) -> None:
    cols = _columns(conn, "companies")
    if not cols:
        print("\n  (no companies table — vault predates v0.2.0)\n")
        return
    rows = conn.execute("SELECT * FROM companies ORDER BY name").fetchall()
    print(f"\n  COMPANIES — {len(rows)} total\n")
    if not rows:
        print("  (no companies)")
        print()
        return
    for row in rows:
        print(_sep())
        print(f"  id       : {row['id']}")
        print(f"  name     : {row['name']}")
        if "icon" in cols and row["icon"]:
            try:
                icon = json.loads(row["icon"])
                print(f"  icon     : [{icon.get('type','?')}] {str(icon.get('value',''))[:60]}")
            except Exception:
                print(f"  icon     : {str(row['icon'])[:60]}")
        if "address" in cols and row["address"]:
            try:
                a     = json.loads(row["address"])
                parts = [a.get("street"), a.get("city"), a.get("state"),
                         a.get("postcode"), a.get("country")]
                print(f"  address  : {', '.join(p for p in parts if p)}")
                print(f"  country  : {a.get('country','—')}  ({a.get('countryCode','?').upper()})")
            except Exception:
                print(f"  address  : {str(row['address'])[:80]}")
        if "revenue" in cols:
            print(f"  revenue  : {_fmt_revenue(row['revenue'])}  (raw: {row['revenue']})")
    print(_sep())


def show_icon_catalogue(conn: sqlite3.Connection) -> None:
    cols = _columns(conn, "icon_catalogue")
    if not cols:
        print("\n  (no icon_catalogue table — vault predates icon library feature)\n")
        return
    rows = conn.execute("SELECT * FROM icon_catalogue ORDER BY created_at DESC").fetchall()
    print(f"\n  ICON CATALOGUE — {len(rows)} total\n")
    if not rows:
        print("  (no icons catalogued yet)")
        print()
        return
    print(f"  {'ID':>4}  {'TYPE':<8}  {'LABEL':<20}  VALUE")
    print(f"  {'─'*4}  {'─'*8}  {'─'*20}  {'─'*46}")
    for row in rows:
        label = (row["label"] or "")[:20]
        value = str(row["value"])[:60]
        print(f"  {row['id']:>4}  {row['type']:<8}  {label:<20}  {value}")
    print()


def list_projects() -> None:
    root = Path.home() / ".sspwd"
    if not root.exists():
        print("  ~/.sspwd does not exist — no projects found.")
        return
    projects = sorted(
        d for d in root.iterdir()
        if d.is_dir() and (d / "vault.db").exists()
    )
    if not projects:
        print("  No projects found in ~/.sspwd/")
        return
    print(f"\n  Projects in {root}\n")
    print(f"  {'NAME':<22} {'ENTRIES':>7}  {'SIZE':>10}  PATH")
    print(f"  {'─'*22} {'─'*7}  {'─'*10}  {'─'*40}")
    for p in projects:
        db   = p / "vault.db"
        size = db.stat().st_size
        try:
            c     = sqlite3.connect(db)
            count = c.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
            c.close()
        except Exception:
            count = "?"
        print(f"  {p.name:<22} {str(count):>7}  {size:>9,}B  {db}")
    print()


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Examine the contents of an sspwd vault.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--project", "-p", metavar="NAME",
        help="Project name — looks in ~/.sspwd/<name>/vault.db")
    parser.add_argument("--db", type=Path,
        help="Explicit path to vault.db (overrides --project)")
    parser.add_argument("--decrypt", action="store_true",
        help="Decrypt sensitive fields (prompts for master password)")
    parser.add_argument("--schema", action="store_true",
        help="Print the SQL schema and exit")
    parser.add_argument("--companies", action="store_true",
        help="Show the companies / owners table")
    parser.add_argument("--icons", action="store_true",
        help="Show the icon catalogue table")
    parser.add_argument("--list", action="store_true",
        help="List all projects in ~/.sspwd/ and exit")
    args = parser.parse_args()

    if args.list:
        list_projects()
        return

    # ── resolve vault path ────────────────────────────────────────────────────
    if args.db:
        db_path   = args.db
        vault_dir = db_path.parent
    elif args.project:
        vault_dir = Path.home() / ".sspwd" / args.project
        db_path   = vault_dir / "vault.db"
    else:
        root     = Path.home() / ".sspwd"
        projects = (
            [d for d in root.iterdir() if d.is_dir() and (d / "vault.db").exists()]
            if root.exists() else []
        )
        if len(projects) == 1:
            vault_dir = projects[0]
            db_path   = vault_dir / "vault.db"
            print(f"  (auto-selected project: {vault_dir.name})")
        elif len(projects) == 0:
            print("[ERROR] No projects found in ~/.sspwd/")
            sys.exit(1)
        else:
            print("[ERROR] Multiple projects found — specify one:")
            for p in sorted(projects):
                print(f"         --project {p.name}")
            sys.exit(1)

    conn = _connect(db_path)
    show_metadata(conn, db_path)

    if args.schema:
        show_schema(conn)
    elif args.companies:
        show_companies(conn)
    elif args.icons:
        show_icon_catalogue(conn)
    elif args.decrypt:
        show_decrypted(conn, vault_dir)
    else:
        show_raw(conn)


if __name__ == "__main__":
    main()