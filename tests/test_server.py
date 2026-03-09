"""Tests for UIServer — targets server.py lines 84 and 102-132."""

import time
import threading
from pathlib import Path

import pytest
import httpx

from sspwd.storage.sqlite import SQLiteStorage
from sspwd.ui.server import UIServer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _storage(tmp_path: Path) -> SQLiteStorage:
    return SQLiteStorage(master_password="pw", vault_dir=tmp_path)


# ---------------------------------------------------------------------------
# App construction (line 84 — static dir branch)
# ---------------------------------------------------------------------------


class TestBuildApp:
    def test_app_created(self, tmp_path: Path) -> None:
        server = UIServer(storage=_storage(tmp_path), open_browser=False)
        assert server.app is not None

    def test_app_exposed_via_property(self, tmp_path: Path) -> None:
        from fastapi import FastAPI
        server = UIServer(storage=_storage(tmp_path), open_browser=False)
        assert isinstance(server.app, FastAPI)

    def test_static_dir_missing_no_crash(self, tmp_path: Path) -> None:
        """Server builds fine even if ui/static/ has no index.html (line 84 branch not taken)."""
        server = UIServer(storage=_storage(tmp_path), open_browser=False)
        # reaching here without exception is sufficient
        assert server.app is not None

    def test_static_dir_with_index_mounts(self, tmp_path: Path, monkeypatch) -> None:
        """Simulate a built frontend: create fake static/index.html so the mount branch runs."""
        from sspwd.ui import server as server_module

        fake_static = tmp_path / "fake_static"
        fake_static.mkdir()
        (fake_static / "index.html").write_text("<html>ok</html>")
        assets = fake_static / "assets"
        assets.mkdir()

        monkeypatch.setattr(server_module, "_STATIC_DIR", fake_static)

        srv = UIServer(storage=_storage(tmp_path), open_browser=False)
        from fastapi.testclient import TestClient
        client = TestClient(srv.app)

        # SPA fallback should return the fake index.html
        r = client.get("/some/deep/route")
        assert r.status_code == 200
        assert "ok" in r.text


# ---------------------------------------------------------------------------
# start() non-blocking (lines 102-132)
# ---------------------------------------------------------------------------


class TestStart:
    def test_start_non_blocking_serves_health(self, tmp_path: Path) -> None:
        """start(block=False) launches a background thread; health endpoint responds."""
        port = 17523  # unlikely to be in use
        server = UIServer(
            storage=_storage(tmp_path),
            host="127.0.0.1",
            port=port,
            open_browser=False,
        )
        server.start(block=False)

        # Give uvicorn a moment to bind
        deadline = time.time() + 5.0
        last_exc: Exception = RuntimeError("server never started")
        while time.time() < deadline:
            try:
                r = httpx.get(f"http://127.0.0.1:{port}/api/v1/health", timeout=1.0)
                assert r.status_code == 200
                assert r.json()["status"] == "ok"
                return          # success
            except Exception as exc:
                last_exc = exc
                time.sleep(0.15)

        raise last_exc

    def test_start_non_blocking_does_not_block_caller(self, tmp_path: Path) -> None:
        """Verify start(block=False) returns quickly (< 3 s)."""
        port = 17524
        server = UIServer(
            storage=_storage(tmp_path),
            host="127.0.0.1",
            port=port,
            open_browser=False,
        )
        t0 = time.time()
        server.start(block=False)
        elapsed = time.time() - t0
        assert elapsed < 3.0, f"start(block=False) took {elapsed:.1f}s — expected non-blocking"

    def test_open_browser_false_does_not_call_webbrowser(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """open_browser=False must never call webbrowser.open."""
        port = 17525
        called = []
        monkeypatch.setattr("webbrowser.open", lambda url: called.append(url))

        server = UIServer(
            storage=_storage(tmp_path),
            host="127.0.0.1",
            port=port,
            open_browser=False,
        )
        server.start(block=False)
        time.sleep(0.5)          # give the startup hook time to fire

        assert called == [], f"webbrowser.open was called with: {called}"