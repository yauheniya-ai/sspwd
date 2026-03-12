"""
CLI for sspwd.

Commands
--------
    sspwd serve            [--project NAME]   Start the web UI
    sspwd add              [--project NAME]   Add entry interactively
    sspwd list             [--project NAME]   List entries
    sspwd get              [--project NAME]   Show one entry
    sspwd delete           [--project NAME]   Delete an entry
    sspwd change-password  [--project NAME]   Re-encrypt vault with a new password
    sspwd version                             Print version
    sspwd projects                            List existing projects

Projects are stored as separate vaults under ~/.sspwd/{project}/vault.db.
The default project is named "default".
"""

import sys
from pathlib import Path
from typing import Optional

import click

from .__version__ import __version__
from .storage.sqlite import SQLiteStorage, project_dir, _DEFAULT_PROJECT
from .storage.base import PasswordEntry

# ---------------------------------------------------------------------------
# Shared option decorator
# ---------------------------------------------------------------------------

_project_option = click.option(
    "--project", "-p",
    default=_DEFAULT_PROJECT,
    show_default=True,
    help="Project / workspace name (subdirectory of ~/.sspwd/).",
)


def _get_storage(master: str, project: str, vault_dir: Optional[Path] = None) -> SQLiteStorage:
    return SQLiteStorage(master_password=master, project=project, vault_dir=vault_dir)


def _prompt_master() -> str:
    return click.prompt("Master password", hide_input=True)


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------


@click.group()
@click.version_option(__version__, prog_name="sspwd")
def cli() -> None:
    """sspwd — a local, encrypted password manager."""


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=7523, show_default=True)
@click.option("--no-browser", is_flag=True, default=False)
def serve(host: str, port: int, no_browser: bool) -> None:
    """Start the web UI. Projects are unlocked on demand in the browser."""
    from .ui.server import UIServer
    server = UIServer(host=host, port=port, open_browser=not no_browser)
    server.start(block=True)


@cli.command("add")
@_project_option
@click.option("--vault-dir", default=None, type=click.Path())
def add_entry(project: str, vault_dir: Optional[str]) -> None:
    """Add a new password entry interactively."""
    master  = _prompt_master()
    storage = _get_storage(master, project, Path(vault_dir) if vault_dir else None)

    title    = click.prompt("Title")
    category = click.prompt("Category")
    username = click.prompt("Username")
    password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
    url      = click.prompt("URL (optional)", default="")
    notes    = click.prompt("Notes (optional)", default="")

    entry = PasswordEntry(
        id=None, title=title, username=username, password=password,
        url=url or None, notes=notes or None,
    )
    created = storage.add(entry)
    click.echo(click.style(f"✓ Saved '{title}' (id={created.id}) in project '{project}'", fg="green"))


@cli.command("list")
@_project_option
@click.option("--search", "-s", default=None, help="Filter by title / username / URL.")
@click.option("--vault-dir", default=None, type=click.Path())
def list_entries(project: str, search: Optional[str], vault_dir: Optional[str]) -> None:
    """List all stored entries for a project."""
    master  = _prompt_master()
    storage = _get_storage(master, project, Path(vault_dir) if vault_dir else None)

    entries = storage.list(search=search)
    if not entries:
        click.echo("No entries found.")
        return

    click.echo(f"\n  Project: {project}\n")
    click.echo(f"{'ID':>4}  {'Title':<30}  {'Username':<25}  URL")
    click.echo("-" * 80)
    for e in entries:
        click.echo(f"{e.id:>4}  {e.title:<30}  {e.username:<25}  {e.url or ''}")


@cli.command("get")
@_project_option
@click.argument("entry_id", type=int)
@click.option("--vault-dir", default=None, type=click.Path())
def get_entry(project: str, entry_id: int, vault_dir: Optional[str]) -> None:
    """Show a single entry (reveals password)."""
    master  = _prompt_master()
    storage = _get_storage(master, project, Path(vault_dir) if vault_dir else None)
    entry   = storage.get(entry_id)

    if entry is None:
        click.echo(click.style(f"Entry {entry_id} not found.", fg="red"), err=True)
        sys.exit(1)

    click.echo(f"\nTitle    : {entry.title}")
    click.echo(f"Username : {entry.username}")
    click.echo(f"Password : {entry.password}")
    click.echo(f"URL      : {entry.url or '-'}")
    click.echo(f"Notes    : {entry.notes or '-'}")
    click.echo(f"Updated  : {entry.updated_at}")


@cli.command("delete")
@_project_option
@click.argument("entry_id", type=int)
@click.option("--yes", "-y", is_flag=True, default=False)
@click.option("--vault-dir", default=None, type=click.Path())
def delete_entry(project: str, entry_id: int, yes: bool, vault_dir: Optional[str]) -> None:
    """Delete an entry by ID."""
    master  = _prompt_master()
    storage = _get_storage(master, project, Path(vault_dir) if vault_dir else None)

    if not yes:
        click.confirm(f"Delete entry {entry_id} from project '{project}'?", abort=True)

    try:
        storage.delete(entry_id)
        click.echo(click.style(f"✓ Deleted entry {entry_id}.", fg="green"))
    except KeyError:
        click.echo(click.style(f"Entry {entry_id} not found.", fg="red"), err=True)
        sys.exit(1)


@cli.command("change-password")
@_project_option
@click.option("--vault-dir", default=None, type=click.Path())
def change_password(project: str, vault_dir: Optional[str]) -> None:
    """Change the master password for a project vault (re-encrypts the vault)."""
    click.echo(
        click.style("⚠  This will re-encrypt the entire vault.", fg="yellow")
    )

    current = click.prompt("Current master password", hide_input=True)
    try:
        storage = _get_storage(current, project, Path(vault_dir) if vault_dir else None)
    except Exception:
        click.echo(click.style("✗ Wrong master password.", fg="red"), err=True)
        sys.exit(1)

    new_pw = click.prompt(
        "New master password",
        hide_input=True,
        confirmation_prompt="Confirm new master password",
    )
    if not new_pw:
        click.echo(click.style("✗ New password must not be empty.", fg="red"), err=True)
        sys.exit(1)
    if new_pw == current:
        click.echo(
            click.style("New password is identical to the current one. Nothing changed.", fg="yellow")
        )
        return

    entry_count = len(storage.list())
    click.echo(f"Re-encrypting {entry_count} {'entry' if entry_count == 1 else 'entries'}…")

    storage.reencrypt(new_pw)

    click.echo(
        click.style(f"✓ Master password changed for project '{project}'.", fg="green")
    )


@cli.command("projects")
def list_projects() -> None:
    """List all existing projects under ~/.sspwd/."""
    root = Path.home() / ".sspwd"
    if not root.exists():
        click.echo("No projects found (vault directory does not exist yet).")
        return

    projects = [d.name for d in sorted(root.iterdir()) if d.is_dir() and (d / "vault.db").exists()]
    if not projects:
        click.echo("No projects found.")
        return

    click.echo(f"\n  Vault: {root}\n")
    for name in projects:
        size = (root / name / "vault.db").stat().st_size
        click.echo(f"  {'●'} {name:<30} ({size:,} bytes)")


@cli.command("version")
def version() -> None:
    """Print version."""
    click.echo(f"sspwd {__version__}")


def main() -> None:
    cli()