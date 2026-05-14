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

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

from .__version__ import __version__
from .storage.sqlite import SQLiteStorage, _DEFAULT_PROJECT
from .storage.base import PasswordEntry

console = Console()
err_console = Console(stderr=True)

app = typer.Typer(
    name="sspwd",
    help="sspwd — a local, encrypted password manager.",
    add_completion=False,
    invoke_without_command=True,
)

_ASCII = """
                                               ▄▄ 
                                               ██ 
 ▄▄█████▄  ▄▄█████▄  ██▄███▄  ██      ██  ▄███▄██ 
 ██▄▄▄▄ ▀  ██▄▄▄▄ ▀  ██▀  ▀██ ▀█  ██  █▀ ██▀  ▀██ 
  ▀▀▀▀██▄   ▀▀▀▀██▄  ██    ██  ██▄██▄██  ██    ██ 
 █▄▄▄▄▄██  █▄▄▄▄▄██  ███▄▄██▀  ▀██  ██▀  ▀██▄▄███ 
  ▀▀▀▀▀▀    ▀▀▀▀▀▀   ██ ▀▀▀     ▀▀  ▀▀     ▀▀▀ ▀▀ 
                     ██                           
"""


@app.callback()
def _main(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option("--version", "-v", help="Print version and exit.", is_eager=True),
    ] = False,
) -> None:
    if version:
        console.print(f"sspwd {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        console.print(_ASCII, style="bold purple")
        console.print(
            f"  sspwd [bold]{__version__}[/bold] — a local, encrypted password manager.\n"
        )
        console.print("  Run [bold]sspwd --help[/bold] to see available commands.")


def _get_storage(
    master: str, project: str, vault_dir: Optional[Path] = None
) -> SQLiteStorage:
    return SQLiteStorage(master_password=master, project=project, vault_dir=vault_dir)


def _prompt_master() -> str:
    return typer.prompt("Master password", hide_input=True)


_ProjectArg = Annotated[
    str,
    typer.Option(
        "--project", "-p", help="Project / workspace name (subdirectory of ~/.sspwd/)."
    ),
]
_VaultDirArg = Annotated[
    Optional[Path], typer.Option("--vault-dir", help="Override vault directory.")
]


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", show_default=True),
    port: int = typer.Option(7523, show_default=True),
    no_browser: bool = typer.Option(False, "--no-browser"),
) -> None:
    """Start the web UI. Projects are unlocked on demand in the browser."""
    from .ui.server import UIServer

    server = UIServer(host=host, port=port, open_browser=not no_browser)
    server.start(block=True)


@app.command("add")
def add_entry(
    project: _ProjectArg = _DEFAULT_PROJECT,
    vault_dir: _VaultDirArg = None,
) -> None:
    """Add a new password entry interactively."""
    master = _prompt_master()
    storage = _get_storage(master, project, vault_dir)

    title = typer.prompt("Title")
    category = typer.prompt("Category (optional)", default="Other")
    username = typer.prompt("Username")
    password = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
    url = typer.prompt("URL (optional)", default="")
    notes = typer.prompt("Notes (optional)", default="")

    entry = PasswordEntry(
        id=None,
        title=title,
        category=category or "Other",
        username=username,
        password=password,
        url=url or None,
        notes=notes or None,
    )
    created = storage.add(entry)
    console.print(
        f"[green]✓ Saved '{title}' (id={created.id}) in project '{project}'[/green]"
    )


@app.command("list")
def list_entries(
    project: _ProjectArg = _DEFAULT_PROJECT,
    search: Annotated[
        Optional[str],
        typer.Option("--search", "-s", help="Filter by title / username / URL."),
    ] = None,
    vault_dir: _VaultDirArg = None,
) -> None:
    """List all stored entries for a project."""
    master = _prompt_master()
    storage = _get_storage(master, project, vault_dir)

    entries = storage.list(search=search)
    if not entries:
        console.print("No entries found.")
        return

    table = Table(title=f"Project: {project}", show_lines=False)
    table.add_column("ID", justify="right", style="dim")
    table.add_column("Title")
    table.add_column("Username")
    table.add_column("URL", style="dim")
    for e in entries:
        table.add_row(str(e.id), e.title, e.username, e.url or "")
    console.print(table)


