from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Icon catalogue
# ---------------------------------------------------------------------------

@dataclass
class IconCatalogueEntry:
    """One catalogued icon — unique by (type, value)."""
    id:              Optional[int]
    type:            str               # "letter" | "iconify" | "url"
    value:           str
    label:           Optional[str]     = None
    created_at:      Optional[datetime] = None
    cached_filename: Optional[str]     = None  # local file saved in icons_dir

    def to_dict(self) -> dict:
        return {
            "id":              self.id,
            "type":            self.type,
            "value":           self.value,
            "label":           self.label,
            "created_at":      self.created_at.isoformat() if self.created_at else None,
            "cached_filename": self.cached_filename,
        }


# ---------------------------------------------------------------------------
# Company / Owner
# ---------------------------------------------------------------------------

@dataclass
class CompanyAddress:
    country:      str
    country_code: str
    street:       Optional[str] = None
    city:         Optional[str] = None
    state:        Optional[str] = None
    postcode:     Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "street":       self.street,
            "city":         self.city,
            "state":        self.state,
            "postcode":     self.postcode,
            "country":      self.country,
            "countryCode":  self.country_code,
        }

    @staticmethod
    def from_dict(d: dict) -> "CompanyAddress":
        return CompanyAddress(
            country      = d.get("country", ""),
            country_code = d.get("countryCode", ""),
            street       = d.get("street"),
            city         = d.get("city"),
            state        = d.get("state"),
            postcode     = d.get("postcode"),
        )


@dataclass
class Company:
    id:      Optional[int]
    name:    str
    icon:    Optional[dict] = None          # {type, value} — matches frontend IconSource
    address: Optional[CompanyAddress] = None
    revenue: Optional[float] = None         # raw USD number, e.g. 307_400_000_000.0

    def to_dict(self) -> dict:
        return {
            "id":      self.id,
            "name":    self.name,
            "icon":    self.icon,
            "address": self.address.to_dict() if self.address else None,
            "revenue": self.revenue,
        }

    @staticmethod
    def from_dict(d: dict) -> "Company":
        addr_raw = d.get("address")
        return Company(
            id      = d.get("id"),
            name    = d.get("name", ""),
            icon    = d.get("icon"),
            address = CompanyAddress.from_dict(addr_raw) if addr_raw else None,
            revenue = d.get("revenue"),
        )


# ---------------------------------------------------------------------------
# Password entry
# ---------------------------------------------------------------------------

@dataclass
class PasswordEntry:
    id:              Optional[int]
    title:           str
    username:        Optional[str]  = None   # login handle / display name
    email:           Optional[str]  = None   # login email
    password:        Optional[str]  = None   # stored encrypted, returned decrypted
    url:             Optional[str]  = None
    notes:           Optional[str]  = None
    icon:            Optional[dict] = None   # {type, value} — matches frontend IconSource
    category:        str            = "Other"
    service_type:    str            = "free"  # "free" | "paid"
    tags:            list[str]      = field(default_factory=list)
    login_methods:   list[str]      = field(default_factory=list)
    company_id:      Optional[int]  = None
    user_created_at: Optional[datetime] = None
    created_at:      datetime       = field(default_factory=datetime.utcnow)
    updated_at:      datetime       = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id":              self.id,
            "title":           self.title,
            "username":        self.username,
            "email":           self.email,
            "password":        self.password,
            "url":             self.url,
            "notes":           self.notes,
            "icon":            self.icon,
            "category":        self.category,
            "service_type":    self.service_type,
            "tags":            self.tags,
            "login_methods":   self.login_methods,
            "company_id":      self.company_id,
            "user_created_at": self.user_created_at.isoformat() if self.user_created_at else None,
            "created_at":      self.created_at.isoformat(),
            "updated_at":      self.updated_at.isoformat(),
        }


# ---------------------------------------------------------------------------
# Abstract storage interface
# ---------------------------------------------------------------------------

class BaseStorage(ABC):

    @abstractmethod
    def initialize(self) -> None: ...

    @abstractmethod
    def add(self, entry: PasswordEntry) -> PasswordEntry: ...

    @abstractmethod
    def get(self, entry_id: int) -> Optional[PasswordEntry]: ...

    @abstractmethod
    def list(self, search: Optional[str] = None) -> list[PasswordEntry]: ...

    @abstractmethod
    def update(self, entry: PasswordEntry) -> PasswordEntry: ...

    @abstractmethod
    def delete(self, entry_id: int) -> None: ...

    def add_company(self, company: Company) -> Company:
        raise NotImplementedError

    def get_company(self, company_id: int) -> Optional[Company]:
        raise NotImplementedError

    def list_companies(self) -> list[Company]:
        raise NotImplementedError

    def update_company(self, company: Company) -> Company:
        raise NotImplementedError

    def delete_company(self, company_id: int) -> None:
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Icon catalogue
    # ------------------------------------------------------------------

    def add_to_icon_catalogue(
        self, type_: str, value: str, label: Optional[str] = None
    ) -> Optional["IconCatalogueEntry"]:
        raise NotImplementedError

    def list_icon_catalogue(self) -> list["IconCatalogueEntry"]:
        raise NotImplementedError

    def update_icon_catalogue_label(self, entry_id: int, label: str) -> "IconCatalogueEntry":
        raise NotImplementedError

    def delete_from_icon_catalogue(self, entry_id: int) -> None:
        raise NotImplementedError