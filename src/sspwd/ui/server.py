"""
UIServer — no master password at startup.
Projects are unlocked on demand via the API.
"""

from __future__ import annotations

import threading
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .api import router as api_router

_STATIC_DIR = Path(__file__).parent / "static"


class UIServer:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7523,
        open_browser: bool = True,
    ) -> None:
        self._host = host
        self._port = port
        self._open_browser = open_browser
        self._app = self._build_app()

    def _build_app(self) -> FastAPI:
        app = FastAPI(title="sspwd", docs_url="/api/docs", redoc_url=None)

        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        app.include_router(api_router)

        if _STATIC_DIR.is_dir() and (_STATIC_DIR / "index.html").exists():
            if (_STATIC_DIR / "assets").is_dir():
                app.mount("/assets", StaticFiles(directory=_STATIC_DIR / "assets"), name="assets")

            @app.get("/{full_path:path}", include_in_schema=False)
            async def spa_fallback(full_path: str):
                return FileResponse(_STATIC_DIR / "index.html")

        return app

    def start(self, block: bool = True) -> None:
        url = f"http://{self._host}:{self._port}"

        config = uvicorn.Config(self._app, host=self._host, port=self._port, log_level="warning")
        server = uvicorn.Server(config)

        if self._open_browser:
            original_startup = server.startup

            async def _startup_and_open(sockets=None):
                await original_startup(sockets=sockets)
                threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()

            server.startup = _startup_and_open  # type: ignore[method-assign]

        print(f"sspwd UI → {url}  (Ctrl+C to quit)")

        if block:
            server.run()
        else:
            threading.Thread(target=server.run, daemon=True).start()

    @property
    def app(self) -> FastAPI:
        return self._app