"""CLI tests using Typer's CliRunner — targets cli.py from 0% → ~85% coverage.

`serve` is excluded because it starts a blocking uvicorn server;
that path is covered indirectly by test_api.py via UIServer.
"""

from pathlib import Path
from unittest.mock import patch
from typer.testing import CliRunner

from sspwd.cli import app, main
from sspwd.storage.sqlite import SQLiteStorage
from sspwd.storage.base import PasswordEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed(vault_dir: Path, master: str = "pw") -> PasswordEntry:
    """Create a vault with a single entry and return it."""
    storage = SQLiteStorage(master_password=master, vault_dir=vault_dir)
    return storage.add(
        PasswordEntry(
            id=None,
            title="GitHub",
            username="alice",
            password="s3cr3t",
            url="https://github.com",
            notes="work account",
        )
    )


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


def test_version() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "sspwd" in result.output
    assert result.output.strip() != ""  # version string present, not pinned


def test_version_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--version"])
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
        result = runner.invoke(
            app, ["list", "--vault-dir", str(tmp_path)], input="pw\n"
        )
        assert result.exit_code == 0
        assert "No entries found" in result.output

    def test_lists_entry(self, tmp_path: Path) -> None:
        _seed(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            app, ["list", "--vault-dir", str(tmp_path)], input="pw\n"
        )
        assert result.exit_code == 0
        assert "GitHub" in result.output
        assert "alice" in result.output

    def test_search_flag_match(self, tmp_path: Path) -> None:
        _seed(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["list", "--vault-dir", str(tmp_path), "--search", "GitHub"],
            input="pw\n",
        )
        assert "GitHub" in result.output

    def test_search_flag_no_match(self, tmp_path: Path) -> None:
        _seed(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["list", "--vault-dir", str(tmp_path), "--search", "zzznomatch"],
            input="pw\n",
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
        result = runner.invoke(app, ["add", "--vault-dir", str(tmp_path)], input=inputs)
        assert result.exit_code == 0
        assert "Saved" in result.output

    def test_add_persists_to_storage(self, tmp_path: Path) -> None:
        SQLiteStorage(master_password="pw", vault_dir=tmp_path)
        runner = CliRunner()
        # prompt order: master pw, title, category, username, password (×2), url, notes
        inputs = "pw\nFigma\nDesign\ncarol@example.com\nsecretpw\nsecretpw\n\n\n"
        runner.invoke(app, ["add", "--vault-dir", str(tmp_path)], input=inputs)

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
        result = runner.invoke(
            app, ["get", str(entry.id), "--vault-dir", str(tmp_path)], input="pw\n"
        )
        assert result.exit_code == 0
        assert "GitHub" in result.output
        assert "alice" in result.output
        assert "s3cr3t" in result.output
        assert "https://github.com" in result.output
        assert "work account" in result.output

    def test_get_not_found_exits_1(self, tmp_path: Path) -> None:
        SQLiteStorage(master_password="pw", vault_dir=tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            app, ["get", "99999", "--vault-dir", str(tmp_path)], input="pw\n"
        )
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
            app,
            ["delete", str(entry.id), "--yes", "--vault-dir", str(tmp_path)],
            input="pw\n",
        )
        assert result.exit_code == 0
        assert "Deleted" in result.output

    def test_delete_with_confirmation(self, tmp_path: Path) -> None:
        entry = _seed(tmp_path)
        runner = CliRunner()
        # inputs: master password, then "y" to confirm
        result = runner.invoke(
            app,
            ["delete", str(entry.id), "--vault-dir", str(tmp_path)],
            input="pw\ny\n",
        )
        assert result.exit_code == 0
        assert "Deleted" in result.output

    def test_delete_abort_on_no(self, tmp_path: Path) -> None:
        entry = _seed(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["delete", str(entry.id), "--vault-dir", str(tmp_path)],
            input="pw\nn\n",
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
            app,
            ["delete", "99999", "--yes", "--vault-dir", str(tmp_path)],
            input="pw\n",
        )
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_delete_removes_entry(self, tmp_path: Path) -> None:
        entry = _seed(tmp_path)
        runner = CliRunner()
        runner.invoke(
            app,
            ["delete", str(entry.id), "--yes", "--vault-dir", str(tmp_path)],
            input="pw\n",
        )
        storage = SQLiteStorage(master_password="pw", vault_dir=tmp_path)
        assert storage.get(entry.id) is None


