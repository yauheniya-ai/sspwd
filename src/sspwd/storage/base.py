from abc import ABC, abstractmethod
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PasswordEntry:
    id: Optional[int]
    title: str
    username: str
    password: str          # stored encrypted, returned decrypted
    url: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "username": self.username,
            "password": self.password,
            "url": self.url,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class BaseStorage(ABC):
    """Abstract interface that every storage backend must implement."""

    @abstractmethod
    def initialize(self) -> None:
        """Create tables / files if they do not exist yet."""

    @abstractmethod
    def add(self, entry: PasswordEntry) -> PasswordEntry:
        """Persist a new entry and return it with its assigned id."""

    @abstractmethod
    def get(self, entry_id: int) -> Optional[PasswordEntry]:
        """Return a single entry by id, or None if not found."""

    @abstractmethod
    def list(self, search: Optional[str] = None) -> list[PasswordEntry]:
        """Return all entries, optionally filtered by a search string."""

    @abstractmethod
    def update(self, entry: PasswordEntry) -> PasswordEntry:
        """Overwrite an existing entry. Raises KeyError if id not found."""

    @abstractmethod
    def delete(self, entry_id: int) -> None:
        """Remove an entry by id. Raises KeyError if not found."""