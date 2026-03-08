"""
Command-line interface for sspwd.

Usage
-----
    sspwd serve               # start the web UI (prompts for master password)
    sspwd add                 # add a new entry interactively
    sspwd list                # list all entries
    sspwd get  <id>           # show a single entry (password revealed)
    sspwd delete <id>         # delete an entry
    sspwd version             # print version and exit
"""

import sys
from pathlib import Path
from typing import Optional

import click

from .__version__ import __version__
from .storage.sqlite import SQLiteStorage
from .storage.base import PasswordEntry


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _get_storage(master_password: str, vault_dir: Optional[Path] = None) -> SQLiteStorage:
    return SQLiteStorage(master_password=master_password, vault_dir=vault_dir)


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
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind address.")
@click.option("--port", default=7523, show_default=True, help="TCP port.")
@click.option("--no-browser", is_flag=True, default=False, help="Do not open browser.")
@click.option("--vault-dir", default=None, type=click.Path(), help="Custom vault directory.")
def serve(host: str, port: int, no_browser: bool, vault_dir: Optional[str]) -> None:
    """Start the web UI."""
    from .ui.server import UIServer

    master = _prompt_master()
    storage = _get_storage(master, Path(vault_dir) if vault_dir else None)
    server = UIServer(
        storage=storage,
        host=host,
        port=port,
        open_browser=not no_browser,
    )
    server.start(block=True)


@cli.command("add")
@click.option("--vault-dir", default=None, type=click.Path())
def add_entry(vault_dir: Optional[str]) -> None:
    """Add a new password entry interactively."""
    master = _prompt_master()
    storage = _get_storage(master, Path(vault_dir) if vault_dir else None)

    title = click.prompt("Title")
    username = click.prompt("Username")
    password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
    url = click.prompt("URL (optional)", default="")
    notes = click.prompt("Notes (optional)", default="")

    entry = PasswordEntry(
        id=None,
        title=title,
        username=username,
        password=password,
        url=url or None,
        notes=notes or None,
    )
    created = storage.add(entry)
    click.echo(click.style(f"✓ Saved (id={created.id})", fg="green"))


@cli.command("list")
@click.option("--search", "-s", default=None, help="Filter by title / username / URL.")
@click.option("--vault-dir", default=None, type=click.Path())
def list_entries(search: Optional[str], vault_dir: Optional[str]) -> None:
    """List all stored entries."""
    master = _prompt_master()
    storage = _get_storage(master, Path(vault_dir) if vault_dir else None)

    entries = storage.list(search=search)
    if not entries:
        click.echo("No entries found.")
        return

    click.echo(f"\n{'ID':>4}  {'Title':<30}  {'Username':<25}  URL")
    click.echo("-" * 80)
    for e in entries:
        click.echo(f"{e.id:>4}  {e.title:<30}  {e.username:<25}  {e.url or ''}")


@cli.command("get")
@click.argument("entry_id", type=int)
@click.option("--vault-dir", default=None, type=click.Path())
def get_entry(entry_id: int, vault_dir: Optional[str]) -> None:
    """Show a single entry including the password."""
    master = _prompt_master()
    storage = _get_storage(master, Path(vault_dir) if vault_dir else None)

    entry = storage.get(entry_id)
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
@click.argument("entry_id", type=int)
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation.")
@click.option("--vault-dir", default=None, type=click.Path())
def delete_entry(entry_id: int, yes: bool, vault_dir: Optional[str]) -> None:
    """Delete an entry by ID."""
    master = _prompt_master()
    storage = _get_storage(master, Path(vault_dir) if vault_dir else None)

    if not yes:
        click.confirm(f"Delete entry {entry_id}?", abort=True)

    try:
        storage.delete(entry_id)
        click.echo(click.style(f"✓ Deleted entry {entry_id}.", fg="green"))
    except KeyError:
        click.echo(click.style(f"Entry {entry_id} not found.", fg="red"), err=True)
        sys.exit(1)


@cli.command("version")
def version() -> None:
    """Print version."""
    click.echo(f"sspwd {__version__}")


def main() -> None:
    cli()