"""CLI tests using Click's CliRunner — targets cli.py from 0% → ~85% coverage.

`serve` is excluded because it starts a blocking uvicorn server;
that path is covered indirectly by test_api.py via UIServer.
"""

import pytest
from pathlib import Path
from click.testing import CliRunner

from sspwd.cli import cli
from sspwd.storage.sqlite import SQLiteStorage
from sspwd.storage.base import PasswordEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed(vault_dir: Path, master: str = "pw") -> PasswordEntry:
    """Create a vault with a single entry and return it."""
    storage = SQLiteStorage(master_password=master, vault_dir=vault_dir)
    return storage.add(PasswordEntry(
        id=None, title="GitHub", username="alice", password="s3cr3t",
        url="https://github.com", notes="work account",
    ))


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


def test_version() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["version"])
    assert result.exit_code == 0
    assert "sspwd" in result.output
    assert result.output.strip() != ""  # version string present, not pinned


def test_version_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    # just check it contains a semver-like pattern, not a hardcoded string
    import re
    assert re.search(r"\d+\.\d+\.\d+", result.output)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


class TestListCommand:
    def test_empty_vault(self, tmp_path: Path) -> None:
        # initialise the vault so the salt exists, but add no entries
        SQLiteStorage(master_password="pw", vault_dir=tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["list", "--vault-dir", str(tmp_path)], input="pw\n")
        assert result.exit_code == 0
        assert "No entries found" in result.output

    def test_lists_entry(self, tmp_path: Path) -> None:
        _seed(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["list", "--vault-dir", str(tmp_path)], input="pw\n")
        assert result.exit_code == 0
        assert "GitHub" in result.output
        assert "alice" in result.output

    def test_search_flag_match(self, tmp_path: Path) -> None:
        _seed(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cli, ["list", "--vault-dir", str(tmp_path), "--search", "GitHub"], input="pw\n"
        )
        assert "GitHub" in result.output

    def test_search_flag_no_match(self, tmp_path: Path) -> None:
        _seed(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cli, ["list", "--vault-dir", str(tmp_path), "--search", "zzznomatch"], input="pw\n"
        )
        assert "No entries found" in result.output


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


class TestAddCommand:
    def test_add_entry(self, tmp_path: Path) -> None:
        SQLiteStorage(master_password="pw", vault_dir=tmp_path)  # init salt
        runner = CliRunner()
        # prompt order: master pw, title, category, username, password (×2), url, notes
        inputs = "pw\nNotion\nSoftware\nbob@example.com\nmypassword\nmypassword\nhttps://notion.so\n\n"
        result = runner.invoke(cli, ["add", "--vault-dir", str(tmp_path)], input=inputs)
        assert result.exit_code == 0
        assert "Saved" in result.output

    def test_add_persists_to_storage(self, tmp_path: Path) -> None:
        SQLiteStorage(master_password="pw", vault_dir=tmp_path)
        runner = CliRunner()
        # prompt order: master pw, title, category, username, password (×2), url, notes
        inputs = "pw\nFigma\nDesign\ncarol@example.com\nsecretpw\nsecretpw\n\n\n"
        runner.invoke(cli, ["add", "--vault-dir", str(tmp_path)], input=inputs)

        storage = SQLiteStorage(master_password="pw", vault_dir=tmp_path)
        entries = storage.list()
        assert any(e.title == "Figma" for e in entries)


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


class TestGetCommand:
    def test_get_existing_entry(self, tmp_path: Path) -> None:
        entry = _seed(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["get", str(entry.id), "--vault-dir", str(tmp_path)], input="pw\n")
        assert result.exit_code == 0
        assert "GitHub" in result.output
        assert "alice" in result.output
        assert "s3cr3t" in result.output
        assert "https://github.com" in result.output
        assert "work account" in result.output

    def test_get_not_found_exits_1(self, tmp_path: Path) -> None:
        SQLiteStorage(master_password="pw", vault_dir=tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["get", "99999", "--vault-dir", str(tmp_path)], input="pw\n")
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


class TestDeleteCommand:
    def test_delete_with_yes_flag(self, tmp_path: Path) -> None:
        entry = _seed(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cli, ["delete", str(entry.id), "--yes", "--vault-dir", str(tmp_path)], input="pw\n"
        )
        assert result.exit_code == 0
        assert "Deleted" in result.output

    def test_delete_with_confirmation(self, tmp_path: Path) -> None:
        entry = _seed(tmp_path)
        runner = CliRunner()
        # inputs: master password, then "y" to confirm
        result = runner.invoke(
            cli, ["delete", str(entry.id), "--vault-dir", str(tmp_path)], input="pw\ny\n"
        )
        assert result.exit_code == 0
        assert "Deleted" in result.output

    def test_delete_abort_on_no(self, tmp_path: Path) -> None:
        entry = _seed(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cli, ["delete", str(entry.id), "--vault-dir", str(tmp_path)], input="pw\nn\n"
        )
        # Click raises Abort on "n", which exits non-zero
        assert result.exit_code != 0
        # Entry must still exist
        storage = SQLiteStorage(master_password="pw", vault_dir=tmp_path)
        assert storage.get(entry.id) is not None

    def test_delete_not_found_exits_1(self, tmp_path: Path) -> None:
        SQLiteStorage(master_password="pw", vault_dir=tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            cli, ["delete", "99999", "--yes", "--vault-dir", str(tmp_path)], input="pw\n"
        )
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_delete_removes_entry(self, tmp_path: Path) -> None:
        entry = _seed(tmp_path)
        runner = CliRunner()
        runner.invoke(
            cli, ["delete", str(entry.id), "--yes", "--vault-dir", str(tmp_path)], input="pw\n"
        )
        storage = SQLiteStorage(master_password="pw", vault_dir=tmp_path)
        assert storage.get(entry.id) is None