# ---------------------------------------------------------------------------
# no-subcommand (banner)
# ---------------------------------------------------------------------------


def test_no_subcommand_shows_banner() -> None:
    runner = CliRunner()
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "sspwd" in result.output


# ---------------------------------------------------------------------------
# change-password
# ---------------------------------------------------------------------------


class TestChangePasswordCommand:
    def test_change_password_success(self, tmp_path: Path) -> None:
        _seed(tmp_path, master="oldpw")
        runner = CliRunner()
        # prompts: current pw, new pw, confirm new pw
        result = runner.invoke(
            app,
            ["change-password", "--vault-dir", str(tmp_path)],
            input="oldpw\nnewpw\nnewpw\n",
        )
        assert result.exit_code == 0
        assert "changed" in result.output.lower()
        # verify vault is accessible with new password
        storage = SQLiteStorage(master_password="newpw", vault_dir=tmp_path)
        assert len(storage.list()) == 1

    def test_change_password_wrong_current(self, tmp_path: Path) -> None:
        _seed(tmp_path, master="correct")
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["change-password", "--vault-dir", str(tmp_path)],
            input="WRONG\nnewpw\nnewpw\n",
        )
        assert result.exit_code != 0
        assert "wrong" in result.output.lower() or "wrong" in (result.stderr or "").lower()

    def test_change_password_same_as_current(self, tmp_path: Path) -> None:
        _seed(tmp_path, master="pw")
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["change-password", "--vault-dir", str(tmp_path)],
            input="pw\npw\npw\n",
        )
        assert result.exit_code == 0
        assert "identical" in result.output.lower() or "nothing changed" in result.output.lower()

    def test_change_password_empty_new(self, tmp_path: Path) -> None:
        _seed(tmp_path, master="pw")
        runner = CliRunner()
        # empty string for new password and its confirmation
        result = runner.invoke(
            app,
            ["change-password", "--vault-dir", str(tmp_path)],
            input="pw\n\n\n",
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# list_projects
# ---------------------------------------------------------------------------


class TestProjectsCommand:
    def test_no_sspwd_dir(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with patch("sspwd.cli.Path") as mock_path_cls:
            # Make Path.home() / ".sspwd" point to a non-existent directory
            fake_root = tmp_path / "nonexistent"
            mock_path_cls.home.return_value = tmp_path
            mock_path_cls.return_value.__truediv__ = lambda s, o: fake_root
            result = runner.invoke(app, ["projects"])
        assert result.exit_code == 0

    def test_no_projects_in_dir(self, tmp_path: Path) -> None:
        # sspwd dir exists but contains no vault.db files
        sspwd_dir = tmp_path / ".sspwd"
        sspwd_dir.mkdir()
        runner = CliRunner()
        with patch("sspwd.cli.Path") as mock_path_cls:
            from pathlib import Path as RealPath
            mock_path_cls.home.return_value.__truediv__ = lambda s, o: sspwd_dir
            # Rebuild the /".sspwd" path
            import sspwd.cli as cli_mod
            with patch.object(cli_mod, "Path", wraps=RealPath) as wp:
                wp.home.return_value = tmp_path
                result = runner.invoke(app, ["projects"])
        assert result.exit_code == 0

    def test_lists_projects(self, tmp_path: Path) -> None:
        # Create a fake project with a vault.db
        fake_project = tmp_path / ".sspwd" / "myproject"
        fake_project.mkdir(parents=True)
        (fake_project / "vault.db").write_bytes(b"x" * 100)
        import sspwd.cli as cli_mod
        from pathlib import Path as RealPath
        runner = CliRunner()
        with patch.object(cli_mod, "Path", wraps=RealPath) as wp:
            wp.home.return_value = tmp_path
            result = runner.invoke(app, ["projects"])
        assert result.exit_code == 0
        assert "myproject" in result.output


# ---------------------------------------------------------------------------
# main() entry point
# ---------------------------------------------------------------------------


def test_main_entry_point() -> None:
    with patch("sspwd.cli.app") as mock_app:
        main()
        mock_app.assert_called_once()
