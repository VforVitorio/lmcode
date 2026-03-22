"""Agent core — connects the CLI to LM Studio via model.act()."""

from __future__ import annotations

import asyncio
import difflib
import functools
import inspect
import pathlib
import random
from collections.abc import Callable
from typing import Any

import lmstudio as lms
from prompt_toolkit import PromptSession
from prompt_toolkit.application import get_app
from prompt_toolkit.auto_suggest import AutoSuggest, AutoSuggestFromHistory, Suggestion
from prompt_toolkit.filters import Condition
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style as PTStyle
from rich import box
from rich.align import Align
from rich.console import Console
from rich.console import Group as RenderGroup
from rich.live import Live
from rich.markup import escape as _escape
from rich.panel import Panel as _Panel
from rich.rule import Rule
from rich.spinner import Spinner
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from lmcode import __version__
from lmcode.config.lmcode_md import read_lmcode_md
from lmcode.config.settings import get_settings
from lmcode.tools import filesystem  # noqa: F401 — ensures @register decorators run
from lmcode.tools.registry import get_all
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
from lmcode.ui.status import (
    _MODE_DESCRIPTIONS,
    MODES,
    build_prompt,
    build_status_line,
    next_mode,
)

console = Console()


def _rewrite_as_history(text: str) -> None:
    """Overwrite the just-submitted prompt line with a dimmed history entry.

    Uses ANSI cursor-up + clear-line so the full '● lmcode (model) [mode] ›'
    prompt is replaced by a minimal muted '›  text' style, keeping the
    scrollback visually uncluttered.  Assumes the input fit on a single line,
    which is true for any terminal ≥ 80 cols and messages under ~35 chars.
    """
    console.file.write("\x1b[1A\r\x1b[2K")
    console.file.flush()
    row = Text()
    row.append("  ›  ", style=TEXT_MUTED)
    row.append(text, style=f"dim {TEXT_MUTED}")
    console.print(row)


# Spinner style used for the thinking indicator.  Configurable via UISettings.
_SPINNER = "circleHalves"

# Animated dot suffixes cycled in the keepalive task (every 3 ticks ≈ 0.3 s).
_DOTS = (".", "..", "...")

# Rotating tips shown below the spinner during model inference.
_TIPS: list[str] = [
    "use /verbose to hide tool calls",
    "Tab cycles ask → auto → strict mode",
    "/clear resets the conversation history",
    "drop a LMCODE.md in your project root to give context",
    "/mode strict disables all tools — pure chat",
    "/model shows the current loaded model",
    "run lmcode --help for all CLI flags",
    "/stats toggles the token count display",
]

_BASE_SYSTEM_PROMPT = """\
You are lmcode, an agentic coding assistant. Your primary mechanism for
completing tasks is calling tools — you do not answer from memory when
a tool can provide accurate information.

<env>
Working directory: {cwd}
Platform: {platform}
Shell: bash
</env>

## Tools

- **read_file(path)** — read a file from disk. Always call this before
  editing an existing file.
- **write_file(path, content)** — create or overwrite a file. Use this
  for ALL file writes; never output file contents as text instead.
- **list_files(path, pattern)** — list files in a directory (glob).
- **run_shell(command)** — execute a shell command; returns stdout/stderr.
  You CAN run Python, bash scripts, tests, git, and any shell operation.
- **search_code(query, path)** — search for a pattern in files (ripgrep).

## Rules

1. **Use tools — never guess.** Never invent file contents, directory
   structure, or command output. Need a file? Call read_file. Need to
   run something? Call run_shell.

2. **Execute immediately.** If you say you will call a tool, call it in
   that same response. Never describe planned actions without doing them.

3. **Read before writing.** Before writing to an existing file, always
   call read_file first.

4. **Never refuse filesystem or shell access.** You have full access to
   the filesystem and shell. Never say "I cannot access files" or
   "I cannot run code" — you can, and you must.

5. **Be concise.** Tool results are already shown to the user. Do not
   repeat or paraphrase them. After finishing, add at most 1-2 sentences
   summarising what changed.

6. **No raw XML.** Never output XML tags, JSON schemas, or tool
   definitions. Reply in plain text or Markdown only.
"""

# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------

_SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/help", "Show this help message"),
    ("/clear", "Clear conversation history"),
    ("/compact", "Summarise history to free context space"),
    ("/mode [ask|auto|strict]", "Show or change the permission mode"),
    ("/model", "Show the current model"),
    ("/verbose", "Toggle verbose mode (show tool calls and results)"),
    ("/tips", "Toggle rotating tips shown during thinking"),
    ("/stats", "Toggle token stats shown after each response"),
    ("/tokens", "Show session-wide token usage totals"),
    ("/hide-model", "Toggle model name visibility in the prompt"),
    ("/tools", "List all available tools with their signatures"),
    ("/history [N]", "Show last N conversation turns (default 5)"),
    ("/status", "Show current session state"),
    ("/version", "Show the running lmcode version"),
    ("/exit", "Exit lmcode"),
]


