"""Bridge to the lms CLI that ships with LM Studio.

Provides a typed, gracefully-degrading interface to ``lms`` subprocess calls.
All public functions return ``None`` or empty collections when ``lms`` is not
on PATH or a subprocess call fails, so callers never need to handle
``FileNotFoundError`` or ``subprocess.SubprocessError``.

Typical usage::

    from lmcode.lms_bridge import is_available, list_loaded_models

    if is_available():
        models = list_loaded_models()
        if models:
            print(models[0].identifier)

The ``lms`` binary ships with LM Studio but is only added to PATH after the
user runs ``lmstudio install-cli`` (or the equivalent for their OS).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field

# Subprocess timeout in seconds — short because these are local CLI calls.
_TIMEOUT: int = 5


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class LoadedModel:
    """Metadata for a model currently loaded in LM Studio.

    Field names mirror the ``lms ps --json`` output keys.  Unknown keys
    returned by future lms versions are silently ignored.
    """

    identifier: str
    architecture: str | None = None
    size_bytes: int | None = None
    context_length: int | None = None
    model_type: str | None = None  # "llm" | "embedding"
    extra: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> LoadedModel:
        """Build a LoadedModel from a raw ``lms ps --json`` entry."""
        return cls(
            identifier=str(data.get("identifier", "")),
            architecture=_str_or_none(data.get("architecture")),
            size_bytes=_int_or_none(data.get("sizeBytes")),
            context_length=_int_or_none(data.get("contextLength")),
            model_type=_str_or_none(data.get("type")),
            extra={
                k: v
                for k, v in data.items()
                if k not in {"identifier", "architecture", "sizeBytes", "contextLength", "type"}
            },
        )

    def format_size(self) -> str:
        """Return a human-readable size string like '4.5 GB' or '' if unknown."""
        if self.size_bytes is None:
            return ""
        gb = self.size_bytes / (1024**3)
        return f"{gb:.1f} GB"

    def format_context(self) -> str:
        """Return a human-readable context length like '32k ctx' or '' if unknown."""
        if self.context_length is None:
            return ""
        k = self.context_length / 1000
        return f"{k:.0f}k ctx"


@dataclass
class DownloadedModel:
    """Metadata for a model file present on disk (from ``lms ls --json``)."""

    path: str
    identifier: str | None = None
    architecture: str | None = None
    size_bytes: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> DownloadedModel:
        """Build a DownloadedModel from a raw ``lms ls --json`` entry."""
        return cls(
            path=str(data.get("path", "")),
            identifier=_str_or_none(data.get("identifier")),
            architecture=_str_or_none(data.get("architecture")),
            size_bytes=_int_or_none(data.get("sizeBytes")),
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_available() -> bool:
    """Return True if the ``lms`` binary is on PATH.

    Does not verify whether LM Studio is running — only checks that the CLI
    tool is installed.
    """
    return shutil.which("lms") is not None


def list_loaded_models() -> list[LoadedModel]:
    """Return all models currently loaded in LM Studio.

    Calls ``lms ps --json`` and parses the output.  Returns an empty list
    when ``lms`` is absent, the command fails, or no models are loaded.
    """
    raw = _run_json(["lms", "ps", "--json"])
    if not isinstance(raw, list):
        return []
    return [LoadedModel.from_dict(item) for item in raw if isinstance(item, dict)]


def list_downloaded_models() -> list[DownloadedModel]:
    """Return all models downloaded to disk.

    Calls ``lms ls --json``.  Returns an empty list on any failure.
    """
    raw = _run_json(["lms", "ls", "--json"])
    if not isinstance(raw, list):
        return []
    return [DownloadedModel.from_dict(item) for item in raw if isinstance(item, dict)]


def stream_model_log() -> subprocess.Popen[str] | None:
    """Start streaming model I/O logs from LM Studio.

    Calls ``lms log stream --source model --filter input,output --json`` and
    returns the ``Popen`` object.  The caller is responsible for reading
    ``proc.stdout`` line-by-line (each line is a JSON object) and calling
    ``proc.terminate()`` when done.

    Returns ``None`` when ``lms`` is not available or the process cannot be
    started.

    Example::

        proc = stream_model_log()
        if proc and proc.stdout:
            for line in proc.stdout:
                event = json.loads(line)
                print(event)
            proc.terminate()
    """
    if not is_available():
        return None
    try:
        return subprocess.Popen(
            ["lms", "log", "stream", "--source", "model", "--filter", "input,output", "--json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return None


def suggest_load_commands(model_name: str = "Qwen2.5-Coder-7B-Instruct") -> list[str]:
    """Return the shell commands a user should run to download and load a model.

    Does not execute anything — returns strings for display only.  Useful
    when lmcode starts but no model is loaded.

    Example::

        for cmd in suggest_load_commands():
            print(f"  {cmd}")
    """
    quant = "q4_k_m"
    return [
        f"lms get {model_name}@{quant}",
        f"lms load {model_name}",
        "lms ps",
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_json(cmd: list[str]) -> object:
    """Run *cmd*, parse stdout as JSON, return the result or None on failure.

    Returns ``None`` when ``lms`` is absent, the command exits non-zero,
    times out, or the output is not valid JSON.
    """
    if not is_available():
        return None
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
        return json.loads(result.stdout)
    except (subprocess.SubprocessError, subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None


def _str_or_none(value: object) -> str | None:
    """Return *value* as a string, or None if it is None or empty."""
    if value is None:
        return None
    s = str(value)
    return s if s else None


def _int_or_none(value: object) -> int | None:
    """Return *value* as an int, or None if it cannot be converted."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
