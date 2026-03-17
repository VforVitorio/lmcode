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
    """Execute *command* in a system shell and return its output.

    WARNING: This tool runs arbitrary shell commands with the same privileges
    as the lmcode process.  It must only be used in trusted environments.
    Never pass unsanitised user input directly to this function.

    Uses ``subprocess.run`` with ``shell=True``, so the full shell feature set
    (pipes, redirects, environment variables) is available.

    Args:
        command: The shell command to execute.
        timeout: Maximum seconds to wait before killing the process (default 30).

    Returns:
        Combined stdout and stderr (stderr prefixed with ``[stderr]``), capped
        at ``_MAX_OUTPUT_CHARS`` characters.  Returns a timeout message if the
        process does not finish within *timeout* seconds.  Returns an
        ``"error: …"`` string on unexpected OS-level failures.
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
