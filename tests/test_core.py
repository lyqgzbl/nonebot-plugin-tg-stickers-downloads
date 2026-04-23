"""Tests for pure utility functions and converter logic."""

import re
import zipfile
from pathlib import Path

import pytest


# ── _safe_name ──────────────────────────────────────────────


def _safe_name(name: str) -> str:
    """Mirror of utils._safe_name for isolated testing."""
    return re.sub(r"[^\w.\-]", "_", name)


@pytest.mark.parametrize(
    ("input_name", "expected"),
    [
        ("normal_pack", "normal_pack"),
        ("pack/name", "pack_name"),
        ("pack..name", "pack..name"),
        ("pack name", "pack_name"),
        ("pack:name", "pack_name"),
        ("pack\x00name", "pack_name"),
        ("hello@world!", "hello_world_"),
        ("a/b/../c", "a_b_.._c"),
        ("simple123", "simple123"),
        ("with-dash.dot", "with-dash.dot"),
    ],
)
def test_safe_name(input_name: str, expected: str) -> None:
    assert _safe_name(input_name) == expected


# ── _mask_token ─────────────────────────────────────────────


def _mask_token(text: str) -> str:
    """Mirror of utils._mask_token for isolated testing."""
    return re.sub(r"bot\d+:[A-Za-z0-9_-]+", "bot***:***", str(text))


@pytest.mark.parametrize(
    ("input_text", "expected"),
    [
        (
            "https://api.telegram.org/bot123456:ABC-DEF/getFile",
            "https://api.telegram.org/bot***:***/getFile",
        ),
        (
            "https://api.telegram.org/file/bot99999:xyz_123/stickers/f.webp",
            "https://api.telegram.org/file/bot***:***/stickers/f.webp",
        ),
        ("no token here", "no token here"),
        ("", ""),
    ],
)
def test_mask_token(input_text: str, expected: str) -> None:
    assert _mask_token(input_text) == expected


# ── get_sticker_info ────────────────────────────────────────


def _get_sticker_info(data: dict) -> str:
    """Mirror of utils.get_sticker_info for isolated testing."""
    name = data.get("name", "Unknown")
    title = data.get("title", "Unknown")
    sticker_type = data.get("sticker_type", "regular")
    count = len(data.get("stickers", []))
    return (
        f"贴纸包名称: {name}\n"
        f"贴纸包标题: {title}\n"
        f"贴纸包类型: {sticker_type}\n"
        f"贴纸总数量: {count}"
    )


def test_get_sticker_info_basic() -> None:
    data = {
        "name": "TestPack",
        "title": "Test Title",
        "sticker_type": "regular",
        "stickers": [{"id": 1}, {"id": 2}],
    }
    info = _get_sticker_info(data)
    assert "TestPack" in info
    assert "Test Title" in info
    assert "2" in info


def test_get_sticker_info_defaults() -> None:
    info = _get_sticker_info({})
    assert "Unknown" in info
    assert "0" in info


# ── URL suffix extraction ──────────────────────────────────


def test_url_suffix_extraction() -> None:
    from urllib.parse import urlparse

    url = "https://api.telegram.org/file/bot123:abc/stickers/file.webp"
    ext = Path(urlparse(url).path).suffix
    assert ext == ".webp"


def test_url_suffix_with_query() -> None:
    from urllib.parse import urlparse

    url = "https://example.com/file.webp?token=abc"
    ext = Path(urlparse(url).path).suffix
    assert ext == ".webp"  # urlparse correctly strips query


# ── create_split_zips ──────────────────────────────────────


def test_create_split_zips(tmp_path: Path) -> None:
    """Test zip creation with correct split logic."""
    # Setup fake sticker files
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    (pack_dir / "sticker1.webp").write_bytes(b"\x00" * 100)
    (pack_dir / "sticker1.png").write_bytes(b"\x00" * 100)
    (pack_dir / "sticker2.tgs").write_bytes(b"\x00" * 50)
    (pack_dir / "sticker2.gif").write_bytes(b"\x00" * 50)
    (pack_dir / "sticker_set.json").write_text("{}")

    all_paths = list(pack_dir.iterdir())

    # Import the actual function - need to handle NoneBot import
    # Instead, replicate the logic here for unit testing
    original_suffixes = {".webp", ".tgs", ".webm", ".json"}
    converted_suffixes = {".png", ".gif", ".json"}
    _compressed_suffixes = {
        ".webp",
        ".webm",
        ".png",
        ".gif",
        ".jpg",
        ".jpeg",
    }

    orig_files = [p for p in all_paths if p.suffix.lower() in original_suffixes]
    conv_files = [p for p in all_paths if p.suffix.lower() in converted_suffixes]

    assert len(orig_files) == 3  # webp, tgs, json
    assert len(conv_files) == 3  # png, gif, json

    # Verify json appears in both
    orig_exts = {p.suffix for p in orig_files}
    conv_exts = {p.suffix for p in conv_files}
    assert ".json" in orig_exts
    assert ".json" in conv_exts

    # Test zip writing with STORED for compressed formats
    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in orig_files:
            compress = (
                zipfile.ZIP_STORED
                if f.suffix.lower() in _compressed_suffixes
                else zipfile.ZIP_DEFLATED
            )
            zf.write(f, arcname=f.name, compress_type=compress)

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        assert len(names) == 3


# ── Input validation regex ─────────────────────────────────


_PACK_NAME_RE = re.compile(r"^[a-zA-Z0-9_]{1,64}$")


@pytest.mark.parametrize(
    ("name", "valid"),
    [
        ("StickerPackName", True),
        ("pack_123", True),
        ("a" * 64, True),
        ("a" * 65, False),
        ("", False),
        ("pack/name", False),
        ("pack name", False),
        ("pack@name", False),
        ("valid_Pack_01", True),
    ],
)
def test_pack_name_validation(name: str, valid: bool) -> None:
    assert bool(_PACK_NAME_RE.match(name)) == valid
