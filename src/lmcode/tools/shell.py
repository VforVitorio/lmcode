"""Shell tool available to the agent: run_shell.

WARNING: Executing arbitrary shell commands is inherently dangerous.
This module is intentionally limited and should only be used in trusted,
sandboxed environments.  Never expose this tool to untrusted input.
"""

from __future__ import annotations

import subprocess

from lmcode.tools.registry import register

# Maximum characters returned from a single command execution.
_MAX_OUTPUT_CHARS = 10_000

# Suffix appended when output is truncated.
_TRUNCATION_SUFFIX = "\n[truncated]"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _truncate(text: str) -> str:
    """Truncate *text* to ``_MAX_OUTPUT_CHARS``, appending a notice if cut.

    Returns the original string unchanged when it fits within the limit.
    """
    if len(text) <= _MAX_OUTPUT_CHARS:
        return text
    return text[:_MAX_OUTPUT_CHARS] + _TRUNCATION_SUFFIX


def _combine_output(stdout: str, stderr: str) -> str:
    """Combine *stdout* and *stderr* into a single string.

    *stderr* is prefixed with ``[stderr]`` so the caller can distinguish the
    two streams when both are non-empty.
    """
    parts: list[str] = []
    if stdout:
        parts.append(stdout)
    if stderr:
        parts.append(f"[stderr]\n{stderr}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# run_shell
# ---------------------------------------------------------------------------


@register
def run_shell(command: str, timeout: int = 30) -> str:
    """Execute a shell command and return its output (stdout + stderr).

    Use this tool whenever you need to:
    - Run a Python script (e.g. "python script.py").
    - Execute tests (e.g. "pytest", "npm test").
    - Run git commands (e.g. "git status", "git diff").
    - Install packages (e.g. "pip install X", "npm install").
    - List files, check output, or perform any terminal operation.

    Returns the combined stdout and stderr. Returns an error string on
    failure or a timeout message if the command exceeds the time limit.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            timeout=timeout,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired:
        return f"command timed out after {timeout}s"
    except OSError as exc:
        return f"error: {exc}"

    combined = _combine_output(result.stdout, result.stderr)
    return _truncate(combined)
