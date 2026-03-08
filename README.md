# sspwd – super secret password

A local, encrypted password manager with a built-in web UI.

Passwords are stored in `~/.sspwd/vault.db` — fully encrypted with a key
derived from your master password. Nothing leaves your machine.

<p align="center">
  <img src="https://raw.githubusercontent.com/yauheniya-ai/sspwd/main/docs/images/Screenshot.png" width="100%" />
  <em>Interactive UI to manage passwords</em>
</p>
---

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
| Encryption | AES-128-CBC via [Fernet](https://cryptography.io/en/latest/fernet/) |
| Key derivation | PBKDF2-HMAC-SHA256, 390 000 iterations |
| Storage | SQLite (`~/.sspwd/vault.db`) |
| Key never stored | Only a random 32-byte salt is persisted |

The master password is required every time you start the app. There is no
"remember me" — the derived key lives only in process memory.

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