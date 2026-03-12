# Changelog

## Version 0.2.2 (2026-03-12)

- **Email / username display unified in cards** — `PasswordCard` now shows whichever identifier is present, preferring email over username; the row is hidden when both are empty; icon switches to `mdi:email-outline` when displaying an email
- **Search includes email field** — the sidebar search now matches against both `username` and `email`; guards added for optional fields to prevent `undefined.toLowerCase()` crashes
- **"Using since" sort option** — sidebar sort dropdown gains a "Using since" option that orders entries by `userCreatedAt`; entries without the field sort to the end
- **Login method filter** — sidebar now includes a "Login method" filter section with `TagBadge` pills for every method present in the vault (AND logic — entry must support all selected methods); integrated with "Clear all filters"
- **Mock data completed** — `userCreatedAt` added to all 32 mock entries; `MOCK_COMPANIES` entries 28–31 reformatted to match the rest of the file (unquoted keys, single-line addresses, `state` field added where missing)

## Version 0.2.1 (2026-03-10)

- **Username and email split into separate fields** — entries now store `username` (login handle) and `email` independently; both optional and both shown in the detail panel with copy buttons
- **Company / owner info redesigned** — owner icon uses the same four-tab picker as entry icons (letter / iconify / url / upload); headquarters stored as structured address (`street`, `city`, `state`, `postcode`, `country`, `countryCode`) instead of a flat string; revenue stored as a raw USD number (`REAL` in SQLite) and formatted as `$307.4B` / `$729M` in the UI
- **Detail panel shows all fields at all times** — every section (Credentials, Classification, Owner, Dates) is always rendered; empty fields display a dimmed `—` so the layout is consistent across all entries
- **Country flag and address toggle in detail panel** — headquarters shows the country name with an inline `circle-flags` icon; full street address is hidden behind a "full address ↓" toggle to save space
- **Login methods field** — 12 common methods (Email / Password, Google, GitHub, Apple, SSO, API Key, …) selectable as chips, plus free-text input for custom methods; stored as a JSON array
- **"Used since" date** — optional user-supplied date for when they started using a service, stored separately from the vault record's `created_at`; shown in the Dates section with a ★ icon
- **Only title is required** — all other entry fields (username, email, password, URL, category, tags, notes, login methods, owner, used since) are optional
- **Backend schema extended** — new `entries` columns: `email` (encrypted), `category`, `tags` (JSON), `login_methods` (JSON), `user_created_at`; `companies` columns: `icon` (JSON), `address` (JSON), `revenue` (REAL); automatic migration via `ALTER TABLE ADD COLUMN` for existing vaults
- **Header cleaned up** — removed duplicate unlock icon and "live" badge shown outside the dropdown; removed folder icon from the "+ new" option
- **`examine_vault.py` rewritten** — updated to Argon2id + AES-256-GCM crypto; displays all new columns; `--companies` flag shows owner table with formatted revenue and structured address; `--project <name>` shortcut resolves `~/.sspwd/<name>/vault.db`; `--list` shows all projects with entry counts

## Version 0.2.0 (2026-03-09)

### Breaking change — vault format incompatible with v0.1.x

Existing vaults encrypted under v0.1.x cannot be read by v0.2.0. Use the
`examine_vault.py` utility to export your entries before upgrading, then
re-import them into a new vault.

### Security upgrade — Argon2id + AES-256-GCM

- **KDF changed from PBKDF2-HMAC-SHA256 (390k iterations) to Argon2id**
  - Parameters: `time_cost=3`, `memory_cost=64 MiB`, `parallelism=2`
  - Argon2id is memory-hard — GPU/ASIC parallel cracking attacks are
    exponentially more expensive than against PBKDF2
  - Parameters meet and exceed OWASP 2024 minimum recommendations
  - New dependency: `argon2-cffi>=23.1`

- **Cipher changed from Fernet (AES-128-CBC + HMAC-SHA256) to AES-256-GCM**
  - 256-bit key (up from 128-bit)
  - GCM is an AEAD mode: authentication is built-in (no separate HMAC)
  - 12-byte random nonce generated fresh for every encryption call
  - Wire format: `base64(nonce[12] || ciphertext+tag)` stored in SQLite
  - Faster than CBC+HMAC on CPUs with AES-NI (all modern hardware)

- **`verify.bin` sentinel added to each vault**
  - Contains `"sspwd-ok"` encrypted with the vault's key
  - Decrypted on every `SQLiteStorage.__init__()` call
  - Wrong master password raises `InvalidTag` immediately, before any
    entry data is touched — prevents silent corruption on wrong password
  - Replaces the previous `storage.list()` verification attempt, which
    failed silently on empty vaults

### Dependency changes

- Added: `argon2-cffi>=23.1`
- `cryptography>=42.0` retained (now used for `AESGCM` instead of `Fernet`)

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