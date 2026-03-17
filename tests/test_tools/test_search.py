"""Tests for src/lmcode/tools/search.py — search_code and helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from lmcode.tools.search import (
    _search_file_py,
    _search_with_python,
    _should_skip,
    search_code,
)

# ---------------------------------------------------------------------------
# _should_skip
# ---------------------------------------------------------------------------


def test_should_skip_git() -> None:
    """.git parts must be skipped."""
    assert _should_skip((".git",)) is True


def test_should_skip_pycache() -> None:
    """__pycache__ parts must be skipped."""
    assert _should_skip(("src", "__pycache__", "mod.cpython-312.pyc")) is True


def test_should_skip_venv() -> None:
    """.venv parts must be skipped."""
    assert _should_skip(("project", ".venv", "lib")) is True


def test_should_skip_normal() -> None:
    """Normal path parts must not be skipped."""
    assert _should_skip(("src", "lmcode", "tools", "search.py")) is False


# ---------------------------------------------------------------------------
# _search_file_py
# ---------------------------------------------------------------------------


def test_search_file_py_finds_match(tmp_path: Path) -> None:
    """Lines matching the pattern are returned in path:lineno: content format."""
    import re

    f = tmp_path / "code.py"
    f.write_text("x = 1\nfoo = 'bar'\nx = 2\n", encoding="utf-8")
    compiled = re.compile(r"foo")
    hits = _search_file_py(f, compiled, tmp_path)
    assert len(hits) == 1
    assert "foo" in hits[0]
    assert "2:" in hits[0]  # line 2


def test_search_file_py_no_match(tmp_path: Path) -> None:
    """No hits when pattern is absent from the file."""
    import re

    f = tmp_path / "empty.py"
    f.write_text("nothing here\n", encoding="utf-8")
    compiled = re.compile(r"ZZZNOTPRESENT")
    hits = _search_file_py(f, compiled, tmp_path)
    assert hits == []


def test_search_file_py_skips_binary(tmp_path: Path) -> None:
    """Files that cannot be decoded as UTF-8 are silently skipped."""
    import re

    f = tmp_path / "binary.bin"
    f.write_bytes(b"\xff\xfe\x00\x01")
    compiled = re.compile(r".")
    hits = _search_file_py(f, compiled, tmp_path)
    assert hits == []


# ---------------------------------------------------------------------------
# _search_with_python
# ---------------------------------------------------------------------------


def test_search_with_python_finds_pattern(tmp_path: Path) -> None:
    """Python fallback returns matches from multiple files."""
    (tmp_path / "a.py").write_text("def hello(): pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def world(): pass\n", encoding="utf-8")
    results = _search_with_python("def ", str(tmp_path), "*.py")
    assert len(results) == 2


def test_search_with_python_invalid_regex(tmp_path: Path) -> None:
    """An invalid regex returns an error string."""
    results = _search_with_python("[invalid(", str(tmp_path), "*")
    assert len(results) == 1
    assert results[0].startswith("error:")


def test_search_with_python_skips_git(tmp_path: Path) -> None:
    """Files inside .git are not searched."""
    git = tmp_path / ".git"
    git.mkdir()
    (git / "config").write_text("needle_in_git\n", encoding="utf-8")
    (tmp_path / "real.py").write_text("not here\n", encoding="utf-8")
    results = _search_with_python("needle_in_git", str(tmp_path), "**/*")
    assert results == []


# ---------------------------------------------------------------------------
# search_code (integration)
# ---------------------------------------------------------------------------


def test_search_code_missing_path() -> None:
    """Non-existent path returns an error string."""
    result = search_code("pattern", path="/nonexistent/xyz_path")
    assert result.startswith("error:")


def test_search_code_not_a_directory(tmp_path: Path) -> None:
    """Passing a file as path returns an error string."""
    f = tmp_path / "file.txt"
    f.write_text("content")
    result = search_code("content", path=str(f))
    assert result.startswith("error:")


def test_search_code_no_matches(tmp_path: Path) -> None:
    """No matches returns the '(no matches found)' message."""
    (tmp_path / "code.py").write_text("x = 1\n", encoding="utf-8")
    # Force Python fallback so test is deterministic regardless of rg presence
    with patch("lmcode.tools.search._rg_available", return_value=False):
        result = search_code("ZZZNOTPRESENT", path=str(tmp_path))
    assert result == "(no matches found)"


def test_search_code_returns_matches(tmp_path: Path) -> None:
    """Matching lines are returned in the expected format."""
    (tmp_path / "greet.py").write_text("print('hello')\n", encoding="utf-8")
    with patch("lmcode.tools.search._rg_available", return_value=False):
        result = search_code("hello", path=str(tmp_path))
    assert "hello" in result
    assert "greet.py" in result


def test_search_code_file_glob_filter(tmp_path: Path) -> None:
    """file_glob restricts which files are searched."""
    (tmp_path / "match.py").write_text("needle\n", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("needle\n", encoding="utf-8")
    with patch("lmcode.tools.search._rg_available", return_value=False):
        result = search_code("needle", path=str(tmp_path), file_glob="*.py")
    assert "match.py" in result
    assert "ignore.txt" not in result
