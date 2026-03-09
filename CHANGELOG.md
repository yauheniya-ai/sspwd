# Changelog

## Version 0.1.2 (2026-03-09)

### Multi-project vault support

- Vault layout changed from `~/.sspwd/vault.db` to `~/.sspwd/{project}/vault.db`
- New `--project` / `-p` flag on all CLI commands (`serve`, `add`, `list`, `get`, `delete`)
- New `sspwd projects` command lists all existing vaults with their sizes
- Default project name is `default` when no `--project` flag is given
- Icons are stored per-project at `~/.sspwd/{project}/icons/`

### Password-free server startup

- `sspwd serve` no longer prompts for a master password at startup
- Server starts unlocked into mock/demo mode
- Projects are unlocked on demand via `POST /api/v1/projects/{name}/unlock` in the browser
- Multiple projects can be unlocked and switched between within a single server session

### New API endpoints

- `GET  /api/v1/projects` — list all projects that exist on disk
- `GET  /api/v1/projects/unlocked` — list projects unlocked in the current session
- `POST /api/v1/projects/{name}/unlock` — unlock a project with its master password
- `POST /api/v1/projects` — create a new project
- `DELETE /api/v1/projects/{name}/lock` — lock a project (remove from session)
- All entry and icon endpoints now require `?project=` query parameter

### Entry persistence fixed

- Adding, editing, and deleting entries now calls the backend API and persists to `vault.db`
- Previously entries were only stored in React state and lost on page reload
- Mock mode (`mockData`) continues to work in local state only

### Icon upload fixed

- Icon upload now correctly passes `?project=` to `POST /api/v1/icons`
- Uploaded icons are saved to `~/.sspwd/{project}/icons/` and survive server restarts
- Mock mode falls back to a local object URL for preview without a backend

### Frontend — project selector redesign

- Native `<select>` replaced with a custom dropdown that renders Iconify icons per option
- Locked projects show `si:lock-muted-fill` icon
- Unlocked projects show `si:unlock-fill` icon in green
- mockData entry shows `si:unlock-fill` (not a database icon — db icon remains next to the dropdown)
- Active unlocked project shows `si:unlock-fill` + `live` badge in the header
- "+ new project" label shortened to "+ new"

### Frontend — unlock modal improvements

- Modal title shows only the project name (e.g. `ya`), not `Unlock — ya`
- Password field label changed from `MASTER PASSWORD` to `ENTER MASTER PASSWORD TO UNLOCK`
- Unlock button shows `si:unlock-fill` icon alongside the label

### Service type simplified

- `ServiceType` reduced from four values (`free`, `paid`, `freemium`, `unknown`) to two (`free`, `paid`)
- All mock entries updated accordingly

### Bug fixes

- `from __future__ import annotations` added to `sqlite.py` to fix `list[str]` type hint crash on Python 3.10
- Empty vault state now shows an "Add first entry" button instead of only the `∅` symbol
- Empty state message distinguishes between "No entries yet." and "No entries match your filters."
- `serviceType` mapping from API response corrected from `"unknown"` fallback to `"free"`

## Version 0.1.1 (2026-03-08)

- Fixed search input triggering browser password manager / fingerprint prompt by switching to `type="search"` with `autocomplete="off"`, `data-form-type="other"`, and `data-lpignore="true"`
- Added solid Iconify icons per category in the sidebar (`mdi:school`, `mdi:bank`, `mdi:server`, etc.) with a `CATEGORY_ICONS` map for easy extension
- Fixed `--no-browser` flag — browser no longer opens when the flag is passed; rewired launch to uvicorn's startup event to eliminate the race condition
- Vault selector dropdown in the header now fetches live data from `GET /api/v1/entries` when `vault.db` is selected, with loading state and error message if the server is unreachable
- Moved "Add entry" button from the header into the main content summary bar, inline with the entry/category count

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