"""File-system tools available to the agent: read, write, list."""

from __future__ import annotations

from pathlib import Path

from lmcode.config.settings import get_settings
from lmcode.tools.registry import register

# Number of bytes sampled to decide whether a file is binary.
_BINARY_SAMPLE_BYTES = 8_192


def _resolve_path(path: str) -> Path:
    """Resolve *path* to an absolute Path and validate it is a regular file.

    Raises:
        FileNotFoundError: if the path does not exist.
        IsADirectoryError: if the path points to a directory.
    """
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"No such file: {path}")
    if resolved.is_dir():
        raise IsADirectoryError(f"Path is a directory, not a file: {path}")
    return resolved


def _is_binary(path: Path) -> bool:
    """Return True if *path* looks like a binary file.

    Reads the first ``_BINARY_SAMPLE_BYTES`` bytes and checks for null bytes,
    which are a reliable indicator of non-text content.
    """
    sample = path.read_bytes()[:_BINARY_SAMPLE_BYTES]
    return b"\x00" in sample


def _read_text(path: Path, max_bytes: int) -> tuple[str, bool]:
    """Read the text content of *path*, capped at *max_bytes*.

    Tries UTF-8 first, then falls back to latin-1 (which never fails).

    Returns:
        A ``(content, truncated)`` tuple where *truncated* is True when the
        file was larger than *max_bytes* and only the first chunk was returned.
    """
    raw = path.read_bytes()
    truncated = len(raw) > max_bytes
    chunk = raw[:max_bytes]

    try:
        text = chunk.decode("utf-8")
    except UnicodeDecodeError:
        text = chunk.decode("latin-1")

    return text, truncated


@register
def read_file(path: str) -> str:
    """Read and return the text contents of a file at *path*.

    Respects the ``agent.max_file_bytes`` setting (default 100 KB).
    Returns an error message string instead of raising on failure so the
    agent loop can handle it gracefully.
    """
    max_bytes = get_settings().agent.max_file_bytes

    try:
        resolved = _resolve_path(path)
    except (FileNotFoundError, IsADirectoryError) as exc:
        return f"error: {exc}"

    if _is_binary(resolved):
        return f"error: {path} appears to be a binary file and cannot be read as text"

    content, truncated = _read_text(resolved, max_bytes)

    if truncated:
        file_size = resolved.stat().st_size
        size_str = f"{file_size // 1024} KB" if file_size >= 1024 else f"{file_size} B"
        limit_str = f"{max_bytes // 1024} KB" if max_bytes >= 1024 else f"{max_bytes} B"
        content += (
            f"\n\n[... truncated — file is {size_str}, "
            f"showing first {limit_str}. "
            f"Adjust agent.max_file_bytes in config to read more. "
            f"See issue #2 for token-aware limits. ...]"
        )

    return content
