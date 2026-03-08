"""
UIServer — wraps a FastAPI application that:
  1. Serves the bundled React/Vite SPA from ui/static/
  2. Exposes the REST API under /api/v1/
  3. Opens the user's default browser automatically (optional)
"""

import threading
import webbrowser
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .api import router as api_router, set_storage
from ..storage.sqlite import SQLiteStorage

_STATIC_DIR = Path(__file__).parent / "static"


class UIServer:
    """
    Manages the lifecycle of the embedded web server.

    Parameters
    ----------
    storage:
        An initialised SQLiteStorage instance.
    host:
        Bind address (default ``127.0.0.1``).
    port:
        TCP port (default ``7523``).
    open_browser:
        Whether to open the UI in the default browser on start.
    """

    def __init__(
        self,
        storage: SQLiteStorage,
        host: str = "127.0.0.1",
        port: int = 7523,
        open_browser: bool = True,
    ) -> None:
        self._storage = storage
        self._host = host
        self._port = port
        self._open_browser = open_browser
        self._app = self._build_app()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_app(self) -> FastAPI:
        app = FastAPI(title="sspwd", docs_url=None, redoc_url=None)

        # Allow the Vite dev-server to call the API during development.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Wire storage into the API module.
        set_storage(self._storage)
        app.include_router(api_router)

        # Serve static build if it exists.
        if _STATIC_DIR.is_dir() and ((_STATIC_DIR / "index.html").exists()):
            app.mount(
                "/assets",
                StaticFiles(directory=_STATIC_DIR / "assets"),
                name="assets",
            )

            @app.get("/{full_path:path}", include_in_schema=False)
            async def spa_fallback(full_path: str):  # noqa: ANN202
                """Catch-all: return index.html so React Router handles routing."""
                return FileResponse(_STATIC_DIR / "index.html")

        return app

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start(self, block: bool = True) -> None:
        """
        Start the server.

        Parameters
        ----------
        block:
            If True (default) the call blocks until the server is stopped.
            Pass False to run in a background thread (useful for testing).
        """
        url = f"http://{self._host}:{self._port}"

        config = uvicorn.Config(
            self._app,
            host=self._host,
            port=self._port,
            log_level="warning",
        )
        server = uvicorn.Server(config)

        # Hook into uvicorn's startup so the browser only opens once the
        # server is actually listening — avoids the race condition that
        # caused the browser to open even when open_browser=False.
        if self._open_browser:
            original_startup = server.startup

            async def _startup_and_open(sockets=None):
                await original_startup(sockets=sockets)
                threading.Thread(
                    target=webbrowser.open, args=(url,), daemon=True
                ).start()

            server.startup = _startup_and_open  # type: ignore[method-assign]

        print(f"sspwd UI → {url}  (Ctrl+C to quit)")

        if block:
            server.run()
        else:
            thread = threading.Thread(target=server.run, daemon=True)
            thread.start()

    @property
    def app(self) -> FastAPI:
        """Expose the raw FastAPI app (e.g. for ASGI testing)."""
        return self._app