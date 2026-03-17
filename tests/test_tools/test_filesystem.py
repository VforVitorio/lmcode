"""Tests for src/lmcode/tools/filesystem.py — read_file and helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from lmcode.tools.filesystem import _is_binary, _read_text, _resolve_path, read_file


# ---------------------------------------------------------------------------
# _resolve_path
# ---------------------------------------------------------------------------


def test_resolve_path_returns_absolute(tmp_path: Path) -> None:
    """Resolved path must be absolute."""
    f = tmp_path / "hello.txt"
    f.write_text("hi")
    result = _resolve_path(str(f))
    assert result.is_absolute()


def test_resolve_path_missing_raises(tmp_path: Path) -> None:
    """FileNotFoundError for a path that does not exist."""
    with pytest.raises(FileNotFoundError):
        _resolve_path(str(tmp_path / "ghost.txt"))


def test_resolve_path_directory_raises(tmp_path: Path) -> None:
    """IsADirectoryError when the path is a directory."""
    with pytest.raises(IsADirectoryError):
        _resolve_path(str(tmp_path))


# ---------------------------------------------------------------------------
# _is_binary
# ---------------------------------------------------------------------------


def test_is_binary_text_file(tmp_path: Path) -> None:
    """Plain text files must not be detected as binary."""
    f = tmp_path / "code.py"
    f.write_text("print('hello')\n", encoding="utf-8")
    assert _is_binary(f) is False


def test_is_binary_binary_file(tmp_path: Path) -> None:
    """Files with null bytes must be detected as binary."""
    f = tmp_path / "data.bin"
    f.write_bytes(b"\x00\x01\x02\x03")
    assert _is_binary(f) is True


def test_is_binary_empty_file(tmp_path: Path) -> None:
    """Empty files have no null bytes — should not be considered binary."""
    f = tmp_path / "empty.txt"
    f.write_bytes(b"")
    assert _is_binary(f) is False


# ---------------------------------------------------------------------------
# _read_text
# ---------------------------------------------------------------------------


def test_read_text_full(tmp_path: Path) -> None:
    """Small file under limit: full content returned, truncated=False."""
    f = tmp_path / "small.txt"
    f.write_text("hello world", encoding="utf-8")
    content, truncated = _read_text(f, max_bytes=100)
    assert content == "hello world"
    assert truncated is False


def test_read_text_truncated(tmp_path: Path) -> None:
    """File larger than limit: content is cut, truncated=True."""
    f = tmp_path / "big.txt"
    f.write_bytes(b"a" * 200)
    content, truncated = _read_text(f, max_bytes=100)
    assert len(content) == 100
    assert truncated is True


def test_read_text_latin1_fallback(tmp_path: Path) -> None:
    """Files with invalid UTF-8 bytes must be decoded via latin-1."""
    f = tmp_path / "latin.txt"
    f.write_bytes(b"caf\xe9")  # 'café' in latin-1, invalid UTF-8
    content, _ = _read_text(f, max_bytes=100)
    assert "caf" in content


# ---------------------------------------------------------------------------
# read_file (integration — uses real settings default 100_000 bytes)
# ---------------------------------------------------------------------------


def test_read_file_returns_content(tmp_path: Path) -> None:
    """Happy path: existing text file returns its content."""
    f = tmp_path / "greet.txt"
    f.write_text("hello lmcode", encoding="utf-8")
    result = read_file(str(f))
    assert result == "hello lmcode"


def test_read_file_missing_returns_error(tmp_path: Path) -> None:
    """Missing file returns an error string, does not raise."""
    result = read_file(str(tmp_path / "nope.txt"))
    assert result.startswith("error:")


def test_read_file_directory_returns_error(tmp_path: Path) -> None:
    """Passing a directory returns an error string, does not raise."""
    result = read_file(str(tmp_path))
    assert result.startswith("error:")


def test_read_file_binary_returns_error(tmp_path: Path) -> None:
    """Binary file returns an error string, does not raise."""
    f = tmp_path / "img.bin"
    f.write_bytes(b"\x00\xff\x00\xff")
    result = read_file(str(f))
    assert result.startswith("error:")


def test_read_file_truncation_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Oversized file includes the truncation notice in the returned string."""
    import lmcode.tools.filesystem as fs_mod

    # Patch get_settings at the module level to return a tiny limit
    class _FakeAgent:
        max_file_bytes = 10

    class _FakeSettings:
        agent = _FakeAgent()

    monkeypatch.setattr(fs_mod, "get_settings", lambda: _FakeSettings())

    f = tmp_path / "huge.txt"
    f.write_text("a" * 100, encoding="utf-8")

    result = read_file(str(f))
    assert "truncated" in result
