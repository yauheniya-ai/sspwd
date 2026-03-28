"""Tests for sspwd.storage.icon_cache — targets near-100 % line coverage."""
from __future__ import annotations

import io
import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import sspwd.storage.icon_cache as ic


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_response(body: bytes, content_type: str = "image/svg+xml") -> MagicMock:
    """Build a mock object that mimics what urllib.request.urlopen returns."""
    resp = MagicMock()
    resp.read.return_value = body
    resp.headers.get.return_value = content_type
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


SVG_BYTES = b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>'
PNG_1PX   = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


# ---------------------------------------------------------------------------
# _hash_key
# ---------------------------------------------------------------------------

class TestHashKey:
    def test_deterministic(self) -> None:
        assert ic._hash_key("iconify", "mdi:home") == ic._hash_key("iconify", "mdi:home")

    def test_different_type(self) -> None:
        assert ic._hash_key("iconify", "x") != ic._hash_key("url", "x")

    def test_length_20(self) -> None:
        assert len(ic._hash_key("url", "http://example.com")) == 20


# ---------------------------------------------------------------------------
# _ext_from_url
# ---------------------------------------------------------------------------

class TestExtFromUrl:
    def test_png(self) -> None:
        assert ic._ext_from_url("https://example.com/logo.png") == ".png"

    def test_svg(self) -> None:
        assert ic._ext_from_url("https://example.com/icon.svg") == ".svg"

    def test_jpg(self) -> None:
        assert ic._ext_from_url("https://example.com/photo.jpg") == ".jpg"

    def test_webp(self) -> None:
        assert ic._ext_from_url("https://example.com/img.webp") == ".webp"

    def test_query_string_ignored(self) -> None:
        assert ic._ext_from_url("https://example.com/img.png?v=1&x=2") == ".png"

    def test_unknown_ext_returns_empty(self) -> None:
        assert ic._ext_from_url("https://example.com/image") == ""

    def test_html_ext_returns_empty(self) -> None:
        assert ic._ext_from_url("https://example.com/page.html") == ""

    def test_trailing_slash(self) -> None:
        # rstrip("/") means no suffix after strip
        assert ic._ext_from_url("https://example.com/img/") == ""


# ---------------------------------------------------------------------------
# _ext_from_content_type
# ---------------------------------------------------------------------------

class TestExtFromContentType:
    @pytest.mark.parametrize("ct,expected", [
        ("image/svg+xml",             ".svg"),
        ("image/png",                 ".png"),
        ("image/jpeg",                ".jpg"),
        ("image/webp",                ".webp"),
        ("image/gif",                 ".gif"),
        ("image/x-icon",              ".ico"),
        ("image/vnd.microsoft.icon",  ".ico"),
        ("image/svg+xml; charset=utf-8", ".svg"),  # with params
        ("IMAGE/PNG",                 ".png"),      # uppercase
        ("application/octet-stream",  ""),          # unknown
        ("",                          ""),          # empty
    ])
    def test_mapping(self, ct: str, expected: str) -> None:
        assert ic._ext_from_content_type(ct) == expected


# ---------------------------------------------------------------------------
# _fetch
# ---------------------------------------------------------------------------

class TestFetch:
    def test_returns_body_and_content_type(self) -> None:
        resp = _fake_response(SVG_BYTES, "image/svg+xml")
        with patch("urllib.request.urlopen", return_value=resp):
            body, ct = ic._fetch("https://example.com/icon.svg")
        assert body == SVG_BYTES
        assert ct == "image/svg+xml"

    def test_sets_user_agent(self) -> None:
        resp = _fake_response(b"data")
        with patch("urllib.request.urlopen", return_value=resp) as mock_open:
            ic._fetch("https://example.com/x")
        req = mock_open.call_args[0][0]
        assert req.get_header("User-agent") == ic._USER_AGENT

    def test_propagates_urlerror(self) -> None:
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            with pytest.raises(urllib.error.URLError):
                ic._fetch("https://example.com/icon.svg")


# ---------------------------------------------------------------------------
# _resize_raster
# ---------------------------------------------------------------------------

class TestResizeRaster:
    def test_no_pillow_returns_none(self) -> None:
        """When PIL is not importable, _resize_raster returns None."""
        with patch.dict(sys.modules, {"PIL": None, "PIL.Image": None}):
            result = ic._resize_raster(PNG_1PX)
        assert result is None

    def test_with_pillow_returns_png_bytes(self) -> None:
        """With PIL available, the output is valid PNG bytes."""
        pytest.importorskip("PIL")
        result = ic._resize_raster(PNG_1PX, size=64)
        assert result is not None
        assert result[:4] == b"\x89PNG"

    def test_resize_clamps_to_size(self) -> None:
        """Thumbnail size is respected (output ≤ requested size)."""
        pytest.importorskip("PIL")
        from PIL import Image
        result = ic._resize_raster(PNG_1PX, size=32)
        assert result is not None
        img = Image.open(io.BytesIO(result))
        assert img.width <= 32
        assert img.height <= 32


