"""
REST API — mounted under /api/v1 by server.py.

All field names use camelCase in JSON to match the TypeScript frontend.
"""
from __future__ import annotations

import mimetypes
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from ..storage.base import Company, CompanyAddress, IconCatalogueEntry, PasswordEntry
from ..storage.sqlite import SQLiteStorage, project_dir

router = APIRouter(prefix="/api/v1")

_sessions: dict[str, SQLiteStorage] = {}

ALLOWED_IMAGE_TYPES = {"image/png", "image/svg+xml", "image/webp", "image/jpeg"}
MAX_ICON_BYTES = 2 * 1024 * 1024


def set_storage(storage: SQLiteStorage) -> None:
    _sessions["default"] = storage


def _require(project: str) -> SQLiteStorage:
    s = _sessions.get(project)
    if s is None:
        raise HTTPException(
            status_code=401,
            detail=f"Project '{project}' is locked. POST /api/v1/projects/{project}/unlock first.",
        )
    return s


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class AddressSchema(BaseModel):
    street:      Optional[str] = None
    city:        Optional[str] = None
    state:       Optional[str] = None
    postcode:    Optional[str] = None
    country:     str           = ""
    countryCode: str           = ""


class CompanyIn(BaseModel):
    name:    str
    icon:    Optional[dict] = None          # {type, value}
    address: Optional[AddressSchema] = None
    revenue: Optional[float] = None


class CompanyOut(CompanyIn):
    id: int
    model_config = ConfigDict(from_attributes=True)


class EntryIn(BaseModel):
    title:          str
    username:       Optional[str]       = None
    email:          Optional[str]       = None
    password:       Optional[str]       = None
    url:            Optional[str]       = None
    notes:          Optional[str]       = None
    icon:           Optional[dict]      = None          # {type, value}
    category:       str                 = "Other"
    service_type:   str                 = "free"        # "free" | "paid"
    tags:           list[str]           = []
    login_methods:  list[str]           = []
    company_id:     Optional[int]       = None
    user_created_at: Optional[str]      = None   # ISO string


class EntryOut(EntryIn):
    id:         int
    created_at: str
    updated_at: str
    model_config = ConfigDict(from_attributes=True)


class UnlockIn(BaseModel):
    password: str


class ProjectIn(BaseModel):
    name:     str
    password: str


class IconOut(BaseModel):
    filename: str
    url:      str


class IconCatalogueIn(BaseModel):
    type:  str
    value: str
    label: Optional[str] = None


class IconCatalogueOut(BaseModel):
    id:         int
    type:       str
    value:      str
    label:      Optional[str] = None
    created_at: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


# ── helpers ────────────────────────────────────────────────────────────────────

def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _entry_in_to_obj(body: EntryIn) -> PasswordEntry:
    return PasswordEntry(
        id              = None,
        title           = body.title,
        username        = body.username,
        email           = body.email,
        password        = body.password,
        url             = body.url,
        notes           = body.notes,
        icon            = body.icon,
        category        = body.category or "Other",
        service_type    = body.service_type or "free",
        tags            = body.tags or [],
        login_methods   = body.login_methods or [],
        company_id      = body.company_id,
        user_created_at = _parse_dt(body.user_created_at),
    )


def _company_in_to_obj(body: CompanyIn, company_id: Optional[int] = None) -> Company:
    addr = None
    if body.address and body.address.country:
        addr = CompanyAddress(
            country      = body.address.country,
            country_code = body.address.countryCode,
            street       = body.address.street,
            city         = body.address.city,
            state        = body.address.state,
            postcode     = body.address.postcode,
        )
    return Company(
        id      = company_id,
        name    = body.name,
        icon    = body.icon,
        address = addr,
        revenue = body.revenue,
    )


# ── projects ──────────────────────────────────────────────────────────────────

@router.get("/projects", response_model=list[str])
def list_projects():
    root = Path.home() / ".sspwd"
    if not root.exists():
        return []
    return sorted(
        d.name for d in root.iterdir()
        if d.is_dir() and (d / "vault.db").exists()
    )


@router.get("/projects/unlocked", response_model=list[str])
def list_unlocked():
    return list(_sessions.keys())


@router.post("/projects/{name}/unlock", status_code=200)
def unlock_project(name: str, body: UnlockIn):
    vault = project_dir(name)
    if not (vault / "vault.db").exists():
        raise HTTPException(status_code=404, detail=f"Project '{name}' does not exist.")
    try:
        storage = SQLiteStorage(master_password=body.password, project=name)
        _sessions[name] = storage
    except Exception:
        raise HTTPException(status_code=401, detail="Wrong master password.")
    return {"project": name, "status": "unlocked"}


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn):
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
    _sessions.pop(name, None)
    return {"project": name, "status": "locked"}


# ── entries ────────────────────────────────────────────────────────────────────

@router.get("/entries", response_model=list[EntryOut])
def list_entries(project: str = Query(...), search: Optional[str] = Query(default=None)):
    return [e.to_dict() for e in _require(project).list(search=search)]


