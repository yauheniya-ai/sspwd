"""
Offline icon cache — downloads external icons into the local icons directory
so the password manager works seamlessly without an internet connection.

Supported icon types
--------------------
* ``iconify``  — fetched from the Iconify public API as SVG.
* ``url``      — downloaded from the remote URL; raster images are resized
                  to 64 × 64 px when *Pillow* is installed (optional dep).

Letter icons need no caching — they are rendered from a single character.
"""
from __future__ import annotations

import hashlib
import io
import logging
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Iconify public API for individual SVG icons
_ICONIFY_URL = "https://api.iconify.design/{collection}/{name}.svg"

# Known raster / vector extensions
_RASTER_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".bmp"}
_SVG_EXTS    = {".svg"}

_USER_AGENT  = "sspwd-icon-cache/1.0"
_TIMEOUT     = 10   # seconds per HTTP request


# ── helpers ───────────────────────────────────────────────────────────────────

def _hash_key(type_: str, value: str) -> str:
    """Return a 20-char hex digest that uniquely identifies (type, value)."""
    return hashlib.sha256(f"{type_}:{value}".encode()).hexdigest()[:20]


def _ext_from_url(url: str) -> str:
    """Best-guess file extension from the URL path (ignores query string)."""
    path   = url.split("?")[0].rstrip("/")
    suffix = Path(path).suffix.lower()
    if suffix in _RASTER_EXTS | _SVG_EXTS:
        return suffix
    return ""


def _ext_from_content_type(ct: str) -> str:
    ct = ct.lower().split(";")[0].strip()
    mapping = {
        "image/svg+xml":              ".svg",
        "image/png":                  ".png",
        "image/jpeg":                 ".jpg",
        "image/webp":                 ".webp",
        "image/gif":                  ".gif",
        "image/x-icon":               ".ico",
        "image/vnd.microsoft.icon":   ".ico",
    }
    return mapping.get(ct, "")


def _fetch(url: str) -> tuple[bytes, str]:
    """
    Download *url* and return ``(body_bytes, content_type)``.
    Raises ``urllib.error.URLError`` / ``OSError`` on network failure.
    """
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        content_type = resp.headers.get("Content-Type", "")
        return resp.read(), content_type


def _resize_raster(data: bytes, size: int = 64) -> Optional[bytes]:
    """
    Resize *data* to ``size × size`` and return PNG bytes.
    Returns ``None`` if Pillow is not installed or the image cannot be decoded.
    """
    try:
        from PIL import Image  # type: ignore[import]
    except ImportError:
        return None
    try:
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        img.thumbnail((size, size), Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()
    except Exception as exc:  # pragma: no cover
        log.warning("icon resize failed: %s", exc)
        return None


# ── public API ────────────────────────────────────────────────────────────────

def cache_iconify(value: str, icons_dir: Path) -> Optional[str]:
    """
    Download an Iconify icon (e.g. ``"mdi:home"``) as an SVG file and save it
    to *icons_dir*.  Returns the saved filename on success, ``None`` on failure.
    """
    if ":" not in value:
        log.debug("cache_iconify: malformed value %r (missing collection prefix)", value)
        return None

    collection, name = value.split(":", 1)
    filename = f"iconify_{_hash_key('iconify', value)}.svg"
    dest     = icons_dir / filename

    if dest.exists():
        return filename  # already cached — skip download

    url = _ICONIFY_URL.format(collection=collection, name=name)
    try:
        data, _ct = _fetch(url)
    except Exception as exc:
        log.debug("cache_iconify: fetch failed for %s: %s", url, exc)
        return None

    # Iconify returns the literal text "404" (not an HTTP 404) for unknown icons
    stripped = data.strip()
    if not stripped or stripped == b"404" or not stripped.startswith(b"<"):
        log.debug("cache_iconify: unexpected response for %r", value)
        return None

    dest.write_bytes(data)
    log.debug("cache_iconify: cached %r → %s", value, filename)
    return filename


def cache_url(value: str, icons_dir: Path) -> Optional[str]:
    """
    Download a URL icon and save it to *icons_dir*.
    Raster images are resized to 64 × 64 px when Pillow is available.
    Returns the saved filename on success, ``None`` on failure.

    Already-local API paths (``/api/…`` or ``/icons/…``) are skipped — they
    are already stored on disk.
    """
    # Local API-served path — already on disk, nothing to do
    if value.startswith("/api/") or value.startswith("/icons/"):
        return None

    key = _hash_key("url", value)

    # If we already cached this URL (under any extension), return it
    for existing in icons_dir.glob(f"url_{key}.*"):
        return existing.name

    url_ext = _ext_from_url(value)

    try:
        data, content_type = _fetch(value)
    except Exception as exc:
        log.debug("cache_url: fetch failed for %s: %s", value, exc)
        return None

    if not data:
        return None

    # Determine true extension from content-type (more reliable than URL)
    ct_ext = _ext_from_content_type(content_type)
    ext    = ct_ext or url_ext or ".png"

    is_svg = (ext == ".svg") or ("svg" in content_type.lower())

    if is_svg:
        filename = f"url_{key}.svg"
        (icons_dir / filename).write_bytes(data)
    else:
        resized = _resize_raster(data)
        if resized is not None:
            filename = f"url_{key}.png"
            (icons_dir / filename).write_bytes(resized)
        else:
            # Pillow not available — save raw bytes with best-guess extension
            filename = f"url_{key}{ext}"
            (icons_dir / filename).write_bytes(data)

    log.debug("cache_url: cached %s → %s", value, filename)
    return filename


def cache_icon(type_: str, value: str, icons_dir: Path) -> Optional[str]:
    """
    Route to the correct downloader for *type_*.
    Returns the cached filename or ``None`` (letter icons always return ``None``).
    """
    if type_ == "iconify":
        return cache_iconify(value, icons_dir)
    if type_ == "url":
        return cache_url(value, icons_dir)
    return None   # "letter" icons are rendered from text — no file needed