# ---------------------------------------------------------------------------
# cache_iconify
# ---------------------------------------------------------------------------

class TestCacheIconify:
    def test_malformed_value_no_colon(self, tmp_path: Path) -> None:
        result = ic.cache_iconify("mdi-home", tmp_path)
        assert result is None

    def test_already_cached_skips_download(self, tmp_path: Path) -> None:
        """If the file already exists on disk, no download is attempted."""
        filename = f"iconify_{ic._hash_key('iconify', 'mdi:home')}.svg"
        (tmp_path / filename).write_bytes(SVG_BYTES)

        with patch("sspwd.storage.icon_cache._fetch") as mock_fetch:
            result = ic.cache_iconify("mdi:home", tmp_path)

        mock_fetch.assert_not_called()
        assert result == filename

    def test_successful_download(self, tmp_path: Path) -> None:
        with patch("sspwd.storage.icon_cache._fetch", return_value=(SVG_BYTES, "image/svg+xml")):
            result = ic.cache_iconify("mdi:home", tmp_path)

        assert result is not None
        assert result.startswith("iconify_")
        assert result.endswith(".svg")
        assert (tmp_path / result).read_bytes() == SVG_BYTES

    def test_fetch_exception_returns_none(self, tmp_path: Path) -> None:
        with patch("sspwd.storage.icon_cache._fetch", side_effect=OSError("net error")):
            result = ic.cache_iconify("mdi:home", tmp_path)
        assert result is None

    def test_iconify_404_body_returns_none(self, tmp_path: Path) -> None:
        """Iconify responds with literal b'404' for unknown icons."""
        with patch("sspwd.storage.icon_cache._fetch", return_value=(b"404", "text/plain")):
            result = ic.cache_iconify("mdi:nonexistent-icon-xyz", tmp_path)
        assert result is None

    def test_empty_body_returns_none(self, tmp_path: Path) -> None:
        with patch("sspwd.storage.icon_cache._fetch", return_value=(b"", "image/svg+xml")):
            result = ic.cache_iconify("mdi:home", tmp_path)
        assert result is None

    def test_non_xml_body_returns_none(self, tmp_path: Path) -> None:
        with patch("sspwd.storage.icon_cache._fetch", return_value=(b"not svg at all", "image/svg+xml")):
            result = ic.cache_iconify("mdi:home", tmp_path)
        assert result is None

    def test_collection_name_split(self, tmp_path: Path) -> None:
        """Colons in the name part (e.g. 'fa:arrow:right') should still work."""
        with patch("sspwd.storage.icon_cache._fetch", return_value=(SVG_BYTES, "image/svg+xml")) as mock_fetch:
            ic.cache_iconify("fa:arrow-right", tmp_path)
        called_url = mock_fetch.call_args[0][0]
        assert "fa/arrow-right.svg" in called_url


# ---------------------------------------------------------------------------
# cache_url
# ---------------------------------------------------------------------------