@app.command("get")
def get_entry(
    entry_id: Annotated[int, typer.Argument(help="Entry ID to retrieve.")],
    project: _ProjectArg = _DEFAULT_PROJECT,
    vault_dir: _VaultDirArg = None,
) -> None:
    """Show a single entry (reveals password)."""
    master = _prompt_master()
    storage = _get_storage(master, project, vault_dir)
    entry = storage.get(entry_id)

    if entry is None:
        err_console.print(f"[red]Entry {entry_id} not found.[/red]")
        raise typer.Exit(1)

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("Title", entry.title)
    table.add_row("Username", entry.username)
    table.add_row("Password", entry.password)
    table.add_row("URL", entry.url or "-")
    table.add_row("Notes", entry.notes or "-")
    table.add_row("Updated", str(entry.updated_at))
    console.print(table)


@app.command("delete")
def delete_entry(
    entry_id: Annotated[int, typer.Argument(help="Entry ID to delete.")],
    project: _ProjectArg = _DEFAULT_PROJECT,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Skip confirmation prompt.")
    ] = False,
    vault_dir: _VaultDirArg = None,
) -> None:
    """Delete an entry by ID."""
    master = _prompt_master()
    storage = _get_storage(master, project, vault_dir)

    if not yes:
        typer.confirm(f"Delete entry {entry_id} from project '{project}'?", abort=True)

    try:
        storage.delete(entry_id)
        console.print(f"[green]✓ Deleted entry {entry_id}.[/green]")
    except KeyError:
        err_console.print(f"[red]Entry {entry_id} not found.[/red]")
        raise typer.Exit(1)


@app.command("change-password")
def change_password(
    project: _ProjectArg = _DEFAULT_PROJECT,
    vault_dir: _VaultDirArg = None,
) -> None:
    """Change the master password for a project vault (re-encrypts the vault)."""
    console.print("[yellow]⚠  This will re-encrypt the entire vault.[/yellow]")

    current = typer.prompt("Current master password", hide_input=True)
    try:
        storage = _get_storage(current, project, vault_dir)
    except Exception:
        err_console.print("[red]✗ Wrong master password.[/red]")
        raise typer.Exit(1)

    new_pw = typer.prompt(
        "New master password",
        hide_input=True,
        confirmation_prompt="Confirm new master password",
    )
    if not new_pw:
        err_console.print("[red]✗ New password must not be empty.[/red]")
        raise typer.Exit(1)
    if new_pw == current:
        console.print(
            "[yellow]New password is identical to the current one. Nothing changed.[/yellow]"
        )
        return

    entry_count = len(storage.list())
    console.print(
        f"Re-encrypting {entry_count} {'entry' if entry_count == 1 else 'entries'}…"
    )

    storage.reencrypt(new_pw)
    console.print(f"[green]✓ Master password changed for project '{project}'.[/green]")


@app.command("projects")
def list_projects() -> None:
    """List all existing projects under ~/.sspwd/."""
    root = Path.home() / ".sspwd"
    if not root.exists():
        console.print("No projects found (vault directory does not exist yet).")
        return

    projects = [
        d.name
        for d in sorted(root.iterdir())
        if d.is_dir() and (d / "vault.db").exists()
    ]
    if not projects:
        console.print("No projects found.")
        return

    table = Table(title=f"Vault: {root}", show_header=False, box=None, padding=(0, 1))
    table.add_column("Icon", style="green")
    table.add_column("Name", style="bold")
    table.add_column("Size", justify="right", style="dim")
    for name in projects:
        size = (root / name / "vault.db").stat().st_size
        table.add_row("●", name, f"{size:,} bytes")
    console.print(table)


@app.command("version")
def version() -> None:
    """Print version."""
    console.print(f"sspwd {__version__}")


def main() -> None:
    app()
