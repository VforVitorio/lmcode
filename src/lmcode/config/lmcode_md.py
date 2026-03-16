"""Find and read LMCODE.md files walking up the directory tree."""

from __future__ import annotations

from pathlib import Path

LMCODE_FILENAME = "LMCODE.md"


def find_lmcode_md(start: Path | None = None) -> list[Path]:
    """
    Walk up from `start` (default: cwd) and collect all LMCODE.md files found.
    Returns them ordered from root → closest, so inner files take precedence.
    """
    current = (start or Path.cwd()).resolve()
    found: list[Path] = []
    while True:
        candidate = current / LMCODE_FILENAME
        if candidate.exists():
            found.append(candidate)
        parent = current.parent
        if parent == current:
            break
        current = parent
    return list(reversed(found))


def read_lmcode_md(start: Path | None = None) -> str | None:
    """
    Return the combined content of all LMCODE.md files found up the tree.
    Returns None if no LMCODE.md is found.
    """
    files = find_lmcode_md(start)
    if not files:
        return None
    parts = []
    for f in files:
        parts.append(f"# From {f}\n\n{f.read_text(encoding='utf-8')}")
    return "\n\n---\n\n".join(parts)
