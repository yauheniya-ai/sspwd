# sspwd – super secret password

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-red.svg)](https://opensource.org/licenses/MIT)
[![PyPI version](https://img.shields.io/pypi/v/sspwd?color=blue&label=PyPI)](https://pypi.org/project/sspwd/)
[![Tests](https://github.com/yauheniya-ai/sspwd/actions/workflows/tests.yml/badge.svg)](https://github.com/yauheniya-ai/sspwd/actions/workflows/tests.yml)
[![Coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/yauheniya-ai/54efe8e9445e06c13617aa69bae44b21/raw/coverage.json)](https://github.com/yauheniya-ai/sspwd/actions/workflows/tests.yml)
[![GitHub last commit](https://img.shields.io/github/last-commit/yauheniya-ai/sspwd)](https://github.com/yauheniya-ai/sspwd/commits/main)


A local, encrypted password manager with a built-in web UI.

<p align="center">
  <img src="https://raw.githubusercontent.com/yauheniya-ai/sspwd/main/docs/images/Screenshot.png" width="100%" />
  <em>Interactive UI to manage passwords</em>
</p>

Passwords are stored in `~/.sspwd/default/vault.db` — fully encrypted with a key
derived from your master password. Nothing leaves your machine.

---

## Tech Stack

**Backend**
- <img src="https://api.iconify.design/devicon:python.svg" width="16" height="16"> Python — package language
- <img src="https://api.iconify.design/devicon:fastapi.svg" width="16" height="16"> FastAPI — REST API for the web UI
- <img src="https://api.iconify.design/devicon:sqlite.svg" width="16" height="16"> SQLite — local encrypted vault database
- <img src="https://api.iconify.design/streamline-plump-color:device-database-encryption-1-flat.svg" width="16" height="16"> Argon2id + AES-256-GCM — key derivation and authenticated encryption via `argon2-cffi` + `cryptography`
- <img src="https://api.iconify.design/devicon:pytest.svg" width="16" height="16"> pytest — test suite with coverage reporting

**Frontend**
- <img src="https://api.iconify.design/devicon:react.svg" width="16" height="16"> React — interactive UI
- <img src="https://api.iconify.design/devicon:vitejs.svg" width="16" height="16"> Vite — frontend build tool and dev server
- <img src="https://api.iconify.design/devicon:typescript.svg" width="16" height="16"> TypeScript — type-safe components
- <img src="https://api.iconify.design/devicon:tailwindcss.svg" width="16" height="16"> Tailwind CSS — utility-first styling
- <img src="https://avatars.githubusercontent.com/u/50354982?v=4" width="16" height="16"> Iconify — service and brand icons

**CLI**
- <img src="https://api.iconify.design/devicon:clickhouse.svg" width="16" height="16"> Click — CLI commands (`serve`, `add`, `list`, `get`, `delete`, `projects`)

**Packaging**
- <img src="https://api.iconify.design/devicon:pypi.svg" width="16" height="16"> PyPI — distributed as an installable Python package

## Installation

```bash
pip install sspwd
```

> Requires Python ≥ 3.10.

---

## Quick start

### Web UI

```bash
sspwd serve
```

Opens `http://127.0.0.1:7523` in your default browser. Enter your master
password when prompted (a new vault is created automatically on first run).

### CLI

```bash
# Add an entry
sspwd add

# List all entries
sspwd list

# Search
sspwd list --search github

# Show a single entry (reveals password)
sspwd get 3

# Delete an entry
sspwd delete 3
```

### Custom vault location

```bash
sspwd serve --vault-dir /path/to/my/vault
```

---

## Security

| Detail | Value |
|---|---|
| Encryption | AES-256-GCM (authenticated — detects tampering via built-in auth tag) |
| Key derivation | [Argon2id](https://github.com/hynek/argon2-cffi) — memory-hard, OWASP 2024 recommended |
| Argon2id parameters | `time=3`, `memory=64 MiB`, `parallelism=2` |
| Key size | 256-bit |
| Nonce | 12 bytes, random per encryption call (never reused) |
| Storage | SQLite (`~/.sspwd/{project}/vault.db`) |
| Key never stored | Derived in memory on unlock, discarded on server exit |

**Vault files explained**

| File | Purpose |
|---|---|
| `salt.bin` | 32 random bytes, created once. Makes your key unique to this vault — the same password on two vaults produces two completely different keys. Not secret on its own. |
| `verify.bin` | A tiny AES-256-GCM encrypted file containing a known plaintext. Decrypted on every unlock to verify the master password immediately — wrong password → `InvalidTag` → 401, before any entry data is touched. |
| `vault.db` | SQLite database. All `password` and `notes` fields are AES-256-GCM encrypted. Titles and usernames are stored in plaintext for search. |
| `icons/` | User-uploaded icon files, served locally. |

The master password is never stored anywhere. It is entered in the browser when unlocking a project, used to derive the key via Argon2id, and the key lives only in process memory for the lifetime of the server session.

---

## Development

```bash
git clone https://github.com/yauheniya-ai/sspwd
cd sspwd/pypi

# Install in editable mode with dev extras
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src tests
```

### Building the React UI

```bash
cd ../frontend
npm install
npm run build
# Copy dist/ into pypi/src/sspwd/ui/static/
cp -r dist/* ../pypi/src/sspwd/ui/static/
```

---

## License

MIT — see [LICENSE](LICENSE).