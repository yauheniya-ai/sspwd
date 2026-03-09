"""Tests for UIServer — server.py coverage."""

import time
from pathlib import Path

import pytest
import httpx

from sspwd.ui.server import UIServer


# ---------------------------------------------------------------------------
# App construction
# ---------------------------------------------------------------------------


class TestBuildApp:
    def test_app_created(self) -> None:
        server = UIServer(open_browser=False)
        assert server.app is not None

    def test_app_exposed_via_property(self) -> None:
        from fastapi import FastAPI
        server = UIServer(open_browser=False)
        assert isinstance(server.app, FastAPI)

    def test_static_dir_missing_no_crash(self) -> None:
        """Server builds fine even if ui/static/ has no index.html."""
        server = UIServer(open_browser=False)
        assert server.app is not None

    def test_static_dir_with_index_mounts(self, tmp_path: Path, monkeypatch) -> None:
        """Simulate a built frontend: fake static/index.html triggers the SPA mount."""
        from sspwd.ui import server as server_module
        from fastapi.testclient import TestClient

        fake_static = tmp_path / "fake_static"
        fake_static.mkdir()
        (fake_static / "index.html").write_text("<html>ok</html>")
        (fake_static / "assets").mkdir()

        monkeypatch.setattr(server_module, "_STATIC_DIR", fake_static)

        srv = UIServer(open_browser=False)
        client = TestClient(srv.app)

        r = client.get("/some/deep/route")
        assert r.status_code == 200
        assert "ok" in r.text


# ---------------------------------------------------------------------------
# start() non-blocking
# ---------------------------------------------------------------------------


class TestStart:
    def test_start_non_blocking_serves_health(self) -> None:
        port = 17523
        server = UIServer(host="127.0.0.1", port=port, open_browser=False)
        server.start(block=False)

        deadline = time.time() + 5.0
        last_exc: Exception = RuntimeError("server never started")
        while time.time() < deadline:
            try:
                r = httpx.get(f"http://127.0.0.1:{port}/api/v1/health", timeout=1.0)
                assert r.status_code == 200
                assert r.json()["status"] == "ok"
                return
            except Exception as exc:
                last_exc = exc
                time.sleep(0.15)
        raise last_exc

    def test_start_non_blocking_does_not_block_caller(self) -> None:
        port = 17524
        server = UIServer(host="127.0.0.1", port=port, open_browser=False)
        t0 = time.time()
        server.start(block=False)
        elapsed = time.time() - t0
        assert elapsed < 3.0, f"start(block=False) took {elapsed:.1f}s"

    def test_open_browser_false_does_not_call_webbrowser(self, monkeypatch) -> None:
        port = 17525
        called = []
        monkeypatch.setattr("webbrowser.open", lambda url: called.append(url))

        server = UIServer(host="127.0.0.1", port=port, open_browser=False)
        server.start(block=False)
        time.sleep(0.5)

        assert called == [], f"webbrowser.open was called with: {called}"