class TestCacheUrl:
    def test_local_api_path_skipped(self, tmp_path: Path) -> None:
        assert ic.cache_url("/api/v1/icons/abc.png", tmp_path) is None

    def test_local_icons_path_skipped(self, tmp_path: Path) -> None:
        assert ic.cache_url("/icons/abc.svg", tmp_path) is None

    def test_already_cached_returns_existing(self, tmp_path: Path) -> None:
        key      = ic._hash_key("url", "https://example.com/logo.png")
        filename = f"url_{key}.png"
        (tmp_path / filename).write_bytes(b"existing")

        with patch("sspwd.storage.icon_cache._fetch") as mock_fetch:
            result = ic.cache_url("https://example.com/logo.png", tmp_path)

        mock_fetch.assert_not_called()
        assert result == filename

    def test_svg_saved_as_svg(self, tmp_path: Path) -> None:
        with patch("sspwd.storage.icon_cache._fetch", return_value=(SVG_BYTES, "image/svg+xml")):
            result = ic.cache_url("https://example.com/icon.svg", tmp_path)

        assert result is not None
        assert result.endswith(".svg")
        assert (tmp_path / result).read_bytes() == SVG_BYTES

    def test_svg_detected_from_content_type(self, tmp_path: Path) -> None:
        """URL has no useful extension but Content-Type says SVG."""
        with patch("sspwd.storage.icon_cache._fetch", return_value=(SVG_BYTES, "image/svg+xml")):
            result = ic.cache_url("https://example.com/icon", tmp_path)

        assert result is not None
        assert result.endswith(".svg")

    def test_svg_detected_from_content_type_substring(self, tmp_path: Path) -> None:
        """content_type containing 'svg' without exact match."""
        with patch("sspwd.storage.icon_cache._fetch", return_value=(SVG_BYTES, "image/svg+xml; charset=utf-8")):
            result = ic.cache_url("https://example.com/icon", tmp_path)

        assert result is not None
        assert result.endswith(".svg")

    def test_png_without_pillow_saved_raw(self, tmp_path: Path) -> None:
        """Without Pillow, raw bytes are saved with the detected extension."""
        with patch("sspwd.storage.icon_cache._fetch", return_value=(PNG_1PX, "image/png")):
            with patch("sspwd.storage.icon_cache._resize_raster", return_value=None):
                result = ic.cache_url("https://example.com/logo.png", tmp_path)

        assert result is not None
        assert result.endswith(".png")
        assert (tmp_path / result).read_bytes() == PNG_1PX

    def test_png_with_pillow_saved_resized(self, tmp_path: Path) -> None:
        """With Pillow, the resized PNG bytes are written."""
        fake_resized = b"\x89PNGresized"
        with patch("sspwd.storage.icon_cache._fetch", return_value=(PNG_1PX, "image/png")):
            with patch("sspwd.storage.icon_cache._resize_raster", return_value=fake_resized):
                result = ic.cache_url("https://example.com/logo.png", tmp_path)

        assert result is not None
        assert result.endswith(".png")
        assert (tmp_path / result).read_bytes() == fake_resized

    def test_unknown_ext_falls_back_to_png(self, tmp_path: Path) -> None:
        """No ct_ext, no url_ext → uses .png as default extension."""
        with patch("sspwd.storage.icon_cache._fetch", return_value=(PNG_1PX, "application/octet-stream")):
            with patch("sspwd.storage.icon_cache._resize_raster", return_value=None):
                result = ic.cache_url("https://example.com/notype", tmp_path)

        assert result is not None
        assert result.endswith(".png")

    def test_fetch_failure_returns_none(self, tmp_path: Path) -> None:
        with patch("sspwd.storage.icon_cache._fetch", side_effect=OSError("unreachable")):
            result = ic.cache_url("https://example.com/logo.png", tmp_path)
        assert result is None

    def test_empty_body_returns_none(self, tmp_path: Path) -> None:
        with patch("sspwd.storage.icon_cache._fetch", return_value=(b"", "image/png")):
            result = ic.cache_url("https://example.com/empty.png", tmp_path)
        assert result is None

    def test_webp_url_ext_used_when_no_ct(self, tmp_path: Path) -> None:
        """.webp in URL, no recognised Content-Type — url_ext is used."""
        with patch("sspwd.storage.icon_cache._fetch", return_value=(b"\x00webp", "application/octet-stream")):
            with patch("sspwd.storage.icon_cache._resize_raster", return_value=None):
                result = ic.cache_url("https://example.com/img.webp", tmp_path)
        assert result is not None
        assert result.endswith(".webp")


# ---------------------------------------------------------------------------
# cache_icon (router)
# ---------------------------------------------------------------------------

class TestCacheIcon:
    def test_iconify_routed(self, tmp_path: Path) -> None:
        with patch("sspwd.storage.icon_cache.cache_iconify", return_value="iconify_abc.svg") as mock:
            result = ic.cache_icon("iconify", "mdi:home", tmp_path)
        mock.assert_called_once_with("mdi:home", tmp_path)
        assert result == "iconify_abc.svg"

    def test_url_routed(self, tmp_path: Path) -> None:
        with patch("sspwd.storage.icon_cache.cache_url", return_value="url_abc.png") as mock:
            result = ic.cache_icon("url", "https://example.com/logo.png", tmp_path)
        mock.assert_called_once_with("https://example.com/logo.png", tmp_path)
        assert result == "url_abc.png"

    def test_letter_returns_none(self, tmp_path: Path) -> None:
        result = ic.cache_icon("letter", "A", tmp_path)
        assert result is None

    def test_unknown_type_returns_none(self, tmp_path: Path) -> None:
        result = ic.cache_icon("unknown", "x", tmp_path)
        assert result is None
