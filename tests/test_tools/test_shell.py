"""Tests for src/lmcode/tools/shell.py — run_shell and helpers."""

from __future__ import annotations

import sys

from lmcode.tools.shell import _combine_output, _truncate, run_shell

# ---------------------------------------------------------------------------
# _truncate
# ---------------------------------------------------------------------------


def test_truncate_short_text_unchanged() -> None:
    """Text shorter than the limit must be returned unchanged."""
    text = "hello"
    assert _truncate(text) == text


def test_truncate_long_text_cut() -> None:
    """Text exceeding the limit must be cut and suffixed with [truncated]."""
    from lmcode.tools.shell import _MAX_OUTPUT_CHARS

    long_text = "x" * (_MAX_OUTPUT_CHARS + 100)
    result = _truncate(long_text)
    assert len(result) < len(long_text)
    assert result.endswith("[truncated]")


def test_truncate_exact_limit_unchanged() -> None:
    """Text exactly at the limit must not be truncated."""
    from lmcode.tools.shell import _MAX_OUTPUT_CHARS

    text = "a" * _MAX_OUTPUT_CHARS
    assert _truncate(text) == text


# ---------------------------------------------------------------------------
# _combine_output
# ---------------------------------------------------------------------------


def test_combine_output_stdout_only() -> None:
    """Only stdout present: no [stderr] label in result."""
    result = _combine_output("out text", "")
    assert result == "out text"
    assert "[stderr]" not in result


def test_combine_output_stderr_only() -> None:
    """Only stderr present: result must carry the [stderr] label."""
    result = _combine_output("", "err text")
    assert "[stderr]" in result
    assert "err text" in result


def test_combine_output_both() -> None:
    """Both streams present: both appear in the combined output."""
    result = _combine_output("stdout line", "stderr line")
    assert "stdout line" in result
    assert "[stderr]" in result
    assert "stderr line" in result


def test_combine_output_both_empty() -> None:
    """Both streams empty: result is an empty string."""
    assert _combine_output("", "") == ""


# ---------------------------------------------------------------------------
# run_shell
# ---------------------------------------------------------------------------


# Platform-agnostic echo commands
_ECHO_HELLO = "echo hello" if sys.platform != "win32" else "echo hello"


def test_run_shell_stdout_returned() -> None:
    """Output written to stdout must appear in the result."""
    result = run_shell(_ECHO_HELLO)
    assert "hello" in result


def test_run_shell_stderr_labelled() -> None:
    """Output written to stderr must appear under the [stderr] label."""
    if sys.platform == "win32":
        cmd = "echo err_text 1>&2"
    else:
        cmd = "echo err_text >&2"
    result = run_shell(cmd)
    assert "[stderr]" in result
    assert "err_text" in result


def test_run_shell_nonzero_exit_still_returns_output() -> None:
    """A non-zero exit code must not raise; output is still returned."""
    if sys.platform == "win32":
        cmd = "exit 1"
    else:
        cmd = "exit 1"
    # Should not raise; just return whatever output was produced
    result = run_shell(cmd)
    assert isinstance(result, str)


def test_run_shell_timeout_message() -> None:
    """A command that exceeds the timeout returns the timeout message."""
    if sys.platform == "win32":
        cmd = "ping -n 10 127.0.0.1 > NUL"
    else:
        cmd = "sleep 10"
    result = run_shell(cmd, timeout=1)
    assert "timed out" in result
    assert "1s" in result


def test_run_shell_output_truncated() -> None:
    """Extremely large output must be truncated to _MAX_OUTPUT_CHARS."""
    from lmcode.tools.shell import _MAX_OUTPUT_CHARS

    if sys.platform == "win32":
        # Python one-liner works on both platforms
        cmd = f"python -c \"print('x' * {_MAX_OUTPUT_CHARS + 5000})\""
    else:
        cmd = f"python3 -c \"print('x' * {_MAX_OUTPUT_CHARS + 5000})\""
    result = run_shell(cmd, timeout=15)
    assert len(result) <= _MAX_OUTPUT_CHARS + len("\n[truncated]")
    assert "[truncated]" in result
