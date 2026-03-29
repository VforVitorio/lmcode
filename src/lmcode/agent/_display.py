"""Terminal display helpers — Rich panels, diff blocks, and slash-command UI.

All Rich output produced by lmcode flows through functions defined here.
The module owns the shared :data:`console` singleton and every ``_print_*``
helper so that :mod:`agent.core` stays focused on the agent loop itself.

Public names imported by other agent sub-modules:
- :data:`console` — the single :class:`rich.console.Console` instance
- :data:`SLASH_COMMANDS` — list of ``(command, description)`` pairs
- :func:`_rewrite_as_history` — dim-out the submitted prompt line
- :func:`_print_help` — display the slash-command table
- :func:`_print_startup_tip` — one-line tip shown at session start
- :func:`_print_history` — render last-N turns as Rich panels
- :func:`_format_tool_signature` — compact signature string for /tools
- :func:`_ctx_usage_line` — arc + percentage context-window indicator
- :func:`_print_tool_call` — one-line tool invocation summary
- :func:`_render_diff_sidebyside` — side-by-side diff table
- :func:`_print_tool_result` — syntax panel / diff / IN-OUT panel
- :func:`_build_stats_line` — token/speed stats string
- :func:`_print_connection_error` — LM Studio unreachable message
- :func:`_print_lmstudio_closed` — LM Studio disconnected message
"""

from __future__ import annotations

import difflib
import inspect
import pathlib
from collections.abc import Callable
from typing import Any

from rich import box
from rich.align import Align
from rich.console import Console
from rich.console import Group as RenderGroup
from rich.markup import escape as _escape
from rich.panel import Panel as _Panel
from rich.rule import Rule
from rich.style import Style
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Span, Text

from lmcode.ui.colors import (
    ACCENT,
    ACCENT_BRIGHT,
    BORDER,
    ERROR,
    SUCCESS,
    TEXT_MUTED,
    TEXT_SECONDARY,
    WARNING,
)

# ---------------------------------------------------------------------------
# Shared console
# ---------------------------------------------------------------------------

#: Single Rich console instance used across the entire agent session.
console = Console()

# ---------------------------------------------------------------------------
# Slash-command registry (drives /help output and ghost-text autocomplete)
# ---------------------------------------------------------------------------

#: All available slash commands as ``(command_signature, description)`` pairs.
SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/help", "Show this help message"),
    ("/clear", "Clear conversation history"),
    ("/compact", "Summarise history to free context space"),
    ("/mode [ask|auto|strict]", "Show or change the permission mode"),
    ("/model", "Manage model · /model list|load <id>|import <path>|unload"),
    ("/verbose", "Toggle verbose mode (show tool calls and results)"),
    ("/tips", "Toggle rotating tips shown during thinking"),
    ("/stats", "Toggle token stats shown after each response"),
    ("/tokens", "Show session-wide token usage totals"),
    ("/hide-model", "Toggle model name visibility in the prompt"),
    ("/tools", "List all available tools with their signatures"),
    ("/history [N]", "Show last N conversation turns (default 5)"),
    ("/status", "Show current session state"),
    ("/log", "Stream lms model I/O logs — shows exact prompt sent to the model"),
    ("/temp [value|reset]", "Show or set the sampling temperature (0.0 – 2.0)"),
    ("/params [set <key> <val>|reset]", "Show or set inference params (temperature, maxTokens, …)"),
    ("/version", "Show the running lmcode version"),
    ("/exit", "Exit lmcode"),
]

# ---------------------------------------------------------------------------
# Context-window arc indicator
# ---------------------------------------------------------------------------

#: Arc characters cycling from empty (○) to full (●).
CTX_ARCS: list[str] = ["○", "◔", "◑", "◕", "●"]

#: Fraction of context usage at which a warning is emitted.
CTX_WARN_THRESHOLD: float = 0.80

# ---------------------------------------------------------------------------
# Preview limits (named so magic numbers don't appear inline)
# ---------------------------------------------------------------------------

_FILE_PREVIEW_LINES: int = 20  # max lines shown in read_file panel
_WRITE_PREVIEW_LINES: int = 30  # max lines in new-file write panel
_SHELL_OUTPUT_LINES: int = 30  # max lines in run_shell OUT section
_RESULT_PREVIEW_CHARS: int = 100  # chars in fallback one-liner result


