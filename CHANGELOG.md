# Changelog

## Version 0.2.5 (2026-03-12)
Adds an icon catalogue shared across entries and owners, a full owners manager view, and miscellaneous UX fixes.

- **Icon catalogue** — new `icon_catalogue` table (columns: `id`, `type`, `value`, `label`, `created_at`); auto-populated with a unique constraint whenever an icon is saved to an entry or company; full CRUD API at `GET/POST/PATCH/DELETE /api/v1/icon-catalogue`; icons appear in a new **library** tab inside the icon picker so previously used icons can be reused without retyping; labels are editable inline; individual icons can be removed from the library
- **Owners Manager modal** — "All owners" button in the AddEdit modal opens a full-table overlay listing every company with name, location, revenue, and entry-usage count; supports inline edit (all fields including icon and address), delete with confirmation, and adding a new owner directly from the table; changes persist to the backend immediately
- **AddEdit modal no longer closes on Escape or backdrop click** — data entered is preserved until the user explicitly clicks Cancel or ✕
- **`examine_vault.py` updated** — icon count shown in the metadata header; new `--icons` flag prints the icon catalogue as a compact table (ID, type, label, value)

## Version 0.2.4 (2026-03-12)
Fixes data loss where entry icons, service type, and all owner/company details silently disappeared after restarting the server. Rebuilds the frontend bundle directly into the package static directory.

- **Entry icon persisted** — `icon` was never stored in the database; added `icon TEXT` column to the `entries` table (JSON `{type, value}`) in the schema, migration, `PasswordEntry` dataclass, `EntryIn` API schema, and both `add` / `update` SQL calls; `icon` is now included in the API request body on create and edit
- **Service type persisted** — `service_type` (`"free"` / `"paid"`) was never stored; same fix applied — `service_type TEXT DEFAULT 'free'` added to the schema and migration; propagated through `PasswordEntry`, `EntryIn`, and all read/write paths
- **Company / owner details persisted** — saving an entry with a new company name only sent `company_id: null`; the company object itself was never POSTed to the API; `handleSave` now upserts the company first (`POST /api/v1/companies` for new, `PUT /api/v1/companies/{id}` for existing) and passes the returned ID into the entry body
- **Companies loaded from vault on unlock** — `companies` state was initialised from hard-coded mock data and never refreshed from the API; `loadProject` now fetches `GET /api/v1/entries` and `GET /api/v1/companies` in parallel, builds a `Map<id, Company>`, and embeds the full company object into each entry so owner details appear immediately after reopening the vault
- **Build output points to package static directory** — `vite.config.ts` lacked an `outDir`; running `npm run build` was writing to `frontend/dist/` (not served by the Python server) instead of `pypi/src/sspwd/ui/static/`; added `build.outDir` and `build.emptyOutDir` so every build replaces the bundled frontend that `sspwd serve` actually serves

## Version 0.2.3 (2026-03-12)
Adds master password rotation with crash-safe re-encryption, a new CLI command, and a standalone helper script.
- **`sspwd change-password --project NAME`** — new CLI command; prompts for the current password (verified before proceeding), then prompts for the new password with confirmation; guards against empty and identical passwords
- **`SQLiteStorage.reencrypt(new_master)`** — re-encrypts all sensitive columns (`password`, `email`, `notes`) in a single atomic SQLite transaction; new Argon2id salt is staged to `salt.bin.tmp` before the commit and promoted with a POSIX atomic rename afterwards, so a mid-process crash leaves the vault consistent
- **`scripts/change_master_password.py`** — standalone script usable without installing the package; accepts the project name as a positional argument (defaults to `default`); validates vault existence, current password, new-password confirmation, and no-op case before re-encrypting
- **5 new tests in `TestReencrypt`** — cover data preservation, new password acceptance, old password rejection, multiple entries, and `None` encrypted fields

## Version 0.2.2 (2026-03-12)
Improves the card display logic, broadens search coverage, adds sorting and filtering options, and cleans up mock data.
- **Email / username display unified in cards** — `PasswordCard` now shows whichever identifier is present, preferring email over username; the row is hidden when both are empty; icon switches to `mdi:email-outline` when displaying an email
- **Search includes email field** — the sidebar search now matches against both `username` and `email`; guards added for optional fields to prevent `undefined.toLowerCase()` crashes
- **"Using since" sort option** — sidebar sort dropdown gains a "Using since" option that orders entries by `userCreatedAt`; entries without the field sort to the end
- **Login method filter** — sidebar now includes a "Login method" filter section with `TagBadge` pills for every method present in the vault (OR logic — entry must support any of the selected methods); integrated with "Clear all filters"
- **HQ country filter** — sidebar gains a "HQ country" filter section derived from `company.address.country`; selecting multiple countries widens the results (OR logic)
- **Mock data completed** — `userCreatedAt` added to all 32 mock entries; `MOCK_COMPANIES` entries 28–31 reformatted to match the rest of the file (unquoted keys, single-line addresses, `state` field added where missing)

## Version 0.2.1 (2026-03-10)
Extends the entry model with split username/email and structured company data, and polishes the detail panel layout.
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
Replaces PBKDF2 + Fernet with Argon2id + AES-256-GCM — a breaking vault format change with significantly stronger security.

### Breaking change — vault format incompatible with v0.1.x
Existing vaults encrypted under v0.1.x cannot be read by v0.2.0. Use the `examine_vault.py` utility to export your entries before upgrading, then re-import them into a new vault.

