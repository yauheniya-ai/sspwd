"""
REST API — mounted under /api/v1 by server.py.

Multi-project design
--------------------
The server starts with NO storage loaded.
Each project must be unlocked by POSTing its master password to
/api/v1/projects/{name}/unlock.  Unlocked storages are cached in
_sessions (memory only — never written to disk).
"""

from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from ..storage.base import PasswordEntry
from ..storage.sqlite import SQLiteStorage, project_dir

router = APIRouter(prefix="/api/v1")

# project_name → unlocked SQLiteStorage instance
_sessions: dict[str, SQLiteStorage] = {}

ALLOWED_IMAGE_TYPES = {"image/png", "image/svg+xml", "image/webp", "image/jpeg"}
MAX_ICON_BYTES = 2 * 1024 * 1024  # 2 MB


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _require(project: str) -> SQLiteStorage:
    storage = _sessions.get(project)
    if storage is None:
        raise HTTPException(
            status_code=401,
            detail=f"Project '{project}' is locked. POST /api/v1/projects/{project}/unlock first.",
        )
    return storage


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class EntryIn(BaseModel):
    title: str
    username: str
    password: str
    url: Optional[str] = None
    notes: Optional[str] = None


class EntryOut(EntryIn):
    id: int
    created_at: str
    updated_at: str
    model_config = ConfigDict(from_attributes=True)


class UnlockIn(BaseModel):
    password: str


class ProjectIn(BaseModel):
    name: str
    password: str


class IconOut(BaseModel):
    filename: str
    url: str


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


@router.get("/projects", response_model=list[str])
def list_projects():
    """All project names that exist under ~/.sspwd/"""
    root = Path.home() / ".sspwd"
    if not root.exists():
        return []
    return sorted(
        d.name for d in root.iterdir()
        if d.is_dir() and (d / "vault.db").exists()
    )


@router.get("/projects/unlocked", response_model=list[str])
def list_unlocked():
    """Projects currently unlocked in this server session."""
    return list(_sessions.keys())


@router.post("/projects/{name}/unlock", status_code=200)
def unlock_project(name: str, body: UnlockIn):
    """
    Unlock an existing project with its master password.
    The decrypted storage is cached in memory for the lifetime of the server.
    """
    vault = project_dir(name)
    if not (vault / "vault.db").exists():
        raise HTTPException(status_code=404, detail=f"Project '{name}' does not exist.")
    try:
        storage = SQLiteStorage(master_password=body.password, project=name)
        # Verify the password is correct by attempting a read
        storage.list()
        _sessions[name] = storage
    except Exception:
        raise HTTPException(status_code=401, detail="Wrong master password.")
    return {"project": name, "status": "unlocked"}


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn):
    """Create a new project (vault) with a master password."""
    name = body.name.strip()
    if not name or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="Invalid project name.")
    vault = project_dir(name)
    if (vault / "vault.db").exists():
        raise HTTPException(status_code=409, detail=f"Project '{name}' already exists.")
    storage = SQLiteStorage(master_password=body.password, project=name)
    _sessions[name] = storage
    return {"project": name, "status": "created"}


@router.delete("/projects/{name}/lock", status_code=200)
def lock_project(name: str):
    """Remove a project from the in-memory session (lock it)."""
    _sessions.pop(name, None)
    return {"project": name, "status": "locked"}


# ---------------------------------------------------------------------------
# Password entry CRUD  (all require ?project=name)
# ---------------------------------------------------------------------------


@router.get("/entries", response_model=list[EntryOut])
def list_entries(
    project: str = Query(..., description="Project name"),
    search: Optional[str] = Query(default=None),
):
    return [e.to_dict() for e in _require(project).list(search=search)]


@router.post("/entries", response_model=EntryOut, status_code=201)
def create_entry(
    body: EntryIn,
    project: str = Query(...),
):
    entry = PasswordEntry(id=None, title=body.title, username=body.username,
                          password=body.password, url=body.url, notes=body.notes)
    return _require(project).add(entry).to_dict()


@router.get("/entries/{entry_id}", response_model=EntryOut)
def get_entry(entry_id: int, project: str = Query(...)):
    entry = _require(project).get(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found.")
    return entry.to_dict()


@router.put("/entries/{entry_id}", response_model=EntryOut)
def update_entry(entry_id: int, body: EntryIn, project: str = Query(...)):
    entry = PasswordEntry(id=entry_id, title=body.title, username=body.username,
                          password=body.password, url=body.url, notes=body.notes)
    try:
        return _require(project).update(entry).to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="Entry not found.")


@router.delete("/entries/{entry_id}", status_code=204)
def delete_entry(entry_id: int, project: str = Query(...)):
    try:
        _require(project).delete(entry_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Entry not found.")


# ---------------------------------------------------------------------------
# Icons
# ---------------------------------------------------------------------------


@router.post("/icons", response_model=IconOut, status_code=201)
async def upload_icon(
    file: UploadFile = File(...),
    project: str = Query(...),
):
    storage = _require(project)
    content_type = file.content_type or ""
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported type '{content_type}'.")
    data = await file.read()
    if len(data) > MAX_ICON_BYTES:
        raise HTTPException(status_code=413, detail="Icon exceeds 2 MB.")
    ext = mimetypes.guess_extension(content_type) or ".png"
    if ext in (".jpe", ".jfif"):
        ext = ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    storage.save_icon(filename, data)
    return {"filename": filename, "url": f"/api/v1/icons/{filename}?project={project}"}


@router.get("/icons/{filename}")
def serve_icon(filename: str, project: str = Query(...)):
    storage = _require(project)
    icon_path = storage.icons_dir / filename
    if not icon_path.exists():
        raise HTTPException(status_code=404, detail="Icon not found.")
    try:
        icon_path.relative_to(storage.icons_dir)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    return FileResponse(icon_path)


@router.get("/icons", response_model=list[IconOut])
def list_icons(project: str = Query(...)):
    storage = _require(project)
    return [{"filename": n, "url": f"/api/v1/icons/{n}?project={project}"}
            for n in storage.list_icons()]


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@router.get("/health")
def health():
    return {"status": "ok"}