# ---------------------------------------------------------------------------
# Session-start helpers
# ---------------------------------------------------------------------------


def _rewrite_as_history(text: str) -> None:
    """Overwrite the just-submitted prompt line with a dimmed history entry.

    Uses ANSI cursor-up + clear-line so the full ``● lmcode (model) [mode] ›``
    prompt is replaced by a minimal muted ``›  text`` style, keeping the
    scrollback visually uncluttered.
    """
    console.file.write("\x1b[1A\r\x1b[2K")
    console.file.flush()
    row = Text()
    row.append("  ›  ", style=TEXT_MUTED)
    row.append(text, style=f"dim {TEXT_MUTED}")
    console.print(row)


def _print_startup_tip() -> None:
    """Print a styled tip rule shown once at session start."""
    tip = "Tab cycles mode  ·  /help for commands  ·  /verbose to hide tool calls"
    console.print(Rule(tip, style=f"dim {ACCENT}"))
    console.print()


# ---------------------------------------------------------------------------
# /help and /history
# ---------------------------------------------------------------------------


def _print_help() -> None:
    """Print the slash-command reference table.

    Uses :class:`rich.text.Text` per row so square brackets in command
    signatures are treated as literal characters, not Rich markup tags.
    """
    console.print(f"\n[{ACCENT_BRIGHT}]in-session commands[/]")
    for cmd, desc in SLASH_COMMANDS:
        row = Text()
        row.append(f"  {cmd:<30}", style=TEXT_MUTED)
        row.append(desc)
        console.print(row)
    footer = Text()
    footer.append(
        "\n  run lmcode --help outside the session for CLI subcommands and flags",
        style=TEXT_MUTED,
    )
    console.print(footer)
    console.print()


def _print_history(raw_history: list[tuple[str, str]], n: int = 5) -> None:
    """Render the last *n* conversation turns as styled Rich panels.

    *raw_history* is a list of ``(role, content)`` pairs where role is
    ``"user"`` or ``"assistant"``.  Pairs are zipped so incomplete turns
    (unanswered user messages) are skipped gracefully.
    """
    if not raw_history:
        console.print(f"[{TEXT_MUTED}]no history yet[/]\n")
        return
    user_msgs = [m for role, m in raw_history if role == "user"]
    asst_msgs = [m for role, m in raw_history if role == "assistant"]
    pairs = list(zip(user_msgs, asst_msgs, strict=False))
    turns = pairs[-n:]
    start = max(1, len(pairs) - n + 1)
    console.print()
    for i, (user_msg, asst_msg) in enumerate(turns):
        turn = start + i
        console.print(
            _Panel(
                f"[{TEXT_MUTED}]{user_msg}[/]",
                title=f"[{ACCENT}]turn {turn}  ·  you[/]",
                border_style=BORDER,
                padding=(0, 1),
            )
        )
        console.print(
            _Panel(
                asst_msg,
                title=f"[{ACCENT_BRIGHT}]turn {turn}  ·  lmcode[/]",
                border_style=f"dim {ACCENT}",
                padding=(0, 1),
            )
        )
    console.print()


# ---------------------------------------------------------------------------
# /tools helper
# ---------------------------------------------------------------------------


def _format_tool_signature(fn: Callable[..., Any]) -> str:
    """Return a compact ``param: type = default, … → return`` signature string.

    Uses :func:`inspect.signature` so the output reflects the actual function
    parameters rather than any wrapper added by :func:`functools.wraps`.
    """
    sig = inspect.signature(fn)
    params: list[str] = []
    for name, param in sig.parameters.items():
        annotation = (
            param.annotation.__name__
            if hasattr(param.annotation, "__name__")
            else str(param.annotation)
            if param.annotation is not inspect.Parameter.empty
            else ""
        )
        if param.default is not inspect.Parameter.empty:
            default_repr = repr(param.default)
            part = (
                f"{name}: {annotation} = {default_repr}"
                if annotation
                else f"{name} = {default_repr}"
            )
        else:
            part = f"{name}: {annotation}" if annotation else name
        params.append(part)
    param_str = ", ".join(params)
    ret = sig.return_annotation
    ret_str = (
        ret.__name__
        if hasattr(ret, "__name__")
        else str(ret)
        if ret is not inspect.Parameter.empty
        else ""
    )
    if ret_str and ret_str != "empty":
        return f"{param_str} → {ret_str}"
    return param_str


