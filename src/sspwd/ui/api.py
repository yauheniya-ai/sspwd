"""
REST API layer — thin bridge between HTTP and the storage backend.

All routes are mounted under /api/v1 by server.py.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from ..storage.base import PasswordEntry
from ..storage.sqlite import SQLiteStorage

router = APIRouter(prefix="/api/v1")

# The storage instance is injected at startup by UIServer.
_storage: Optional[SQLiteStorage] = None


def set_storage(storage: SQLiteStorage) -> None:
    global _storage
    _storage = storage


def _get_storage() -> SQLiteStorage:
    if _storage is None:
        raise RuntimeError("Storage has not been initialised.")
    return _storage


# ------------------------------------------------------------------
# Pydantic schemas
# ------------------------------------------------------------------


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


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------


@router.get("/entries", response_model=list[EntryOut])
def list_entries(search: Optional[str] = Query(default=None)):
    storage = _get_storage()
    entries = storage.list(search=search)
    return [e.to_dict() for e in entries]


@router.post("/entries", response_model=EntryOut, status_code=201)
def create_entry(body: EntryIn):
    storage = _get_storage()
    entry = PasswordEntry(
        id=None,
        title=body.title,
        username=body.username,
        password=body.password,
        url=body.url,
        notes=body.notes,
    )
    created = storage.add(entry)
    return created.to_dict()


@router.get("/entries/{entry_id}", response_model=EntryOut)
def get_entry(entry_id: int):
    storage = _get_storage()
    entry = storage.get(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found.")
    return entry.to_dict()


@router.put("/entries/{entry_id}", response_model=EntryOut)
def update_entry(entry_id: int, body: EntryIn):
    storage = _get_storage()
    entry = PasswordEntry(
        id=entry_id,
        title=body.title,
        username=body.username,
        password=body.password,
        url=body.url,
        notes=body.notes,
    )
    try:
        updated = storage.update(entry)
    except KeyError:
        raise HTTPException(status_code=404, detail="Entry not found.")
    return updated.to_dict()


@router.delete("/entries/{entry_id}", status_code=204)
def delete_entry(entry_id: int):
    storage = _get_storage()
    try:
        storage.delete(entry_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Entry not found.")


@router.get("/health")
def health():
    return {"status": "ok"}