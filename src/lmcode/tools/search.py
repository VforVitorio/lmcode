"""Code-search tool available to the agent: search_code.

Uses ripgrep (``rg``) when available for speed; falls back to a pure-Python
``re`` walk when ripgrep is not installed.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from lmcode.tools.registry import register

# Maximum number of match lines returned.
_MAX_RESULTS = 200

# Directory names that are never searched.
_SKIP_DIRS: frozenset[str] = frozenset({".git", "__pycache__", ".venv"})


# ---------------------------------------------------------------------------
# ripgrep helpers
# ---------------------------------------------------------------------------


def _rg_available() -> bool:
    """Return True if the ``rg`` binary is on PATH."""
    try:
        subprocess.run(
            ["rg", "--version"],
            capture_output=True,
            check=True,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _search_with_rg(pattern: str, path: str, file_glob: str) -> list[str]:
    """Run ripgrep and return up to ``_MAX_RESULTS`` ``path:line: content`` strings.

    Skips ``.git``, ``__pycache__``, and ``.venv`` via ``--glob`` exclusions.
    """
    cmd = [
        "rg",
        "--line-number",
        "--glob",
        file_glob,
        "--glob",
        "!.git/**",
        "--glob",
        "!__pycache__/**",
        "--glob",
        "!.venv/**",
        "--max-count",
        str(_MAX_RESULTS),
        pattern,
        path,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
    except OSError:
        return []

    lines = result.stdout.splitlines()
    return lines[:_MAX_RESULTS]


# ---------------------------------------------------------------------------
# Pure-Python fallback helpers
# ---------------------------------------------------------------------------


def _should_skip(parts: tuple[str, ...]) -> bool:
    """Return True if any component of *parts* is in the skip set."""
    return any(part in _SKIP_DIRS for part in parts)


def _iter_candidate_files(root: Path, file_glob: str):
    """Yield Path objects under *root* matching *file_glob*, skipping ignored dirs."""
    for p in root.rglob(file_glob):
        if p.is_file() and not _should_skip(p.parts):
            yield p


def _search_file_py(file_path: Path, compiled: re.Pattern[str], root: Path) -> list[str]:
    """Search *file_path* for lines matching *compiled* and return formatted hits.

    Each hit is formatted as ``relative_path:lineno: content``.  Skips files
    that cannot be decoded as UTF-8.
    """
    try:
        text = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    hits: list[str] = []
    try:
        rel = str(file_path.relative_to(root))
    except ValueError:
        rel = str(file_path)

    for lineno, line in enumerate(text.splitlines(), start=1):
        if compiled.search(line):
            hits.append(f"{rel}:{lineno}: {line}")
    return hits


def _search_with_python(pattern: str, path: str, file_glob: str) -> list[str]:
    """Walk the directory tree with ``re`` and return matching lines.

    Falls back gracefully if the pattern is an invalid regex.
    """
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        return [f"error: invalid regex pattern: {exc}"]

    root = Path(path).expanduser().resolve()
    results: list[str] = []

    for file_path in _iter_candidate_files(root, file_glob):
        results.extend(_search_file_py(file_path, compiled, root))
        if len(results) >= _MAX_RESULTS:
            break

    return results[:_MAX_RESULTS]


# ---------------------------------------------------------------------------
# search_code
# ---------------------------------------------------------------------------


@register
def search_code(pattern: str, path: str = ".", file_glob: str = "**/*") -> str:
    """Search *path* for lines matching the regex *pattern*.

    Prefers ripgrep (``rg``) when available on PATH; otherwise uses a
    pure-Python ``re`` walk.  Either way, ``.git/``, ``__pycache__/``, and
    ``.venv/`` are excluded.

    Args:
        pattern:   Regular-expression pattern to search for.
        path:      Root directory to search (default: current directory).
        file_glob: Glob pattern to restrict which files are searched
                   (default: ``**/*``, all files).

    Returns:
        Newline-joined ``path:line: content`` strings, capped at
        ``_MAX_RESULTS`` entries.  Returns ``"(no matches found)"`` when
        nothing matched, or an ``"error: …"`` string on failure.
    """
    root = Path(path).expanduser().resolve()

    if not root.exists():
        return f"error: path does not exist: {path}"
    if not root.is_dir():
        return f"error: path is not a directory: {path}"

    if _rg_available():
        matches = _search_with_rg(pattern, str(root), file_glob)
    else:
        matches = _search_with_python(pattern, str(root), file_glob)

    if not matches:
        return "(no matches found)"

    return "\n".join(matches)