# ---------------------------------------------------------------------------
# Context-window usage line
# ---------------------------------------------------------------------------


def _ctx_usage_line(used: int, total: int) -> str:
    """Return a compact ``◑ 48%  (15.4k / 32k tokens)`` string.

    *used* and *total* are token counts.  Returns an empty string when
    *total* is zero or unknown so callers can skip printing cleanly.
    """
    if not total:
        return ""
    pct = min(used / total, 1.0)
    arc = CTX_ARCS[min(int(pct * len(CTX_ARCS)), len(CTX_ARCS) - 1)]

    def _k(n: int) -> str:
        return f"{n / 1_000:.1f}k" if n >= 1_000 else str(n)

    return f"{arc} {pct:.0%}  ({_k(used)} / {_k(total)} tok)"


# ---------------------------------------------------------------------------
# Tool call / result printing
# ---------------------------------------------------------------------------


def _print_tool_call(name: str, args: dict[str, Any]) -> None:
    """Print a one-line summary of a tool invocation to the console."""
    args_str = ", ".join(f"{k}={v!r}" for k, v in args.items())
    console.print(f"  [{TEXT_MUTED}]⚙  {name}({args_str})[/]")


def _render_diff_sidebyside(
    old_lines: list[str], new_lines: list[str], filename: str = "", max_rows: int = 50
) -> tuple[Table, int, int]:
    """Build a side-by-side diff table and return ``(table, n_added, n_removed)``.

    Uses Catppuccin Mocha foregrounds on Codex-style warm tint backgrounds —
    the same palette used by Claude Code's diff view.  Equal lines receive a
    subtle violet-tinted neutral background to keep the panel cohesive.
    """
    _EQ_BG = "#1c1a2e"  # unchanged — violet-tinted neutral
    _DEL_BG = "#4a221d"  # Codex dark-TC del bg — warm maroon
    _ADD_BG = "#1e3a2a"  # Codex dark-TC add bg — deep forest green
    _SEP = Text("│", style=f"dim {ACCENT}")

    table = Table(box=None, padding=(0, 1), show_header=False, expand=True)
    table.add_column(ratio=1, no_wrap=True, overflow="fold")
    table.add_column(width=1, no_wrap=True)  # separator
    table.add_column(ratio=1, no_wrap=True, overflow="fold")

    lexer_name = Syntax.guess_lexer(filename, code="".join(old_lines)) if filename else "text"

    old_text_obj = Syntax(
        "".join(old_lines), lexer_name, theme="one-dark", background_color="default"
    ).highlight("".join(old_lines))
    new_text_obj = Syntax(
        "".join(new_lines), lexer_name, theme="one-dark", background_color="default"
    ).highlight("".join(new_lines))

    old_hlt_lines = old_text_obj.split("\n")
    new_hlt_lines = new_text_obj.split("\n")

    def _style_line(line_text: Text, bg_color: str, is_empty: bool = False) -> Text:
        line_text = line_text.copy()
        if is_empty:
            return Text("", style=Style(bgcolor=bg_color))

        line_text.style = Style(bgcolor=bg_color)
        new_spans = []
        for span in line_text.spans:
            if isinstance(span.style, str):
                new_spans.append(Span(span.start, span.end, f"on {bg_color}"))
            else:
                new_spans.append(Span(span.start, span.end, span.style + Style(bgcolor=bg_color)))
        line_text.spans = new_spans
        return line_text

    added = removed = rows = 0
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)

    def _row(left: Text, right: Text) -> None:
        table.add_row(left, _SEP, right)

    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if rows >= max_rows:
            break
        if op == "equal":
            for i in range(i2 - i1):
                old_len = len(old_hlt_lines)
                new_len = len(new_hlt_lines)
                left = (
                    _style_line(old_hlt_lines[i1 + i], _EQ_BG)
                    if i1 + i < old_len
                    else Text("", style=Style(bgcolor=_EQ_BG))
                )
                right = (
                    _style_line(new_hlt_lines[j1 + i], _EQ_BG)
                    if j1 + i < new_len
                    else Text("", style=Style(bgcolor=_EQ_BG))
                )
                _row(left, right)
                rows += 1
        elif op == "replace":
            old_chunk = old_lines[i1:i2]
            new_chunk = new_lines[j1:j2]
            for i in range(max(len(old_chunk), len(new_chunk))):
                if i < len(old_chunk) and i1 + i < len(old_hlt_lines):
                    left = _style_line(old_hlt_lines[i1 + i], _DEL_BG)
                else:
                    left = _style_line(Text(""), _DEL_BG, is_empty=True)

                if i < len(new_chunk) and j1 + i < len(new_hlt_lines):
                    right = _style_line(new_hlt_lines[j1 + i], _ADD_BG)
                else:
                    right = _style_line(Text(""), _ADD_BG, is_empty=True)
                _row(left, right)
                rows += 1
            removed += i2 - i1
            added += j2 - j1
        elif op == "delete":
            for i in range(i2 - i1):
                if i1 + i < len(old_hlt_lines):
                    left = _style_line(old_hlt_lines[i1 + i], _DEL_BG)
                else:
                    left = _style_line(Text(""), _DEL_BG, is_empty=True)
                right = _style_line(Text(""), _DEL_BG, is_empty=True)
                _row(left, right)
                rows += 1
            removed += i2 - i1
        elif op == "insert":
            for i in range(j2 - j1):
                left = _style_line(Text(""), _ADD_BG, is_empty=True)
                if j1 + i < len(new_hlt_lines):
                    right = _style_line(new_hlt_lines[j1 + i], _ADD_BG)
                else:
                    right = _style_line(Text(""), _ADD_BG, is_empty=True)
                _row(left, right)
                rows += 1
            added += j2 - j1

    return table, added, removed


