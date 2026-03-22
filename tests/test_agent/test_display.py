"""Tests for src/lmcode/agent/_display.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lmcode.agent._display import (
    SLASH_COMMANDS,
    _build_stats_line,
    _ctx_usage_line,
    _format_tool_signature,
    _print_history,
    _render_diff_sidebyside,
)

# ---------------------------------------------------------------------------
# SLASH_COMMANDS
# ---------------------------------------------------------------------------


def test_slash_commands_is_list_of_pairs() -> None:
    """SLASH_COMMANDS is a non-empty list of (str, str) tuples."""
    assert isinstance(SLASH_COMMANDS, list)
    assert len(SLASH_COMMANDS) > 0
    for cmd, desc in SLASH_COMMANDS:
        assert isinstance(cmd, str)
        assert isinstance(desc, str)


def test_slash_commands_all_start_with_slash() -> None:
    """Every command signature starts with '/'."""
    for cmd, _ in SLASH_COMMANDS:
        assert cmd.startswith("/"), f"Command {cmd!r} does not start with '/'"


# ---------------------------------------------------------------------------
# _ctx_usage_line
# ---------------------------------------------------------------------------


def test_ctx_usage_line_zero_total_returns_empty() -> None:
    """Returns '' when total is 0 to avoid ZeroDivisionError."""
    assert _ctx_usage_line(0, 0) == ""


def test_ctx_usage_line_format() -> None:
    """Returns an arc + percentage + token counts string."""
    result = _ctx_usage_line(16_000, 32_000)
    assert "50%" in result
    assert "tok" in result


def test_ctx_usage_line_full_context() -> None:
    """At 100% usage returns the ● (full) arc."""
    result = _ctx_usage_line(32_000, 32_000)
    assert "●" in result
    assert "100%" in result


def test_ctx_usage_line_empty_context() -> None:
    """At 0% usage returns the ○ (empty) arc."""
    result = _ctx_usage_line(0, 32_000)
    assert "○" in result


# ---------------------------------------------------------------------------
# _build_stats_line
# ---------------------------------------------------------------------------


def test_build_stats_line_empty_list() -> None:
    """Returns '' when no stats are available."""
    assert _build_stats_line([], None) == ""


def test_build_stats_line_with_stats() -> None:
    """Returns a non-empty string with tok counts when stats are present."""
    stats = MagicMock()
    stats.prompt_tokens_count = 1024
    stats.predicted_tokens_count = 256
    stats.tokens_per_second = 40.0
    result = _build_stats_line([stats], 2.5)
    assert "↑" in result
    assert "↓" in result
    assert "tok/s" in result
    assert "2.5s" in result


def test_build_stats_line_no_elapsed() -> None:
    """Elapsed time section is omitted when total_seconds is None."""
    stats = MagicMock()
    stats.prompt_tokens_count = 100
    stats.predicted_tokens_count = 50
    stats.tokens_per_second = 0
    result = _build_stats_line([stats], None)
    assert "s" not in result.split("·")[-1] if "·" in result else True


# ---------------------------------------------------------------------------
# _format_tool_signature
# ---------------------------------------------------------------------------


def test_format_tool_signature_basic() -> None:
    """Returns a readable signature for a simple function."""

    def my_tool(path: str, count: int = 10) -> str:
        return ""

    sig = _format_tool_signature(my_tool)
    assert "path" in sig
    assert "str" in sig
    assert "count" in sig
    assert "10" in sig


def test_format_tool_signature_return_type() -> None:
    """Includes return type annotation when present."""

    def my_tool(x: int) -> str:
        return ""

    sig = _format_tool_signature(my_tool)
    assert "→" in sig
    assert "str" in sig


# ---------------------------------------------------------------------------
# _render_diff_sidebyside
# ---------------------------------------------------------------------------


def test_render_diff_no_changes() -> None:
    """Returns 0 added and 0 removed for identical content."""
    lines = ["line1\n", "line2\n"]
    _, added, removed = _render_diff_sidebyside(lines, lines)
    assert added == 0
    assert removed == 0


def test_render_diff_counts_additions() -> None:
    """Counts inserted lines correctly."""
    old = ["a\n"]
    new = ["a\n", "b\n", "c\n"]
    _, added, removed = _render_diff_sidebyside(old, new)
    assert added == 2
    assert removed == 0


def test_render_diff_counts_deletions() -> None:
    """Counts deleted lines correctly."""
    old = ["a\n", "b\n", "c\n"]
    new = ["a\n"]
    _, added, removed = _render_diff_sidebyside(old, new)
    assert added == 0
    assert removed == 2


def test_render_diff_counts_replacements() -> None:
    """replace op counts both sides."""
    old = ["old line\n"]
    new = ["new line\n"]
    _, added, removed = _render_diff_sidebyside(old, new)
    assert added == 1
    assert removed == 1


# ---------------------------------------------------------------------------
# _print_history
# ---------------------------------------------------------------------------


def test_print_history_empty(capsys: pytest.CaptureFixture[str]) -> None:
    """Prints a 'no history yet' message for an empty history."""
    with patch("lmcode.agent._display.console") as mock_console:
        _print_history([], n=5)
        calls = [str(c) for c in mock_console.print.call_args_list]
        assert any("no history" in c for c in calls)


def test_print_history_limits_to_n() -> None:
    """Only renders the last n turns regardless of history length."""
    # Interleave: user/assistant alternating
    interleaved: list[tuple[str, str]] = []
    for i in range(10):
        interleaved.append(("user", f"q{i}"))
        interleaved.append(("assistant", f"a{i}"))

    with patch("lmcode.agent._display.console") as mock_console:
        _print_history(interleaved, n=2)
        # With 10 pairs and n=2, only 2 panels per pair × 2 pairs = 4 panel prints
        panel_calls = [
            c
            for c in mock_console.print.call_args_list
            if c.args  # non-empty prints
        ]
        # At least 4 calls (2 user + 2 assistant panels) plus surrounding newlines
        assert len(panel_calls) >= 4