@router.post("/entries", response_model=EntryOut, status_code=201)
def create_entry(body: EntryIn, project: str = Query(...)):
    return _require(project).add(_entry_in_to_obj(body)).to_dict()


@router.get("/entries/{entry_id}", response_model=EntryOut)
def get_entry(entry_id: int, project: str = Query(...)):
    entry = _require(project).get(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found.")
    return entry.to_dict()


@router.put("/entries/{entry_id}", response_model=EntryOut)
def update_entry(entry_id: int, body: EntryIn, project: str = Query(...)):
    obj    = _entry_in_to_obj(body)
    obj.id = entry_id
    try:
        return _require(project).update(obj).to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="Entry not found.")


@router.delete("/entries/{entry_id}", status_code=204)
def delete_entry(entry_id: int, project: str = Query(...)):
    try:
        _require(project).delete(entry_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Entry not found.")


# ── companies ──────────────────────────────────────────────────────────────────

@router.get("/companies", response_model=list[CompanyOut])
def list_companies(project: str = Query(...)):
    return [c.to_dict() for c in _require(project).list_companies()]


@router.post("/companies", response_model=CompanyOut, status_code=201)
def create_company(body: CompanyIn, project: str = Query(...)):
    return _require(project).add_company(_company_in_to_obj(body)).to_dict()


@router.get("/companies/{company_id}", response_model=CompanyOut)
def get_company(company_id: int, project: str = Query(...)):
    c = _require(project).get_company(company_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Company not found.")
    return c.to_dict()


@router.put("/companies/{company_id}", response_model=CompanyOut)
def update_company(company_id: int, body: CompanyIn, project: str = Query(...)):
    try:
        return _require(project).update_company(
            _company_in_to_obj(body, company_id)
        ).to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="Company not found.")


@router.delete("/companies/{company_id}", status_code=204)
def delete_company(company_id: int, project: str = Query(...)):
    try:
        _require(project).delete_company(company_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Company not found.")


# ── icons ──────────────────────────────────────────────────────────────────────

@router.post("/icons", response_model=IconOut, status_code=201)
async def upload_icon(file: UploadFile = File(...), project: str = Query(...)):
    storage = _require(project)
    ct = file.content_type or ""
    if ct not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported type '{ct}'.")
    data = await file.read()
    if len(data) > MAX_ICON_BYTES:
        raise HTTPException(status_code=413, detail="Icon exceeds 2 MB.")
    ext = mimetypes.guess_extension(ct) or ".png"
    if ext in (".jpe", ".jfif"):
        ext = ".jpg"
    filename = f"{uuid.uuid4().hex}{ext}"
    storage.save_icon(filename, data)
    url = f"/api/v1/icons/{filename}?project={project}"
    # auto-catalogue the uploaded icon as a "url" entry pointing to the api path
    storage.add_to_icon_catalogue("url", url)
    return {"filename": filename, "url": url}


@router.get("/icons/{filename}")
def serve_icon(filename: str, project: str = Query(...)):
    storage = _require(project)
    p = storage.icons_dir / filename
    if not p.exists():
        raise HTTPException(status_code=404, detail="Icon not found.")
    try:
        p.relative_to(storage.icons_dir)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    return FileResponse(p)


@router.get("/icons", response_model=list[IconOut])
def list_icons(project: str = Query(...)):
    s = _require(project)
    return [
        {"filename": n, "url": f"/api/v1/icons/{n}?project={project}"}
        for n in s.list_icons()
    ]


# ── icon catalogue ────────────────────────────────────────────────────────────

@router.get("/icon-catalogue", response_model=list[IconCatalogueOut])
def list_icon_catalogue(project: str = Query(...)):
    return [e.to_dict() for e in _require(project).list_icon_catalogue()]


@router.post("/icon-catalogue", response_model=IconCatalogueOut, status_code=201)
def add_to_icon_catalogue(body: IconCatalogueIn, project: str = Query(...)):
    entry = _require(project).add_to_icon_catalogue(body.type, body.value, body.label)
    if entry is None:
        raise HTTPException(status_code=500, detail="Failed to add icon to catalogue.")
    return entry.to_dict()


@router.patch("/icon-catalogue/{entry_id}", response_model=IconCatalogueOut)
def update_icon_catalogue_label(
    entry_id: int,
    body: dict,
    project: str = Query(...),
):
    label = body.get("label", "")
    try:
        return _require(project).update_icon_catalogue_label(entry_id, label).to_dict()
    except KeyError:
        raise HTTPException(status_code=404, detail="Icon catalogue entry not found.")


@router.delete("/icon-catalogue/{entry_id}", status_code=204)
def delete_from_icon_catalogue(entry_id: int, project: str = Query(...)):
    try:
        _require(project).delete_from_icon_catalogue(entry_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Icon catalogue entry not found.")


# ── health ─────────────────────────────────────────────────────────────────────

@router.get("/health")
def health():
    return {"status": "ok"}