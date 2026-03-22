"""Tests for src/lmcode/tools/filesystem.py — read_file, write_file, list_files and helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from lmcode.tools.filesystem import (
    _is_binary,
    _is_binary_extension,
    _read_text,
    _resolve_path,
    _should_skip,
    list_files,
    read_file,
    write_file,
)

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


# ---------------------------------------------------------------------------
# _is_binary_extension
# ---------------------------------------------------------------------------


def test_is_binary_extension_blocked() -> None:
    """Known binary extensions must be blocked."""
    assert _is_binary_extension("output.exe") is True
    assert _is_binary_extension("module.pyc") is True
    assert _is_binary_extension("image.PNG") is True  # case-insensitive


def test_is_binary_extension_allowed() -> None:
    """Text-file extensions must not be blocked."""
    assert _is_binary_extension("script.py") is False
    assert _is_binary_extension("README.txt") is False
    assert _is_binary_extension("config.toml") is False


# ---------------------------------------------------------------------------
# _should_skip
# ---------------------------------------------------------------------------


def test_should_skip_blocked_names() -> None:
    """Known skip-directory names must return True."""
    assert _should_skip(".git") is True
    assert _should_skip("__pycache__") is True
    assert _should_skip(".venv") is True


def test_should_skip_normal_names() -> None:
    """Regular directory names must not be skipped."""
    assert _should_skip("src") is False
    assert _should_skip("tests") is False


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------


def test_write_file_creates_file(tmp_path: Path) -> None:
    """Happy path: new file is created and byte count is returned."""
    target = tmp_path / "hello.txt"
    result = write_file(str(target), "hello world")
    assert target.read_text(encoding="utf-8") == "hello world"
    assert "wrote" in result
    assert "bytes" in result


def test_write_file_overwrites_existing(tmp_path: Path) -> None:
    """Calling write_file twice should overwrite the previous content."""
    target = tmp_path / "file.txt"
    write_file(str(target), "first")
    write_file(str(target), "second")
    assert target.read_text(encoding="utf-8") == "second"


def test_write_file_creates_parents(tmp_path: Path) -> None:
    """write_file must create intermediate directories automatically."""
    target = tmp_path / "a" / "b" / "c" / "deep.txt"
    write_file(str(target), "deep content")
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "deep content"


def test_write_file_refuses_binary_extension(tmp_path: Path) -> None:
    """Writing a .pyc file must return an error string."""
    result = write_file(str(tmp_path / "module.pyc"), "bytecode")
    assert result.startswith("error:")


def test_write_file_byte_count_in_result(tmp_path: Path) -> None:
    """Returned string must include the exact UTF-8 byte count."""
    content = "café"  # 5 UTF-8 bytes (é = 2 bytes)
    target = tmp_path / "unicode.txt"
    result = write_file(str(target), content)
    byte_count = len(content.encode("utf-8"))
    assert str(byte_count) in result


def test_write_file_unescape_literal_newlines(tmp_path: Path) -> None:
    """Content with literal \\n (two chars) but no real newlines is unescaped."""
    target = tmp_path / "escaped.py"
    # Simulate what a 7B model sometimes produces: JSON-escaped sequences
    escaped = "def foo():\\n    return 1\\n"
    write_file(str(target), escaped)
    written = target.read_text(encoding="utf-8")
    assert "\n" in written
    assert "\\n" not in written
    assert written == "def foo():\n    return 1\n"


def test_write_file_unescape_preserves_real_newlines(tmp_path: Path) -> None:
    """Content that already has real newlines is NOT unescaped."""
    target = tmp_path / "normal.py"
    normal = "def foo():\n    return 1\n"
    write_file(str(target), normal)
    assert target.read_text(encoding="utf-8") == normal


def test_write_file_unescape_tabs_and_quotes(tmp_path: Path) -> None:
    """Literal \\t and \\" sequences are also unescaped together with \\n."""
    target = tmp_path / "mixed.txt"
    escaped = 'key:\\t\\"value\\"\\nend'
    write_file(str(target), escaped)
    written = target.read_text(encoding="utf-8")
    assert written == 'key:\t"value"\nend'


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------


def test_list_files_basic(tmp_path: Path) -> None:
    """list_files returns relative paths of files under the given directory."""
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    result = list_files(str(tmp_path))
    assert "a.txt" in result
    assert "b.txt" in result


def test_list_files_pattern(tmp_path: Path) -> None:
    """list_files honours the glob pattern argument."""
    (tmp_path / "code.py").write_text("x = 1")
    (tmp_path / "notes.txt").write_text("notes")
    result = list_files(str(tmp_path), pattern="*.py")
    assert "code.py" in result
    assert "notes.txt" not in result


def test_list_files_skips_git(tmp_path: Path) -> None:
    """list_files must not include files inside .git directories."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main")
    (tmp_path / "real.py").write_text("# real")
    result = list_files(str(tmp_path))
    assert "real.py" in result
    assert ".git" not in result


def test_list_files_skips_pycache(tmp_path: Path) -> None:
    """list_files must not include files inside __pycache__ directories."""
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "mod.pyc").write_bytes(b"\x00")
    (tmp_path / "mod.py").write_text("pass")
    result = list_files(str(tmp_path))
    assert "__pycache__" not in result


def test_list_files_missing_path() -> None:
    """A path that does not exist returns an error string."""
    result = list_files("/nonexistent/path/xyz")
    assert result.startswith("error:")


def test_list_files_not_a_directory(tmp_path: Path) -> None:
    """Passing a file path instead of a directory returns an error string."""
    f = tmp_path / "file.txt"
    f.write_text("content")
    result = list_files(str(f))
    assert result.startswith("error:")


def test_list_files_empty_directory(tmp_path: Path) -> None:
    """An empty directory returns a no-files message."""
    result = list_files(str(tmp_path))
    assert "no files" in result


def test_list_files_cap(tmp_path: Path) -> None:
    """Results are capped at _LIST_FILES_MAX entries."""
    import lmcode.tools.filesystem as fs_mod

    original_max = fs_mod._LIST_FILES_MAX
    fs_mod._LIST_FILES_MAX = 3
    try:
        for i in range(10):
            (tmp_path / f"f{i}.txt").write_text(str(i))
        result = list_files(str(tmp_path))
        assert len(result.splitlines()) == 3
    finally:
        fs_mod._LIST_FILES_MAX = original_max