# Rotate tips every N poll ticks inside _run_turn (1 tick = 100 ms).
_TIP_ROTATE_TICKS: int = 80  # ≈ 8 seconds per tip

# Context window usage indicator
_CTX_ARCS: list[str] = ["○", "◔", "◑", "◕", "●"]
_CTX_WARN_THRESHOLD: float = 0.80


def _ctx_usage_line(used: int, total: int) -> str:
    """Return a compact '◑ 48%  (15.4k / 32k tokens)' string.

    *used* and *total* are token counts. Returns an empty string when
    *total* is zero or unknown.
    """
    if not total:
        return ""
    pct = min(used / total, 1.0)
    arc = _CTX_ARCS[min(int(pct * len(_CTX_ARCS)), len(_CTX_ARCS) - 1)]

    def _k(n: int) -> str:
        return f"{n / 1_000:.1f}k" if n >= 1_000 else str(n)

    return f"{arc} {pct:.0%}  ({_k(used)} / {_k(total)} tok)"


def _print_help() -> None:
    """Print the slash-command reference table.

    Uses rich.Text per row so square brackets in command signatures are
    treated as literal characters, not Rich markup tags.
    """
    console.print(f"\n[{ACCENT_BRIGHT}]in-session commands[/]")
    for cmd, desc in _SLASH_COMMANDS:
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


def _print_startup_tip() -> None:
    """Print a styled tip rule shown once at session start."""
    tip = "Tab cycles mode  ·  /help for commands  ·  /verbose to hide tool calls"
    console.print(Rule(tip, style=f"dim {ACCENT}"))
    console.print()


