"""File-system tools available to the agent: read, write, list."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from lmcode.config.settings import get_settings
from lmcode.tools.registry import register

# Number of bytes sampled to decide whether a file is binary.
_BINARY_SAMPLE_BYTES = 8_192

# File extensions that write_file refuses to create.
_BINARY_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".pyc",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".bin",
        ".obj",
        ".o",
        ".class",
        ".jar",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".7z",
        ".rar",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".ico",
        ".tiff",
        ".webp",
        ".mp3",
        ".mp4",
        ".wav",
        ".avi",
        ".mov",
        ".mkv",
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".db",
        ".sqlite",
        ".sqlite3",
    }
)

# Directory names skipped when listing files.
_SKIP_DIRS: frozenset[str] = frozenset({".git", "__pycache__", ".venv"})

# Maximum number of entries returned by list_files.
_LIST_FILES_MAX = 500


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
    """Read a file from disk and return its full text contents.

    Use this tool whenever you need to:
    - See what a file contains before editing or analysing it.
    - Verify the current state of a file.
    - Read source code, configs, or any text file.

    Always call this before writing to an existing file.
    Returns an error string (starting with "error:") if the file does
    not exist, is a directory, or is binary.
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


# ---------------------------------------------------------------------------
# Helpers for write_file
# ---------------------------------------------------------------------------


def _is_binary_extension(path: str) -> bool:
    """Return True if *path* has an extension on the binary blocklist.

    This guards against accidental writes to binary file types.
    """
    return Path(path).suffix.lower() in _BINARY_EXTENSIONS


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------


@register
def write_file(path: str, content: str) -> str:
    """Create or overwrite a file on disk with the given content.

    Use this tool whenever you need to:
    - Create a new file.
    - Edit or update an existing file (provide the full new content).
    - Save any code, configuration, or text to disk.

    Always call read_file first if the file already exists, so you can
    preserve any parts you are not changing.
    Creates parent directories automatically. Returns "wrote N bytes to
    path" on success, or an error string on failure.
    """
    if _is_binary_extension(path):
        ext = Path(path).suffix.lower()
        return f"error: refusing to write binary file type '{ext}': {path}"

    try:
        target = Path(path).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        encoded = content.encode("utf-8")
        target.write_bytes(encoded)
        return f"wrote {len(encoded)} bytes to {path}"
    except OSError as exc:
        return f"error: {exc}"


# ---------------------------------------------------------------------------
# Helpers for list_files
# ---------------------------------------------------------------------------


def _should_skip(part: str) -> bool:
    """Return True if a path component is in the skip-directory set."""
    return part in _SKIP_DIRS


def _iter_files(root: Path, pattern: str) -> Iterator[Path]:
    """Yield Path objects under *root* matching *pattern*, skipping ignored dirs.

    Skips any path whose components include a directory from ``_SKIP_DIRS``.
    """
    for p in root.rglob(pattern):
        if p.is_file() and not any(_should_skip(part) for part in p.parts):
            yield p


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------


@register
def list_files(path: str = ".", pattern: str = "*") -> str:
    """List files under *path* whose names match *pattern*.

    Uses ``pathlib.Path.rglob`` to walk the directory tree recursively.
    Skips ``.git/``, ``__pycache__/``, and ``.venv/`` directories.
    Results are relative to *path* and capped at ``_LIST_FILES_MAX`` entries.

    Returns:
        Newline-joined relative paths on success, or an ``"error: …"`` string
        if *path* does not exist or is not a directory.
    """
    root = Path(path).expanduser().resolve()

    if not root.exists():
        return f"error: path does not exist: {path}"
    if not root.is_dir():
        return f"error: path is not a directory: {path}"

    entries: list[str] = []
    for p in _iter_files(root, pattern):
        try:
            entries.append(str(p.relative_to(root)))
        except ValueError:
            entries.append(str(p))
        if len(entries) >= _LIST_FILES_MAX:
            break

    if not entries:
        return "(no files matched)"

    return "\n".join(entries)