def _print_tool_result(
    name: str,
    result: str,
    args: dict[str, Any] | None = None,
    old_content: str | None = None,
) -> None:
    """Print a tool result using the most appropriate Rich component.

    Dispatch rules:
    - ``read_file``  → syntax-highlighted panel (one-dark, line numbers)
    - ``write_file`` → side-by-side diff block for edits; new-file panel otherwise
    - ``run_shell``  → IN / OUT panel with a separator Rule
    - everything else → one-line ``✓ name  preview…`` summary
    """
    if name == "read_file" and args:
        path = args.get("path", "")
        if path and result and not result.startswith("error:"):
            lines = result.splitlines()
            n = min(len(lines), _FILE_PREVIEW_LINES)
            preview = "\n".join(lines[:n])
            suffix = f"\n… ({len(lines) - n} more lines)" if len(lines) > n else ""
            ext = pathlib.Path(path).suffix.lstrip(".")
            syn = Syntax(
                preview + suffix,
                ext or "text",
                theme="one-dark",
                line_numbers=True,
            )
            short = pathlib.Path(path).name
            title = f"[{TEXT_MUTED}]{short}[/]  [dim](lines 1–{n})[/]"
            console.print(
                _Panel(syn, title=title, border_style=ACCENT, box=box.ROUNDED, padding=(0, 1))
            )
            return

    if name == "write_file" and args:
        path = args.get("path", "")
        new_content = args.get("content", "")
        if path and new_content and not result.startswith("error:"):
            short = pathlib.Path(path).name
            ext = pathlib.Path(path).suffix.lstrip(".")
            if old_content is None:
                lines = new_content.splitlines()
                n = min(len(lines), _WRITE_PREVIEW_LINES)
                preview = "\n".join(lines[:n])
                more = f"\n… ({len(lines) - n} more lines)" if len(lines) > n else ""
                body: Any = Syntax(
                    preview + more, ext or "text", theme="one-dark", line_numbers=True
                )
                title = f"[{TEXT_MUTED}]{short}[/]  [{SUCCESS}]new file[/]"
            else:
                old_ls = old_content.splitlines(keepends=True)
                new_ls = new_content.splitlines(keepends=True)
                diff_table, n_added, n_removed = _render_diff_sidebyside(
                    old_ls, new_ls, filename=path
                )
                if n_added == 0 and n_removed == 0:
                    console.print(
                        f"  [{SUCCESS}]✓  write_file[/] [{TEXT_MUTED}]{short} (no changes)[/]"
                    )
                    return
                parts = []
                if n_added:
                    parts.append(f"[{SUCCESS}]+{n_added}[/]")
                if n_removed:
                    parts.append(f"[{ERROR}]-{n_removed}[/]")
                title = f"[{TEXT_MUTED}]{short}[/]  {' '.join(parts)}"
                body = diff_table
            console.print(
                _Panel(body, title=title, border_style=ACCENT, box=box.ROUNDED, padding=(0, 1))
            )
            return

    if name == "run_shell" and args:
        cmd = args.get("command", "")
        if cmd:
            lines = result.splitlines()
            n = min(len(lines), _SHELL_OUTPUT_LINES)
            out_text = "\n".join(lines[:n])
            more = f"\n… ({len(lines) - n} more lines)" if len(lines) > n else ""
            in_grid = Table.grid(padding=(0, 1))
            in_grid.add_column(style=f"bold {ACCENT}", width=3, no_wrap=True)
            in_grid.add_column(style=TEXT_SECONDARY)
            in_grid.add_row("IN", _escape(cmd))
            out_grid = Table.grid(padding=(0, 1))
            out_grid.add_column(style=f"bold {ACCENT}", width=3, no_wrap=True)
            out_grid.add_column(style=TEXT_MUTED)
            out_grid.add_row("OUT", _escape(out_text + more))
            content = RenderGroup(in_grid, Rule(style=f"dim {ACCENT}"), out_grid)
            console.print(_Panel(content, border_style=ACCENT, box=box.ROUNDED, padding=(0, 1)))
            return

    # Fallback: one-liner summary
    preview = result[:_RESULT_PREVIEW_CHARS].replace("\n", " ")
    suffix = "…" if len(result) > _RESULT_PREVIEW_CHARS else ""
    console.print(f"  [{SUCCESS}]✓  {name}[/] [{TEXT_MUTED}]{preview}{suffix}[/]")


