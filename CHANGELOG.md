# Changelog

## Version 0.1.0 (2026-03-08)

- Initialized PyPI package `sspwd` with `setuptools` build backend and `pyproject.toml`
- Implemented `PasswordEntry` dataclass and `BaseStorage` abstract interface
- Built SQLite storage backend with PBKDF2-SHA256 key derivation (390k iterations) and Fernet AES encryption
- Sensitive fields (`password`, `notes`) encrypted at rest; only a random 32-byte salt persisted to disk
- Created FastAPI REST API (`/api/v1`) with full CRUD: list, create, get, update, delete, and search
- Added `UIServer` class serving the React SPA as static files with a catch-all SPA fallback route
- Built `Click` CLI with commands: `serve`, `add`, `list`, `get`, `delete`, `version`
- Wrote `examine_vault.py` utility script to inspect raw or decrypted vault contents from the terminal
- Added pytest test suite covering storage (add, list, update, delete, search, wrong-password decryption) and API endpoints
- Initialized React + Vite + TypeScript + Tailwind CSS v4 frontend
- Designed 3-column layout: `Sidebar` / `MainContent` / `DetailPanel` with blue-700 → red-700 gradient `Header`
- Built `Sidebar` with live search, tag filter pills, service-type filter, sort controls, and category tree with entry counts
- Implemented `MainContent` grouping entries by category with a responsive card grid
- Created `PasswordCard` with masked password toggle, one-click copy for username and password, tag badges, and service-type indicator
- Built `DetailPanel` showing full entry details, copy fields, edit and delete actions
- Added `AddEditModal` form with icon picker (Iconify / URL / letter fallback), strong password generator, tag autocomplete, and category autocomplete
- Created `EntryIcon` component supporting Iconify icons, external image URLs (e.g. companieslogo.com), and letter fallback
- Defined shared TypeScript types (`PasswordEntry`, `FilterState`, `IconSource`, `ServiceType`)
- Populated 15 realistic mock entries across 8 categories (Software, Finance, Education, Hosting, etc.)
- Wired all state management in `App.tsx` with filter, selection, add/edit/delete, and modal lifecycle