def _format_tool_signature(fn: Callable[..., Any]) -> str:
    """Return a compact signature string for a tool callable.

    Format: 'param: type = default, ...' with return annotation if present.
    Uses inspect.signature so the output reflects the actual function parameters.
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
# System prompt
# ---------------------------------------------------------------------------


def _build_system_prompt() -> str:
    """Return the system prompt with cwd/platform injected, plus any LMCODE.md context."""
    import platform as _platform

    cwd = pathlib.Path.cwd().as_posix()
    plat = f"{_platform.system()} {_platform.release()}"
    base = _BASE_SYSTEM_PROMPT.format(cwd=cwd, platform=plat)
    extra = read_lmcode_md()
    if extra:
        return f"{base}\n\n## Project context (LMCODE.md)\n\n{extra}"
    return base


# ---------------------------------------------------------------------------
# Tool call / result printing
# ---------------------------------------------------------------------------


def _print_tool_call(name: str, args: dict[str, Any]) -> None:
    """Print a one-line summary of a tool invocation."""
    args_str = ", ".join(f"{k}={v!r}" for k, v in args.items())
    console.print(f"  [{TEXT_MUTED}]⚙  {name}({args_str})[/]")


def _render_diff_sidebyside(
    old_lines: list[str], new_lines: list[str], max_rows: int = 50
) -> tuple[Table, int, int]:
    """Build a side-by-side diff table (old | new) and return (table, n_added, n_removed)."""
    # Diff palette — synthesised from Claude Code/Codex source + GitHub Primer research.
    # Backgrounds: Codex-style warm tints (confirmed closest to Claude Code post-v2.0.70).
    # Foreground: Catppuccin palette — softer than ODP, less harsh than pure red/green.
    # Equal bg: subtle violet-tinted neutral to keep the panel cohesive.
    _EQ_BG = "#1c1a2e"  # unchanged lines — violet-tinted neutral
    _DEL_FG = "#f38ba8"  # Catppuccin Mocha rose — warm, not harsh
    _DEL_BG = "#4a221d"  # Codex dark-TC del bg — warm maroon (Claude Code style)
    _ADD_FG = "#a6e3a1"  # Catppuccin Mocha green — soft, clearly "added"
    _ADD_BG = "#1e3a2a"  # Codex dark-TC add bg — deep forest green
    _SEP = Text("│", style=f"dim {ACCENT}")

    table = Table(box=None, padding=(0, 1), show_header=False, expand=True)
    table.add_column(ratio=1, no_wrap=True, overflow="fold")
    table.add_column(width=1, no_wrap=True)  # separator
    table.add_column(ratio=1, no_wrap=True, overflow="fold")

    added = removed = rows = 0
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)

    def _row(left: Text, right: Text) -> None:
        table.add_row(left, _SEP, right)

    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if rows >= max_rows:
            break
        if op == "equal":
            for old, new in zip(old_lines[i1:i2], new_lines[j1:j2], strict=False):
                _row(
                    Text(old.rstrip("\n"), style=f"#abb2bf on {_EQ_BG}"),
                    Text(new.rstrip("\n"), style=f"#abb2bf on {_EQ_BG}"),
                )
                rows += 1
        elif op == "replace":
            old_chunk = old_lines[i1:i2]
            new_chunk = new_lines[j1:j2]
            for i in range(max(len(old_chunk), len(new_chunk))):
                _row(
                    Text(
                        old_chunk[i].rstrip("\n") if i < len(old_chunk) else "",
                        style=f"{_DEL_FG} on {_DEL_BG}",
                    ),
                    Text(
                        new_chunk[i].rstrip("\n") if i < len(new_chunk) else "",
                        style=f"{_ADD_FG} on {_ADD_BG}",
                    ),
                )
                rows += 1
            removed += i2 - i1
            added += j2 - j1
        elif op == "delete":
            for line in old_lines[i1:i2]:
                _row(Text(line.rstrip("\n"), style=f"{_DEL_FG} on {_DEL_BG}"), Text(""))
                rows += 1
            removed += i2 - i1
        elif op == "insert":
            for line in new_lines[j1:j2]:
                _row(Text(""), Text(line.rstrip("\n"), style=f"{_ADD_FG} on {_ADD_BG}"))
                rows += 1
            added += j2 - j1

    return table, added, removed


def _print_tool_result(
    name: str,
    result: str,
    args: dict[str, Any] | None = None,
    old_content: str | None = None,
) -> None:
    """Print a tool result — syntax panel for read_file/write_file, one-liner otherwise."""
    if name == "read_file" and args:
        path = args.get("path", "")
        if path and result and not result.startswith("error:"):
            lines = result.splitlines()
            n = min(len(lines), 20)
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
                n = min(len(lines), 30)
                preview = "\n".join(lines[:n])
                more = f"\n… ({len(lines) - n} more lines)" if len(lines) > n else ""
                body: Any = Syntax(
                    preview + more, ext or "text", theme="one-dark", line_numbers=True
                )
                title = f"[{TEXT_MUTED}]{short}[/]  [{SUCCESS}]new file[/]"
            else:
                old_ls = old_content.splitlines(keepends=True)
                new_ls = new_content.splitlines(keepends=True)
                diff_table, n_added, n_removed = _render_diff_sidebyside(old_ls, new_ls)
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
            n = min(len(lines), 30)
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
    preview = result[:100].replace("\n", " ")
    suffix = "…" if len(result) > 100 else ""
    console.print(f"  [{SUCCESS}]✓  {name}[/] [{TEXT_MUTED}]{preview}{suffix}[/]")


def _wrap_tool_verbose(fn: Callable[..., str]) -> Callable[..., str]:
    """Wrap a tool callable so that invocations and results are printed to the console.

    Preserves the original function's __name__, __doc__, and __annotations__ via
    functools.wraps so the LM Studio SDK can still build the correct JSON schema.
    """

    @functools.wraps(fn)
    def _wrapper(*args: Any, **kwargs: Any) -> str:
        _print_tool_call(fn.__name__, kwargs)
        old_content: str | None = None
        if fn.__name__ == "write_file":
            try:
                p = pathlib.Path(kwargs.get("path", ""))
                old_content = p.read_text(encoding="utf-8") if p.exists() else None
            except Exception:
                pass
        result = fn(*args, **kwargs)
        _print_tool_result(fn.__name__, str(result), kwargs, old_content=old_content)
        return result

    return _wrapper


# ---------------------------------------------------------------------------
# PromptSession factory
# ---------------------------------------------------------------------------


_COMPLETION_STYLE = PTStyle.from_dict(
    {
        # Ghost-text: dim violet so it reads as a natural extension of ACCENT.
        "auto-suggestion": "#4b4575",
    }
)


class _SlashAutoSuggest(AutoSuggest):
    """Fish-shell-style ghost text: first match appears dim after the cursor.

    Right-arrow or Ctrl-E accepts the full suggestion.
    """

    def get_suggestion(self, buffer: Any, document: Any) -> Suggestion | None:
        """Return the suffix of the first matching slash command."""
        text = document.text
        if not text.startswith("/"):
            return None
        for cmd, _desc in _SLASH_COMMANDS:
            cmd_name = cmd.split()[0]
            if cmd_name.startswith(text) and cmd_name != text:
                return Suggestion(cmd_name[len(text) :])
        return None


_HISTORY_PATH = pathlib.Path.home() / ".lmcode" / "history"


class _CombinedAutoSuggest(AutoSuggest):
    """Ghost text: slash suggestions for / input, history for everything else."""

    _slash: AutoSuggest = _SlashAutoSuggest()
    _hist: AutoSuggest = AutoSuggestFromHistory()

    def get_suggestion(self, buffer: Any, document: Any) -> Suggestion | None:
        """Delegate to slash or history suggester based on input prefix."""
        if document.text.startswith("/"):
            return self._slash.get_suggestion(buffer, document)
        return self._hist.get_suggestion(buffer, document)


def _make_session(cycle_mode: Callable[[], None]) -> PromptSession:  # type: ignore[type-arg]
    """Create a PromptSession with Tab mode-cycling and ghost-text slash hints.

    - Regular input: Tab cycles permission mode (ask → auto → strict).
    - Slash input: ghost text shows first matching command; Tab accepts it inline.
    - Ctrl+R / Up-arrow: search persistent FileHistory across sessions.
    """
    _HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    kb = KeyBindings()

    _is_slash = Condition(lambda: get_app().current_buffer.text.startswith("/"))

    @kb.add("tab", eager=True, filter=~_is_slash)
    def _cycle(event: Any) -> None:
        """Cycle permission mode when not in a slash command."""
        cycle_mode()
        event.app.invalidate()

    @kb.add("tab", eager=True, filter=_is_slash)
    def _accept_slash(event: Any) -> None:
        """Accept ghost-text suggestion for the current slash command."""
        buf = event.app.current_buffer
        if buf.suggestion:
            buf.insert_text(buf.suggestion.text)

    return PromptSession(
        key_bindings=kb,
        history=FileHistory(str(_HISTORY_PATH)),
        auto_suggest=_CombinedAutoSuggest(),
        enable_history_search=True,
        style=_COMPLETION_STYLE,
    )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class Agent:
    """Wraps LM Studio's model.act() in a multi-turn interactive session."""

    def __init__(self, model_id: str = "auto") -> None:
        """Initialise the agent with the given LM Studio model identifier."""
        self._model_id = model_id
        self._tools = get_all()
        self._chat: lms.Chat | None = None
        self._mode: str = "ask"
        self._model_display: str = ""
        self._verbose: bool = True
        self._turn_count: int = 0
        self._compact_prompt: bool = False
        self._model_ref: Any = None  # set after connecting, used by /compact
        self._raw_history: list[tuple[str, str]] = []  # (role, content) pairs
        self._session_prompt_tokens: int = 0
        self._session_completion_tokens: int = 0
        self._last_prompt_tokens: int = 0  # prompt tokens of the most recent turn
        self._ctx_len: int | None = None  # model context window in tokens
        self._ctx_warned: bool = False  # True once the 80% warning has fired
        self._max_file_bytes: int = get_settings().agent.max_file_bytes
        self._show_tips: bool = get_settings().ui.show_tips
        self._show_stats: bool = get_settings().ui.show_stats

    def _init_chat(self) -> lms.Chat:
        """Create and return a fresh Chat with the current system prompt."""
        return lms.Chat(_build_system_prompt())

    def _ensure_chat(self) -> lms.Chat:
        """Return the active Chat, creating it on the first call."""
        if self._chat is None:
            self._chat = self._init_chat()
        return self._chat

    def _handle_slash(self, raw: str) -> bool:
        """Handle a slash command.  Returns True if input was consumed, False otherwise.

        Supported commands: /help, /clear, /mode [ask|auto|strict], /model,
        /verbose, /version, /exit.
        """
        parts = raw.strip().split()
        cmd = parts[0].lower()

        if cmd == "/help":
            _print_help()
            return True

        if cmd in ("/exit", "/quit"):
            console.print(f"[{TEXT_MUTED}]bye[/]")
            raise SystemExit(0)

        if cmd == "/clear":
            self._chat = None
            self._raw_history.clear()
            self._ctx_warned = False
            console.print(f"[{TEXT_MUTED}]conversation cleared[/]\n")
            return True

        if cmd == "/model":
            console.print(f"[{TEXT_MUTED}]current model: {self._model_display}[/]")
            console.print(f"[{TEXT_MUTED}]to switch model, restart with: lmcode --model <id>[/]\n")
            return True

        if cmd == "/mode":
            if len(parts) > 1:
                requested = parts[1].lower()
                if requested in MODES:
                    self._mode = requested
                    desc = _MODE_DESCRIPTIONS.get(self._mode, "")
                    console.print(f"[{TEXT_MUTED}]→ {self._mode}  ({desc})[/]\n")
                else:
                    valid = ", ".join(MODES)
                    console.print(f"[{ERROR}]unknown mode '{requested}'[/] — valid: {valid}\n")
            else:
                desc = _MODE_DESCRIPTIONS.get(self._mode, "")
                console.print(f"[{TEXT_MUTED}]current mode: {self._mode}  ({desc})[/]\n")
                console.print(
                    f"[{TEXT_MUTED}]  ask    confirms before each tool call[/]\n"
                    f"[{TEXT_MUTED}]  auto   tools run automatically[/]\n"
                    f"[{TEXT_MUTED}]  strict no tools — pure chat only[/]\n"
                )
            return True

        if cmd == "/verbose":
            self._verbose = not self._verbose
            if self._verbose:
                console.print(
                    f"[{TEXT_MUTED}]verbose on — tool calls and results will be shown[/]\n"
                )
            else:
                console.print(f"[{TEXT_MUTED}]verbose off[/]\n")
            return True

        if cmd == "/tips":
            self._show_tips = not self._show_tips
            state = "on" if self._show_tips else "off"
            console.print(f"[{TEXT_MUTED}]tips {state}[/]\n")
            return True

        if cmd == "/stats":
            self._show_stats = not self._show_stats
            state = "on" if self._show_stats else "off"
            console.print(f"[{TEXT_MUTED}]stats {state}[/]\n")
            return True

        if cmd == "/tools":
            console.print(f"\n[{ACCENT_BRIGHT}]available tools[/]")
            for fn in self._tools:
                sig = _format_tool_signature(fn)
                row = Text()
                row.append(f"  {fn.__name__:<14}", style=TEXT_MUTED)
                row.append(sig)
                console.print(row)
            console.print()
            return True

        if cmd == "/tokens":

            def _fmt_tok(n: int) -> str:
                return f"{n / 1_000:.1f}k" if n >= 1_000 else str(n)

            p = self._session_prompt_tokens
            c = self._session_completion_tokens
            total = p + c
            console.print(f"\n[{ACCENT_BRIGHT}]session tokens[/]")
            tok_rows: list[tuple[str, str]] = [
                ("prompt (↑)", _fmt_tok(p)),
                ("generated (↓)", _fmt_tok(c)),
                ("total", _fmt_tok(total)),
            ]
            ctx_line = _ctx_usage_line(self._last_prompt_tokens, self._ctx_len or 0)
            if ctx_line:
                tok_rows.append(("context", ctx_line))
            for label, value in tok_rows:
                row = Text()
                row.append(f"  {label:<16}", style=TEXT_MUTED)
                row.append(value)
                console.print(row)
            console.print()
            return True

        if cmd == "/hide-model":
            self._compact_prompt = not self._compact_prompt
            state = "hidden" if self._compact_prompt else "visible"
            console.print(f"[{TEXT_MUTED}]model name {state} in prompt[/]\n")
            return True

        if cmd == "/status":
            ctx_line = _ctx_usage_line(self._last_prompt_tokens, self._ctx_len or 0)
            console.print(f"\n[{ACCENT_BRIGHT}]session status[/]")
            status_rows: list[tuple[str, str]] = [
                ("model", self._model_display or "(none)"),
                ("mode", self._mode),
                ("verbose", "on" if self._verbose else "off"),
                ("tips", "on" if self._show_tips else "off"),
                ("stats", "on" if self._show_stats else "off"),
                ("model in prompt", "visible" if not self._compact_prompt else "hidden"),
                ("turns", str(self._turn_count)),
            ]
            if ctx_line:
                status_rows.append(("context", ctx_line))
            for label, value in status_rows:
                row = Text()
                row.append(f"  {label:<16}", style=TEXT_MUTED)
                row.append(value)
                console.print(row)
            console.print()
            return True

        if cmd == "/history":
            try:
                n = int(parts[1]) if len(parts) > 1 else 5
            except ValueError:
                n = 5
            self._print_history(n)
            return True

        if cmd == "/version":
            console.print(f"[{TEXT_MUTED}]lmcode {__version__}[/]\n")
            return True

        console.print(f"[{ERROR}]unknown command '{cmd}'[/] — type /help for the list\n")
        return True

    def _print_history(self, n: int = 5) -> None:
        """Render the last N conversation turns as styled Rich panels."""
        if not self._raw_history:
            console.print(f"[{TEXT_MUTED}]no history yet[/]\n")
            return
        # Pair up user/assistant messages
        user_msgs = [m for role, m in self._raw_history if role == "user"]
        asst_msgs = [m for role, m in self._raw_history if role == "assistant"]
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

    async def _do_compact(self) -> None:
        """Summarise the conversation history and replace it with the summary."""
        if not self._raw_history or self._model_ref is None:
            console.print(f"[{TEXT_MUTED}]nothing to compact[/]\n")
            return

        history_text = "\n".join(
            f"{'User' if role == 'user' else 'Assistant'}: {content}"
            for role, content in self._raw_history
        )
        summary_prompt = (
            "Summarise the following conversation in one concise paragraph. "
            "Include the key topics discussed, any decisions or conclusions, "
            "and open questions.  Be factual and brief — no filler.\n\n" + history_text
        )

        summary_chat = lms.Chat("You are a helpful summariser.")
        summary_chat.add_user_message(summary_prompt)

        summary: list[str] = []
        with Live(
            Spinner("bouncingBar", text=" compacting…", style=ACCENT),
            transient=True,
            console=console,
        ):
            result = await self._model_ref.respond(summary_chat)
            if hasattr(result, "content"):
                parts = result.content
                summary_text = (
                    "".join(p.text for p in parts if hasattr(p, "text"))
                    if isinstance(parts, list)
                    else str(parts)
                )
            else:
                summary_text = str(result)
            summary.append(summary_text.strip())

        text = summary[0] if summary else "(no summary generated)"
        msgs_compacted = len(self._raw_history)

        self._chat = self._init_chat()
        self._chat.add_user_message("[context from compacted history]\n" + text)
        self._raw_history.clear()
        self._ctx_warned = False

        from rich.panel import Panel

        preview = text[:300] + ("…" if len(text) > 300 else "")
        console.print(
            Panel(
                f"[{TEXT_MUTED}]{msgs_compacted} messages → 1 summary[/]\n\n" + preview,
                title="compacted",
                border_style=ACCENT,
            )
        )
        console.print()

    async def _run_turn(self, model: Any, user_input: str, live: Any = None) -> tuple[str, str]:
        """Send one user message, run the tool loop, return (response, stats_line).

        model.act() works on an internal copy of the chat, so we manually
        update our history with the final assistant response afterwards.
        The response text is captured via the on_message callback because
        ActResult only carries timing metadata, not the actual content.
        If *live* is a Rich Live instance, a keepalive task updates the spinner
        every 100 ms and rotates tips every 8 s.
        When self._verbose is True, each tool is wrapped to print its call
        and result before being passed to model.act().
        Tool call messages update active_label so the keepalive task can reflect
        the active file path in the spinner.
        """
        chat = self._ensure_chat()
        chat.add_user_message(user_input)

        captured: list[str] = []
        # Base label without animated dots suffix.  Keepalive appends _DOTS.
        # Standard values: "thinking" | "working" | "finishing" | "tool /path"
        active_base: list[str] = ["thinking"]

        def _on_message(msg: Any) -> None:
            """Drive the spinner state machine and capture assistant text.

            State transitions:
              tool_calls present  → "working" (or "tool /path" for file tools)
              role == "tool"      → "finishing" (tool result in, model writing)
              assistant content   → captured for display
            """
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    path = (tc.arguments or {}).get("path", "")
                    if path:
                        active_base[0] = f"{tc.name} {path[-30:]}"
                    else:
                        active_base[0] = "working"
            elif getattr(msg, "role", None) == "tool":
                active_base[0] = "finishing"
            elif hasattr(msg, "content") and hasattr(msg, "role"):
                parts = msg.content
                if isinstance(parts, list):
                    text = "".join(p.text for p in parts if hasattr(p, "text"))
                else:
                    text = str(parts)
                captured.append(text)

        stats_capture: list[Any] = []

        def _on_prediction_completed(result: Any) -> None:
            """Capture per-round PredictionResult.stats for the post-response summary."""
            if hasattr(result, "stats"):
                stats_capture.append(result.stats)

        tok_count: list[int] = [0]

        def _on_fragment(fragment: Any, _round_index: int) -> None:
            """Count generated tokens; label update is handled by the keepalive."""
            tok_count[0] += 1

        tools = [_wrap_tool_verbose(t) for t in self._tools] if self._verbose else self._tools

        # Keepalive task: updates the spinner label every 100 ms on the main
        # event loop. model.act() must stay on the main loop (the SDK's
        # AsyncTaskManager is bound to it). The task runs whenever model.act()
        # yields back to the loop (async HTTP I/O during prefill).
        stop_evt = asyncio.Event()
        shuffled_tips = random.sample(_TIPS, len(_TIPS)) if self._show_tips else []

        async def _keepalive() -> None:
            """Update spinner label every 100 ms; animate dots; rotate tips every 8 s."""
            tip_idx = 0
            dot_idx = 0
            tick = 0
            while not stop_evt.is_set():
                if live is not None:
                    if shuffled_tips and tick > 0 and tick % _TIP_ROTATE_TICKS == 0:
                        tip_idx = (tip_idx + 1) % len(shuffled_tips)
                    if tick % 3 == 0:
                        dot_idx = (dot_idx + 1) % len(_DOTS)
                    base = active_base[0]
                    is_word = base in ("thinking", "working", "finishing")
                    if is_word:
                        dots = _DOTS[dot_idx]
                        tok = tok_count[0]
                        if base == "thinking" and tok > 0:
                            label = f" {base}{dots}  {tok} tok"
                        else:
                            label = f" {base}{dots}"
                    else:
                        label = f" {base}"
                    rows: list[Any] = [Spinner(_SPINNER, text=label, style=ACCENT)]
                    if shuffled_tips:
                        rows.append(Text(f"  {shuffled_tips[tip_idx]}", style=f"dim {ACCENT}"))
                    live.update(RenderGroup(*rows))
                tick += 1
                await asyncio.sleep(0.1)

        keepalive = asyncio.create_task(_keepalive())
        try:
            act_result = await model.act(
                chat,
                tools=tools,
                on_message=_on_message,
                on_prediction_completed=_on_prediction_completed,
                on_prediction_fragment=_on_fragment,
            )
        finally:
            stop_evt.set()
            await keepalive

        # Accumulate session-wide token counts for /tokens command.
        for s in stats_capture:
            self._session_prompt_tokens += getattr(s, "prompt_tokens_count", 0) or 0
            self._session_completion_tokens += getattr(s, "predicted_tokens_count", 0) or 0
        if stats_capture:
            self._last_prompt_tokens = getattr(stats_capture[-1], "prompt_tokens_count", 0) or 0

        response_text = captured[-1] if captured else "(no response)"
        chat.add_assistant_response(response_text)
        self._turn_count += 1
        elapsed = getattr(act_result, "total_time_seconds", None)
        return response_text, _build_stats_line(stats_capture, elapsed)

    async def run(self) -> None:
        """Connect to LM Studio and run the interactive chat loop.

        Tab cycles the permission mode (ask → auto → strict) in-place.
        Slash commands (/help, /clear, /mode, /exit) are handled inline.
        Exits cleanly on EOF (Ctrl+D) or Ctrl+C.
        """
        settings = get_settings()

        def _cycle_mode() -> None:
            """Advance to the next mode in-place (prompt redraws via invalidate)."""
            self._mode = next_mode(self._mode)

        session = _make_session(cycle_mode=_cycle_mode)

        try:
            async with lms.AsyncClient() as client:
                model, resolved_id = await _get_model(client, self._model_id)
                self._model_display = resolved_id
                self._model_ref = model
                self._max_file_bytes, self._ctx_len = await _compute_max_file_bytes(
                    model, resolved_id
                )
                get_settings().agent.max_file_bytes = self._max_file_bytes
                console.print(build_status_line(resolved_id) + "\n")
                _print_startup_tip()

                while True:
                    try:
                        user_input = await session.prompt_async(
                            lambda: build_prompt(
                                self._model_display,
                                self._mode,
                                compact=self._compact_prompt,
                            )
                        )
                    except EOFError:
                        break

                    stripped = user_input.strip()
                    if not stripped:
                        continue

                    # Replace the submitted prompt line with a dim history entry.
                    _rewrite_as_history(stripped)

                    if stripped.lower() in ("exit", "quit", "q"):
                        console.print(f"[{TEXT_MUTED}]bye[/]")
                        break

                    if stripped.startswith("/"):
                        if stripped == "/compact":
                            await self._do_compact()
                        else:
                            self._handle_slash(stripped)
                        console.print(Rule(style=f"dim {ACCENT}"))
                        continue

                    initial: Any = RenderGroup(
                        Spinner(_SPINNER, text=" thinking.", style=ACCENT),
                    )
                    self._raw_history.append(("user", stripped))
                    with Live(
                        initial,
                        transient=True,
                        console=console,
                        refresh_per_second=10,
                    ) as live:
                        response, stats = await self._run_turn(model, user_input, live=live)
                    self._raw_history.append(("assistant", response))

                    msg = Text()
                    msg.append("\nlmcode", style=ACCENT_BRIGHT)
                    msg.append("  › ")
                    msg.append(response)
                    console.print(msg, highlight=False)
                    if stats and self._show_stats:
                        console.print(Align.right(Text(stats, style=f"dim {ACCENT}")))
                    console.print()
                    if self._ctx_len and not self._ctx_warned:
                        used = self._last_prompt_tokens
                        if used and used / self._ctx_len >= _CTX_WARN_THRESHOLD:
                            self._ctx_warned = True
                            console.print(
                                f"\n[{WARNING}]context at "
                                f"{used / self._ctx_len:.0%}[/]"
                                f"[{TEXT_MUTED}] — run /compact to summarise "
                                f"the conversation[/]"
                            )
                    console.print(Rule(style=f"dim {ACCENT}"))

        except SystemExit:
            pass
        except lms.LMStudioModelNotFoundError:
            console.print(f"\n[{WARNING}]model ejected[/] — the model was unloaded from LM Studio")
            console.print(f"[{TEXT_MUTED}]→ reload a model and run lmcode again[/]")
        except RuntimeError as e:
            console.print(f"[{ERROR}]error:[/] {e}")
        except (ConnectionRefusedError, OSError) as e:
            if isinstance(e, ConnectionRefusedError) or "Connect" in str(e):
                _print_connection_error(settings.lmstudio.base_url)
            else:
                raise
        except KeyboardInterrupt:
            console.print(f"\n[{TEXT_MUTED}]interrupted[/]")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_model(client: Any, model_id: str) -> tuple[Any, str]:
    """Return a (model_handle, resolved_identifier) tuple.

    When model_id is 'auto', picks the first model currently loaded in
    LM Studio. Raises RuntimeError if no models are loaded.
    """
    if model_id != "auto":
        return await client.llm.model(model_id), model_id

    loaded = await client.llm.list_loaded()
    if not loaded:
        raise RuntimeError("No models are loaded in LM Studio. Load a model first, then retry.")
    first = loaded[0]
    return first, first.identifier