# ---------------------------------------------------------------------------
# Stats line
# ---------------------------------------------------------------------------


def _build_stats_line(stats_list: list[Any], total_seconds: float | None) -> str:
    """Build a compact stats string from accumulated ``PredictionResult.stats`` objects.

    Returns an empty string when no stats are available so the caller can
    skip printing entirely.  Format: ``↑ 1.2k  ↓ 384  ·  45 tok/s  ·  2.3s``
    """
    if not stats_list:
        return ""

    def _fmt(n: int) -> str:
        return f"{n / 1_000:.1f}k" if n >= 1_000 else str(n)

    prompt_tok = sum(getattr(s, "prompt_tokens_count", 0) or 0 for s in stats_list)
    pred_tok = sum(getattr(s, "predicted_tokens_count", 0) or 0 for s in stats_list)
    tok_per_sec: float = getattr(stats_list[-1], "tokens_per_second", 0) or 0

    parts: list[str] = []
    if prompt_tok or pred_tok:
        parts.append(f"↑ {_fmt(prompt_tok)}  ↓ {_fmt(pred_tok)}")
    if tok_per_sec > 0:
        parts.append(f"{tok_per_sec:.0f} tok/s")
    if total_seconds and total_seconds > 0:
        parts.append(f"{total_seconds:.1f}s")

    return "  ·  ".join(parts)


# ---------------------------------------------------------------------------
# /log — lms log stream event formatter
# ---------------------------------------------------------------------------


def _print_log_event(event: dict[str, object]) -> None:
    """Print a single event from ``lms log stream --json``.

    Known event types are ``"input"`` (prompt sent to the model) and
    ``"output"`` (response tokens received).  Unknown types are printed as
    compact JSON so no data is silently discarded.
    """
    event_type = str(event.get("type", ""))
    text = str(event.get("text", ""))

    # Try to extract tokens/sec if --stats was passed
    tok_sec = event.get("tokensPerSecond")
    if tok_sec is None:
        stats_obj = event.get("stats")
        if isinstance(stats_obj, dict):
            tok_sec = stats_obj.get("tokensPerSecond")
    stats_str = f" [{tok_sec:.1f} tok/s]" if isinstance(tok_sec, (int, float)) else ""

    if event_type == "input":
        label = Text()
        label.append("  ↑ input   ", style=f"dim {ACCENT}")
        label.append(text[:300], style=TEXT_MUTED)
        console.print(label)
    elif event_type == "output":
        label = Text()
        label.append(f"  ↓ output{stats_str}  ", style=f"dim {ACCENT_BRIGHT}")
        label.append(text[:300])
        console.print(label)
    else:
        row = Text()
        row.append(f"  {event_type or '?'}  ", style=f"dim {TEXT_MUTED}")
        row.append(str(event), style=TEXT_MUTED)
        console.print(row)


