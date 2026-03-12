#!/usr/bin/env python3
"""
change_master_password.py — Re-encrypt a sspwd project vault with a new master password.

Usage
-----
    python scripts/change_master_password.py [PROJECT]

    PROJECT defaults to "default" when omitted.

Examples
--------
    # Change password for the "demo" project
    python scripts/change_master_password.py demo

    # Change password for the default project
    python scripts/change_master_password.py
"""

import sys
from pathlib import Path

# Allow running from the repo root without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import getpass
from sspwd.storage.sqlite import SQLiteStorage, project_dir, _DEFAULT_PROJECT


def main() -> None:
    project = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_PROJECT
    vault   = project_dir(project)

    if not (vault / "vault.db").exists():
        print(f"✗  No vault found for project '{project}' at {vault}", file=sys.stderr)
        sys.exit(1)

    print(f"Re-encrypting vault for project: {project}")
    print(f"Vault path: {vault}\n")

    current = getpass.getpass("Current master password: ")
    try:
        storage = SQLiteStorage(master_password=current, vault_dir=vault)
    except Exception:
        print("✗  Wrong master password.", file=sys.stderr)
        sys.exit(1)

    entry_count = len(storage.list())
    print(f"  {entry_count} {'entry' if entry_count == 1 else 'entries'} found.\n")

    new_pw = getpass.getpass("New master password: ")
    if not new_pw:
        print("✗  New password must not be empty.", file=sys.stderr)
        sys.exit(1)

    confirm = getpass.getpass("Confirm new master password: ")
    if new_pw != confirm:
        print("✗  Passwords do not match.", file=sys.stderr)
        sys.exit(1)

    if new_pw == current:
        print("  New password is identical to the current one. Nothing changed.")
        return

    print(f"\nRe-encrypting {entry_count} {'entry' if entry_count == 1 else 'entries'}…")
    storage.reencrypt(new_pw)
    print(f"✓  Master password changed for project '{project}'.")


if __name__ == "__main__":
    main()
