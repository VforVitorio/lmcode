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
            # ``lms ls --json`` uses ``modelKey``; older/future versions may use ``identifier``
            identifier=_str_or_none(data.get("identifier") or data.get("modelKey")),
            architecture=_str_or_none(data.get("architecture")),
            size_bytes=_int_or_none(data.get("sizeBytes")),
        )

    def load_name(self) -> str:
        """Return the name to pass to ``lms load``.

        Uses the model identifier when available.  Falls back to the filename
        without extension (e.g. ``qwen2.5-coder-7b-instruct-q4_k_m`` instead
        of ``qwen2.5-coder-7b-instruct-q4_k_m.gguf``).
        """
        if self.identifier:
            return self.identifier
        basename = self.path.replace("\\", "/").split("/")[-1]
        if basename.lower().endswith(".gguf"):
            return basename[:-5]
        return basename

    def format_size(self) -> str:
        """Return a human-readable size string like '4.5 GB' or '' if unknown."""
        if self.size_bytes is None:
            return ""
        gb = self.size_bytes / (1024**3)
        return f"{gb:.1f} GB"


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


def stream_model_log(stats: bool = False) -> subprocess.Popen[str] | None:
    """Start streaming model I/O logs from LM Studio.

    Calls ``lms log stream --source model --filter input,output --json`` and
    returns the ``Popen`` object.  The caller is responsible for reading
    ``proc.stdout`` line-by-line (each line is a JSON object) and calling
    ``proc.terminate()`` when done.

    If *stats* is True, appends the ``--stats`` flag to include token metrics.

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
        cmd = ["lms", "log", "stream", "--source", "model", "--filter", "input,output", "--json"]
        if stats:
            cmd.append("--stats")
        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return None


def load_model(
    identifier: str,
    gpu: str = "auto",
    context_length: int | None = None,
) -> bool:
    """Load a model into LM Studio via ``lms load``.

    Runs ``lms load <identifier> --yes [--gpu <gpu>]`` and waits up to 120 seconds
    for the process to complete (loading large models takes time).

    Args:
        identifier: Model identifier as shown by ``lms ls``.
        gpu: GPU offload strategy — ``"auto"``, ``"max"``, or a float string
            between ``"0.0"`` and ``"1.0"``.
        context_length: Optional override for the model's context window.

    Returns:
        ``True`` if ``lms load`` exited with code 0, ``False`` on any failure.
    """
    if not is_available():
        return False
    cmd = ["lms", "load", identifier, "--yes"]
    if gpu != "auto":
        cmd += ["--gpu", gpu]
    if context_length is not None:
        cmd += ["--context-length", str(context_length)]
    try:
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, subprocess.TimeoutExpired, OSError):
        return False


def import_model(path: str) -> bool:
    """Import an external model file (.gguf) into LM Studio via ``lms import``.

    Args:
        path: The filesystem path to the model file.

    Returns:
        ``True`` on success, ``False`` on any failure or when ``lms`` is absent.
    """
    if not is_available():
        return False
    try:
        result = subprocess.run(
            ["lms", "import", path],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, subprocess.TimeoutExpired, OSError):
        return False


def unload_model(identifier: str | None = None, all_models: bool = False) -> bool:
    """Unload a model (or all models) from LM Studio memory.

    Runs ``lms unload <identifier>`` or ``lms unload --all``.

    Args:
        identifier: Model identifier to unload.  Ignored when *all_models* is
            ``True``.
        all_models: If ``True``, unload every loaded model (``lms unload --all``).

    Returns:
        ``True`` on success, ``False`` on any failure or when ``lms`` is absent.
    """
    if not is_available():
        return False
    if all_models:
        cmd = ["lms", "unload", "--all"]
    elif identifier:
        cmd = ["lms", "unload", identifier]
    else:
        return False
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except (subprocess.SubprocessError, subprocess.TimeoutExpired, OSError):
        return False


def server_start(port: int | None = None) -> bool:
    """Start the LM Studio inference server via ``lms server start``.

    Blocks until the server is ready (the ``lms`` process exits) or the 30-second
    timeout is reached.

    Args:
        port: Optional port number to pass via ``--port``.

    Returns:
        ``True`` if the server started successfully, ``False`` on any failure.
    """
    if not is_available():
        return False
    cmd = ["lms", "server", "start"]
    if port is not None:
        cmd += ["--port", str(port)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except (subprocess.SubprocessError, subprocess.TimeoutExpired, OSError):
        return False


def server_stop() -> bool:
    """Stop the LM Studio inference server via ``lms server stop``.

    Returns:
        ``True`` on success, ``False`` on any failure or when ``lms`` is absent.
    """
    if not is_available():
        return False
    try:
        result = subprocess.run(
            ["lms", "server", "stop"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, subprocess.TimeoutExpired, OSError):
        return False


def daemon_up() -> bool:
    """Start LM Studio in headless (daemon) mode via ``lms daemon up``.

    Launches the LM Studio daemon which includes the inference server.
    The command returns once the daemon process has been started; callers
    should poll ``_probe_lmstudio()`` to wait until the server is reachable.

    Returns:
        ``True`` if the command exited cleanly, ``False`` on any failure.
    """
    if not is_available():
        return False
    try:
        result = subprocess.run(
            ["lms", "daemon", "up"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, subprocess.TimeoutExpired, OSError):
        return False


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