# ---------------------------------------------------------------------------
# Error messages
# ---------------------------------------------------------------------------


def _print_connection_error(base_url: str) -> None:
    """Print a user-friendly message when LM Studio cannot be reached at startup."""
    console.print(f"[{ERROR}]error:[/] cannot connect to LM Studio at {base_url}")
    console.print(
        f"[{TEXT_MUTED}]→ Open LM Studio and enable the local server (default: localhost:1234)[/]"
    )


def _print_lmstudio_closed() -> None:
    """Print a user-friendly message when LM Studio closes mid-session."""
    console.print(f"\n[{ERROR}]LM Studio disconnected[/]")
    console.print(f"[{TEXT_MUTED}]→ restart LM Studio and run lmcode again[/]")


# Align.right is re-exported here so core.py only needs to import from _display.
__all__ = [
    "Align",
    "CTX_ARCS",
    "CTX_WARN_THRESHOLD",
    "SLASH_COMMANDS",
    "console",
    "_build_stats_line",
    "_ctx_usage_line",
    "_format_tool_signature",
    "_print_connection_error",
    "_print_log_event",
    "_print_help",
    "_print_history",
    "_print_lmstudio_closed",
    "_print_startup_tip",
    "_print_tool_call",
    "_print_tool_result",
    "_render_diff_sidebyside",
    "_rewrite_as_history",
]


def _print_tool_preview(
    name: str,
    args: dict[str, Any],
    old_content: str | None = None,
) -> None:
    """Print a preview of a tool execution (before it happens) in ask mode."""
    if name == "write_file":
        path = args.get("path", "")
        new_content = args.get("content", "")
        if path and new_content:
            short = pathlib.Path(path).name
            ext = pathlib.Path(path).suffix.lstrip(".")
            if old_content is None:
                lines = new_content.splitlines()
                n = min(len(lines), _WRITE_PREVIEW_LINES)
                preview = "\n".join(lines[:n])
                more = f"\n… ({len(lines) - n} more lines)" if len(lines) > n else ""
                body: Any = Syntax(
                    preview + more, ext or "text", theme="one-dark", line_numbers=True
                )
                title = f"[{TEXT_MUTED}]{short}[/]  [{WARNING}]new file (preview)[/]"
            else:
                old_ls = old_content.splitlines(keepends=True)
                new_ls = new_content.splitlines(keepends=True)
                diff_table, n_added, n_removed = _render_diff_sidebyside(
                    old_ls, new_ls, filename=path
                )
                if n_added == 0 and n_removed == 0:
                    console.print(
                        f"  [{WARNING}]?  write_file[/] [{TEXT_MUTED}]{short} "
                        "(no changes - preview)[/]"
                    )
                    return
                parts = []
                if n_added:
                    parts.append(f"[{SUCCESS}]+{n_added}[/]")
                if n_removed:
                    parts.append(f"[{ERROR}]-{n_removed}[/]")
                title = f"[{TEXT_MUTED}]{short}[/]  {' '.join(parts)} [{WARNING}](preview)[/]"
                body = diff_table
            console.print(
                _Panel(body, title=title, border_style=WARNING, box=box.ROUNDED, padding=(0, 1))
            )
            return

    if name == "run_shell":
        cmd = args.get("command", "")
        if cmd:
            in_grid = Table.grid(padding=(0, 1))
            in_grid.add_column(style=f"bold {WARNING}", width=3, no_wrap=True)
            in_grid.add_column(style=TEXT_SECONDARY)
            in_grid.add_row("IN", _escape(cmd))
            title = f"[{WARNING}]run_shell (preview)[/]"
            console.print(
                _Panel(
                    in_grid,
                    title=title,
                    border_style=WARNING,
                    box=box.ROUNDED,
                    padding=(0, 1),
                )
            )
            return