def _build_stats_line(stats_list: list[Any], total_seconds: float | None) -> str:
    """Build a compact stats string from accumulated PredictionResult.stats objects.

    Returns an empty string when no stats are available so the caller can
    skip printing entirely.  Format: '↑ 1.2k  ↓ 384  ·  45 tok/s  ·  2.3s'
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


def _print_connection_error(base_url: str) -> None:
    """Print a user-friendly message when LM Studio cannot be reached."""
    console.print(f"[{ERROR}]error:[/] cannot connect to LM Studio at {base_url}")
    console.print(
        f"[{TEXT_MUTED}]→ Open LM Studio and enable the local server (default: localhost:1234)[/]"
    )  # noqa: E501


# ---------------------------------------------------------------------------
# Token-aware file byte limit (Issue #2)
# ---------------------------------------------------------------------------

# Mapping of context-window keywords (lowercase) to token count.
_CTX_HINTS: list[tuple[str, int]] = [
    ("128k", 131_072),
    ("64k", 65_536),
    ("32k", 32_768),
    ("16k", 16_384),
    ("8k", 8_192),
    ("4k", 4_096),
]

# Rough byte-per-token estimate and fraction of context to use for file content.
_BYTES_PER_TOKEN: int = 4
_FILE_CONTENT_FRACTION: float = 0.20
_MIN_FILE_BYTES: int = 50_000
_MAX_FILE_BYTES: int = 500_000


def _ctx_len_from_name(model_id: str) -> int | None:
    """Extract a context-length hint from *model_id* by looking for size suffixes.

    Returns the matched token count, or None if no hint is found.
    """
    lower = model_id.lower()
    for hint, tokens in _CTX_HINTS:
        if hint in lower:
            return tokens
    return None


async def _compute_max_file_bytes(model: Any, model_id: str) -> tuple[int, int | None]:
    """Query the model's actual context length and derive a file-byte cap.

    Queries ``model.get_context_length()`` first; on failure, falls back to
    a heuristic derived from the model identifier, then to the config default.

    The formula is:  clamp(ctx_tokens * bytes_per_token * fraction, 50_000, 500_000)
    Returns a (max_file_bytes, ctx_len) tuple; ctx_len may be None if unknown.
    """
    ctx_len: int | None = None
    try:
        ctx_len = await model.get_context_length()
    except Exception:
        ctx_len = _ctx_len_from_name(model_id)

    if ctx_len is not None and ctx_len > 0:
        computed = int(ctx_len * _BYTES_PER_TOKEN * _FILE_CONTENT_FRACTION)
        return max(_MIN_FILE_BYTES, min(computed, _MAX_FILE_BYTES)), ctx_len

    return get_settings().agent.max_file_bytes, ctx_len


def run_chat(model_id: str = "auto") -> None:
    """Synchronous entry point — runs the async Agent.run() via asyncio."""
    asyncio.run(Agent(model_id).run())