- **KDF changed from PBKDF2-HMAC-SHA256 (390k iterations) to Argon2id** — parameters: `time_cost=3`, `memory_cost=64 MiB`, `parallelism=2`; memory-hard against GPU/ASIC cracking; meets and exceeds OWASP 2024 minimums; new dependency: `argon2-cffi>=23.1`
- **Cipher changed from Fernet (AES-128-CBC + HMAC-SHA256) to AES-256-GCM** — 256-bit key; built-in AEAD authentication; 12-byte random nonce per encryption call; wire format: `base64(nonce[12] || ciphertext+tag)`; faster on CPUs with AES-NI
- **`verify.bin` sentinel added** — contains `"sspwd-ok"` encrypted with the vault key; decrypted on every `SQLiteStorage.__init__()`; wrong password raises `InvalidTag` immediately before any entry data is touched
- Added: `argon2-cffi>=23.1`; `cryptography>=42.0` retained (now used for `AESGCM` instead of `Fernet`)

## Version 0.1.2 (2026-03-09)
Introduces multi-project vault support, password-free server startup, and on-demand project unlocking via the browser.
- **Multi-project vaults** — layout changed from `~/.sspwd/vault.db` to `~/.sspwd/{project}/vault.db`; new `--project` / `-p` flag on all CLI commands; new `sspwd projects` command; default project name is `default`; icons stored per-project at `~/.sspwd/{project}/icons/`
- **Password-free server startup** — `sspwd serve` no longer prompts at startup; server starts in mock/demo mode; projects unlocked on demand via `POST /api/v1/projects/{name}/unlock`; multiple projects can be unlocked and switched within a single session
- **New API endpoints** — `GET /api/v1/projects`, `GET /api/v1/projects/unlocked`, `POST /api/v1/projects/{name}/unlock`, `POST /api/v1/projects`, `DELETE /api/v1/projects/{name}/lock`; all entry and icon endpoints now require `?project=`
- **Entry persistence fixed** — add, edit, and delete now call the backend API and persist to `vault.db`; mock mode continues to work in local state only
- **Icon upload fixed** — correctly passes `?project=` to `POST /api/v1/icons`; icons saved to `~/.sspwd/{project}/icons/` and survive server restarts
- **Frontend — project selector redesign** — native `<select>` replaced with a custom dropdown rendering Iconify icons per option; locked/unlocked/active states with distinct icons and a `live` badge
- **Frontend — unlock modal improvements** — modal title shows only the project name; password label changed to `ENTER MASTER PASSWORD TO UNLOCK`; unlock button shows `si:unlock-fill` icon
- **Service type simplified** — `ServiceType` reduced from four values to two (`free`, `paid`); all mock entries updated
- **Bug fixes** — `from __future__ import annotations` added to `sqlite.py` to fix Python 3.10 crash; empty vault shows "Add first entry" button; empty state message distinguishes no entries from no filter matches; `serviceType` API mapping corrected

## Version 0.1.1 (2026-03-08)
Fixes browser password manager interference, improves sidebar navigation, and repairs the `--no-browser` startup flag.
- Fixed search input triggering browser password manager / fingerprint prompt by switching to `type="search"` with `autocomplete="off"`, `data-form-type="other"`, and `data-lpignore="true"`
- Added solid Iconify icons per category in the sidebar (`mdi:school`, `mdi:bank`, `mdi:server`, etc.) with a `CATEGORY_ICONS` map for easy extension
- Fixed `--no-browser` flag — browser no longer opens when the flag is passed; rewired launch to uvicorn's startup event to eliminate the race condition
- Vault selector dropdown in the header now fetches live data from `GET /api/v1/entries` when `vault.db` is selected, with loading state and error message if the server is unreachable
- Moved "Add entry" button from the header into the main content summary bar, inline with the entry/category count

## Version 0.1.0 (2026-03-08)
Initial release — full-stack local password manager with encrypted SQLite storage, a FastAPI backend, and a React/Vite frontend.
- Initialized PyPI package `sspwd` with `setuptools` build backend and `pyproject.toml`
- Implemented `PasswordEntry` dataclass and `BaseStorage` abstract interface
- Built SQLite storage backend with PBKDF2-SHA256 key derivation (390k iterations) and Fernet AES encryption; sensitive fields (`password`, `notes`) encrypted at rest
- Created FastAPI REST API (`/api/v1`) with full CRUD: list, create, get, update, delete, and search
- Added `UIServer` class serving the React SPA as static files with a catch-all SPA fallback route
- Built `Click` CLI with commands: `serve`, `add`, `list`, `get`, `delete`, `version`
- Wrote `examine_vault.py` utility script to inspect raw or decrypted vault contents from the terminal
- Added pytest test suite covering storage and API endpoints
- Initialized React + Vite + TypeScript + Tailwind CSS v4 frontend
- Designed 3-column layout: `Sidebar` / `MainContent` / `DetailPanel` with blue-700 → red-700 gradient `Header`
- Built `Sidebar` with live search, tag filter pills, service-type filter, sort controls, and category tree with entry counts
- Implemented `MainContent` grouping entries by category with a responsive card grid
- Created `PasswordCard` with masked password toggle, one-click copy, tag badges, and service-type indicator
- Built `DetailPanel` showing full entry details, copy fields, edit and delete actions
- Added `AddEditModal` form with icon picker (Iconify / URL / letter fallback), strong password generator, tag autocomplete, and category autocomplete
- Created `EntryIcon` component supporting Iconify icons, external image URLs, and letter fallback
- Defined shared TypeScript types (`PasswordEntry`, `FilterState`, `IconSource`, `ServiceType`)
- Populated 15 realistic mock entries across 8 categories
- Wired all state management in `App.tsx` with filter, selection, add/edit/delete, and modal lifecycle


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