"""Agent core — the main agent loop connecting lmcode to LM Studio.

This module is intentionally kept narrow.  Display helpers live in
:mod:`agent._display`, prompt-toolkit session setup in :mod:`agent._prompt`,
and SDK noise suppression in :mod:`agent._noise` (installed at import time).

Public API:
- :func:`run_chat` — synchronous entry point called by ``lmcode chat``
- :class:`Agent` — the stateful agent that owns the LM Studio connection
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import json
import pathlib
import random
from typing import Any

import lmstudio as lms
from rich.align import Align
from rich.console import Group as RenderGroup
from rich.live import Live
from rich.markdown import Markdown
from rich.rule import Rule
from rich.spinner import Spinner
from rich.text import Text

from lmcode import __version__
from lmcode.agent._display import (
    CTX_WARN_THRESHOLD,
    _build_stats_line,
    _ctx_usage_line,
    _format_tool_signature,
    _print_connection_error,
    _print_help,
    _print_history,
    _print_lmstudio_closed,
    _print_log_event,
    _print_startup_tip,
    _print_tool_call,
    _print_tool_preview,
    _print_tool_result,
    _rewrite_as_history,
    console,
)
from lmcode.agent._noise import SDK_NOISE as _SDK_NOISE  # noqa: F401 — installs suppression
from lmcode.agent._prompt import make_session
from lmcode.config.lmcode_md import read_lmcode_md
from lmcode.config.settings import get_settings
from lmcode.lms_bridge import load_model, stream_model_log, unload_model
from lmcode.tools import filesystem  # noqa: F401 — ensures @register decorators run
from lmcode.tools.registry import get_all
from lmcode.ui._interactive_prompt import display_interactive_approval
from lmcode.ui.colors import (
    ACCENT,
    ACCENT_BRIGHT,
    ERROR,
    SUCCESS,
    TEXT_MUTED,
    WARNING,
)
from lmcode.ui.status import (
    _MODE_DESCRIPTIONS,
    MODES,
    build_prompt,
    build_status_line,
    next_mode,
)

# ---------------------------------------------------------------------------
# Spinner / tips constants
# ---------------------------------------------------------------------------

#: Rich spinner style used during model inference.
_SPINNER: str = "circleHalves"

#: Animated dot suffixes cycled in the keepalive task (every 3 ticks ≈ 0.3 s).
_DOTS: tuple[str, ...] = (".", "..", "...")

#: Rotating tips shown below the spinner during model inference.
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

#: Number of keepalive ticks between tip rotations (1 tick = 100 ms → ≈ 8 s).
_TIP_ROTATE_TICKS: int = 80

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_BASE_SYSTEM_PROMPT = """\
You are lmcode, a coding agent. You have NO built-in knowledge of the
local filesystem. You CANNOT see file contents, directory listings, or
command output unless you call the appropriate tool first. Every claim
about a file's contents that is not backed by a read_file call is a
hallucination.

<env>
Working directory: {cwd}
Platform: {platform}
Shell: bash
</env>

## Available tools

- **read_file(path)** — read a file. Call this FIRST before any edit.
- **write_file(path, content)** — create or overwrite a file.
- **list_files(path, pattern)** — list files recursively.
- **run_shell(command)** — run a shell command; returns stdout + stderr.
- **search_code(query, path)** — search files with ripgrep.

## Mandatory rules

1. **Always call a tool.** Never describe, invent, or recall file
   contents. If you need to know what is in a file, call read_file —
   every time, even if you think you saw it earlier.

2. **read_file before write_file.** If the file already exists, call
   read_file first. Then call write_file with the complete new content.

3. **run_shell to execute.** Never say "I ran the code" without having
   called run_shell. Never print hypothetical output.

4. **Call tools, do not describe them.** If you plan to read a file,
   read it — do not say "I will read it". Call the tool immediately.

5. **Be concise after tools.** Tool results are shown to the user. Do
   not repeat or reprint them. One or two sentences of summary is enough.
"""


def _build_system_prompt() -> str:
    """Return the system prompt with cwd/platform injected, plus any LMCODE.md content.

    Walks the directory tree upward from cwd looking for LMCODE.md files and
    appends their combined content under a ``## Project context`` heading.
    """
    import platform as _platform

    cwd = pathlib.Path.cwd().as_posix()
    plat = f"{_platform.system()} {_platform.release()}"
    base = _BASE_SYSTEM_PROMPT.format(cwd=cwd, platform=plat)
    extra = read_lmcode_md()
    if extra:
        return f"{base}\n\n## Project context (LMCODE.md)\n\n{extra}"
    return base


# ---------------------------------------------------------------------------
# Tool verbose wrapper
# ---------------------------------------------------------------------------


def _wrap_tool_verbose(fn: Any) -> Any:
    """Wrap a tool callable so invocations and results are printed to the console.

    Preserves the original function's ``__name__``, ``__doc__``, and
    ``__annotations__`` via :func:`functools.wraps` so the LM Studio SDK can
    still build the correct JSON schema.

    The LM Studio SDK calls tools with positional arguments, leaving
    ``kwargs`` empty.  :func:`inspect.signature` is used to map positional
    args to their parameter names so display panels can look up values by name.
    """
    _params = list(inspect.signature(fn).parameters.keys())

    @functools.wraps(fn)
    def _wrapper(*args: Any, **kwargs: Any) -> str:
        merged = {_params[i]: v for i, v in enumerate(args)}
        merged.update(kwargs)
        _print_tool_call(fn.__name__, merged)
        old_content: str | None = None
        if fn.__name__ == "write_file":
            try:
                p = pathlib.Path(merged.get("path", ""))
                old_content = p.read_text(encoding="utf-8") if p.exists() else None
            except Exception:
                pass
        result: str = fn(*args, **kwargs)
        _print_tool_result(fn.__name__, str(result), merged, old_content=old_content)
        return result

    return _wrapper


# ---------------------------------------------------------------------------
# Token-aware file byte limit
# ---------------------------------------------------------------------------

#: Context-window size hints extracted from model identifier substrings.
_CTX_HINTS: list[tuple[str, int]] = [
    ("128k", 131_072),
    ("64k", 65_536),
    ("32k", 32_768),
    ("16k", 16_384),
    ("8k", 8_192),
    ("4k", 4_096),
]

_BYTES_PER_TOKEN: int = 4  # rough bytes-per-token estimate
_FILE_CONTENT_FRACTION: float = 0.20  # fraction of context to use for file content
_MIN_FILE_BYTES: int = 50_000
_MAX_FILE_BYTES: int = 500_000


def _ctx_len_from_name(model_id: str) -> int | None:
    """Extract a context-length token count from *model_id* by matching size suffixes.

    Returns the first matched token count (e.g. ``32_768`` for ``"…32k…"``),
    or ``None`` if no hint is found.
    """
    lower = model_id.lower()
    for hint, tokens in _CTX_HINTS:
        if hint in lower:
            return tokens
    return None


async def _get_model(client: Any, model_id: str) -> tuple[Any, str]:
    """Return a ``(model_handle, resolved_identifier)`` tuple from *client*.

    When *model_id* is ``"auto"``, picks the first model currently loaded in
    LM Studio.  Raises :class:`RuntimeError` if no models are loaded.
    """
    if model_id != "auto":
        return await client.llm.model(model_id), model_id
    loaded = await client.llm.list_loaded()
    if not loaded:
        raise RuntimeError("No models are loaded in LM Studio. Load a model first, then retry.")
    first = loaded[0]
    return first, first.identifier


async def _compute_max_file_bytes(model: Any, model_id: str) -> tuple[int, int | None]:
    """Query the model's context length and derive a file-byte cap.

    Tries ``model.get_context_length()`` first; on failure falls back to a
    heuristic derived from *model_id*, then to the config default.

    Formula: ``clamp(ctx_tokens × bytes_per_token × fraction, 50_000, 500_000)``

    Returns:
        A ``(max_file_bytes, ctx_len)`` tuple; *ctx_len* may be ``None``.
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


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class Agent:
    """Stateful agent that wraps LM Studio's ``model.act()`` in a multi-turn session.

    One ``Agent`` instance lives for the duration of a ``lmcode chat`` session.
    It maintains the conversation history, permission mode, verbose flag, token
    counters, and a reference to the LM Studio model handle.
    """

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
        self._model_ref: Any = None  # set after connecting; used by /compact and /model load
        self._client_ref: Any = None  # AsyncClient; set in run(); used by /model load
        self._raw_history: list[tuple[str, str]] = []  # (role, content) pairs
        self._session_prompt_tokens: int = 0
        self._session_completion_tokens: int = 0
        self._last_prompt_tokens: int = 0  # prompt tokens of the most recent turn
        self._ctx_len: int | None = None  # model context window in tokens
        self._ctx_warned: bool = False  # True once the 80 % warning has fired
        self._max_file_bytes: int = get_settings().agent.max_file_bytes
        self._show_tips: bool = get_settings().ui.show_tips
        self._show_stats: bool = get_settings().ui.show_stats
        self._always_allowed_tools: set[str] = set()
        self._inference_config: dict[str, Any] = {}  # passed as config= to model.act()

    # ------------------------------------------------------------------
    # Chat initialisation
    # ------------------------------------------------------------------

    def _init_chat(self) -> lms.Chat:
        """Create and return a fresh :class:`lms.Chat` with the current system prompt."""
        return lms.Chat(_build_system_prompt())

    def _ensure_chat(self) -> lms.Chat:
        """Return the active chat, creating it on the first call."""
        if self._chat is None:
            self._chat = self._init_chat()
        return self._chat

    # ------------------------------------------------------------------
    # Slash-command handler
    # ------------------------------------------------------------------

    def _handle_slash(self, raw: str) -> bool:
        """Handle a slash command and return ``True`` if the input was consumed.

        All commands that don't require async work are handled here.
        ``/compact`` is handled directly in :meth:`run` because it needs ``await``.
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
            self._print_tokens()
            return True

        if cmd == "/hide-model":
            self._compact_prompt = not self._compact_prompt
            state = "hidden" if self._compact_prompt else "visible"
            console.print(f"[{TEXT_MUTED}]model name {state} in prompt[/]\n")
            return True

        if cmd == "/status":
            self._print_status()
            return True

        if cmd == "/history":
            try:
                n = int(parts[1]) if len(parts) > 1 else 5
            except ValueError:
                n = 5
            _print_history(self._raw_history, n)
            return True

        if cmd == "/version":
            console.print(f"[{TEXT_MUTED}]lmcode {__version__}[/]\n")
            return True

        if cmd == "/temp":
            return self._handle_temp(parts)

        if cmd == "/params":
            return self._handle_params(parts)

        console.print(f"[{ERROR}]unknown command '{cmd}'[/] — type /help for the list\n")
        return True

    def _handle_temp(self, parts: list[str]) -> bool:
        """Handle ``/temp [value|reset]`` — show or set the sampling temperature.

        ``/temp``         — show the current temperature (or ``default`` if unset).
        ``/temp <float>`` — set temperature (must be between 0.0 and 2.0).
        ``/temp reset``   — clear the override and revert to LM Studio default.
        """
        if len(parts) == 1:
            current = self._inference_config.get("temperature")
            if current is None:
                console.print(f"[{TEXT_MUTED}]temperature: default (set by LM Studio)[/]\n")
            else:
                console.print(f"[{TEXT_MUTED}]temperature: {current}[/]\n")
            return True

        arg = parts[1].lower()
        if arg == "reset":
            self._inference_config.pop("temperature", None)
            console.print(f"[{TEXT_MUTED}]temperature reset to default[/]\n")
            return True

        try:
            value = float(arg)
        except ValueError:
            console.print(
                f"[{ERROR}]invalid temperature '{arg}'[/] "
                f"[{TEXT_MUTED}]— use a number between 0.0 and 2.0[/]\n"
            )
            return True

        if not 0.0 <= value <= 2.0:
            console.print(f"[{ERROR}]temperature must be between 0.0 and 2.0[/] (got {value})\n")
            return True

        self._inference_config["temperature"] = value
        console.print(f"[{TEXT_MUTED}]temperature set to {value}[/]\n")
        return True

    def _handle_params(self, parts: list[str]) -> bool:
        """Handle ``/params`` and ``/params set <key> <value>`` — show or update inference params.

        ``/params``                 — show all current inference parameter overrides.
        ``/params set <key> <val>`` — set an inference parameter.
        ``/params reset``           — clear all overrides.

        Supported keys: ``temperature``, ``maxTokens``, ``topP``, ``topKSampling``,
        ``minPSampling``.
        """
        _VALID_PARAMS = {
            "temperature": float,
            "maxTokens": int,
            "topP": float,
            "topKSampling": int,
            "minPSampling": float,
        }

        sub = parts[1].lower() if len(parts) > 1 else ""

        if not sub or sub == "list":
            console.print(f"\n[{ACCENT_BRIGHT}]inference params[/]")
            if not self._inference_config:
                console.print(f"  [{TEXT_MUTED}](all defaults — no overrides set)[/]")
            else:
                for k, v in self._inference_config.items():
                    row = Text()
                    row.append(f"  {k:<18}", style=TEXT_MUTED)
                    row.append(str(v))
                    console.print(row)
            console.print(f"\n  [{TEXT_MUTED}]supported: {', '.join(_VALID_PARAMS)}[/]")
            console.print(f"  [{TEXT_MUTED}]/params set temperature 0.7  ·  /params reset[/]\n")
            return True

        if sub == "reset":
            self._inference_config.clear()
            console.print(f"[{TEXT_MUTED}]all inference params reset to defaults[/]\n")
            return True

        if sub == "set":
            if len(parts) < 4:
                console.print(f"[{ERROR}]usage: /params set <key> <value>[/]\n")
                return True
            key = parts[2]
            raw_val = parts[3]
            if key not in _VALID_PARAMS:
                valid = ", ".join(_VALID_PARAMS)
                console.print(f"[{ERROR}]unknown param '{key}'[/] — valid: {valid}\n")
                return True
            try:
                value: int | float = _VALID_PARAMS[key](raw_val)
            except ValueError:
                console.print(
                    f"[{ERROR}]invalid value '{raw_val}' for {key}[/] "
                    f"[{TEXT_MUTED}]— expected {_VALID_PARAMS[key].__name__}[/]\n"
                )
                return True
            self._inference_config[key] = value
            console.print(f"[{TEXT_MUTED}]{key} set to {value}[/]\n")
            return True

        console.print(
            f"[{ERROR}]unknown /params sub-command '{sub}'[/] "
            f"[{TEXT_MUTED}]— use: /params · /params set <key> <val> · /params reset[/]\n"
        )
        return True

    def _print_tokens(self) -> None:
        """Print session-wide token usage totals for the ``/tokens`` command."""

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

    def _print_status(self) -> None:
        """Print current session state for the ``/status`` command."""
        ctx_line = _ctx_usage_line(self._last_prompt_tokens, self._ctx_len or 0)
        console.print(f"\n[{ACCENT_BRIGHT}]session status[/]")
        temp_display = str(self._inference_config.get("temperature", "default"))
        status_rows: list[tuple[str, str]] = [
            ("model", self._model_display or "(none)"),
            ("mode", self._mode),
            ("temperature", temp_display),
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

    # ------------------------------------------------------------------
    # /compact
    # ------------------------------------------------------------------

    async def _do_compact(self) -> None:
        """Summarise the conversation history and replace it with the summary.

        Calls ``model.respond()`` with a summarisation prompt, then resets the
        chat object and injects the summary as a ``[context from compacted
        history]`` user message so the model has continuity without the full
        token cost.
        """
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

        from rich.panel import Panel

        text = summary[0] if summary else "(no summary generated)"
        msgs_compacted = len(self._raw_history)

        self._chat = self._init_chat()
        self._chat.add_user_message("[context from compacted history]\n" + text)
        self._raw_history.clear()
        self._ctx_warned = False

        preview = text[:300] + ("…" if len(text) > 300 else "")
        console.print(
            Panel(
                f"[{TEXT_MUTED}]{msgs_compacted} messages → 1 summary[/]\n\n" + preview,
                title="compacted",
                border_style=ACCENT,
            )
        )
        console.print()

    # ------------------------------------------------------------------
    # /log
    # ------------------------------------------------------------------

    async def _do_log(self, raw: str) -> None:
        """Stream lms model I/O logs until the user presses Ctrl+C.

        Starts ``lms log stream`` via :func:`lms_bridge.stream_model_log` and
        reads NDJSON lines in a thread executor so the event loop stays free.
        Each line is parsed and rendered via :func:`_print_log_event`.

        Terminates cleanly on Ctrl+C (``KeyboardInterrupt`` or
        ``asyncio.CancelledError``) and always calls ``proc.terminate()``
        in the ``finally`` block.
        """
        parts = raw.strip().split()
        stats_flag = len(parts) > 1 and parts[1] in ("stats", "--stats")

        proc = stream_model_log(stats=stats_flag)
        if proc is None:
            console.print(
                f"[{TEXT_MUTED}]lms not available — install LM Studio CLI to use /log[/]\n"
            )
            return

        console.print(f"\n[{ACCENT_BRIGHT}]lms log stream[/]  [{TEXT_MUTED}]Ctrl+C to stop[/]\n")
        loop = asyncio.get_event_loop()
        try:
            while proc.stdout:
                line: str = await loop.run_in_executor(None, proc.stdout.readline)
                if not line:
                    break
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    event: dict[str, object] = json.loads(stripped)
                except json.JSONDecodeError:
                    console.print(f"  [{TEXT_MUTED}]{stripped}[/]")
                    continue
                _print_log_event(event)
        except (KeyboardInterrupt, asyncio.CancelledError):
            task = asyncio.current_task()
            if task is not None and task.cancelling() > 0:
                task.uncancel()
        finally:
            proc.terminate()
            console.print(f"\n[{TEXT_MUTED}]log stream stopped[/]\n")

    # ------------------------------------------------------------------
    # /model
    # ------------------------------------------------------------------

    async def _do_model(self, raw: str) -> None:
        """Handle the ``/model`` family of sub-commands.

        Sub-commands:
            ``/model``               — show current model (read-only).
            ``/model list``          — table of downloaded + loaded models.
            ``/model load <id>``     — load *id* via lms, reconnect SDK handle.
            ``/model import <path>`` — import an external .gguf model file.
            ``/model unload``        — unload the current model from memory.
        """
        parts = raw.strip().split()
        sub = parts[1].lower() if len(parts) > 1 else ""

        if not sub:
            console.print(f"[{TEXT_MUTED}]current model: {self._model_display}[/]")
            console.print(
                f"[{TEXT_MUTED}]  /model list          — list downloaded models[/]\n"
                f"[{TEXT_MUTED}]  /model load <id>     — switch to a different model[/]\n"
                f"[{TEXT_MUTED}]  /model import <path> — import a .gguf file into LM Studio[/]\n"
                f"[{TEXT_MUTED}]  /model unload        — unload current model from memory[/]\n"
            )
            return

        if sub == "list":
            await self._model_list()
            return

        if sub == "load":
            if len(parts) < 3:
                console.print(f"[{ERROR}]usage: /model load <identifier>[/]\n")
                return
            await self._model_load(parts[2])
            return

        if sub == "import":
            if len(parts) < 3:
                console.print(f"[{ERROR}]usage: /model import <path_to_gguf>[/]\n")
                return
            # To handle unquoted paths with spaces, just join the rest
            await self._model_import(" ".join(parts[2:]))
            return

        if sub == "unload":
            await self._model_unload()
            return

        console.print(
            f"[{ERROR}]unknown /model sub-command '{sub}'[/] "
            "— valid: list · load <id> · import <path> · unload\n"
        )

    async def _model_list(self) -> None:
        """Print a table of downloaded and currently loaded models."""
        from lmcode.lms_bridge import list_downloaded_models, list_loaded_models

        loaded = list_loaded_models()
        downloaded = list_downloaded_models()

        loaded_ids = {m.identifier for m in loaded if m.identifier}

        console.print(f"\n[{ACCENT_BRIGHT}]downloaded models[/]")
        if not downloaded:
            console.print(f"  [{TEXT_MUTED}](none — run: lms get <model>)[/]")
        else:
            for m in downloaded:
                mid = m.load_name()
                tag = f" [{ACCENT}]● loaded[/]" if mid in loaded_ids else ""
                size = f"  [{TEXT_MUTED}]{m.format_size()}[/]"
                row = Text()
                row.append(f"  {mid}", style=TEXT_MUTED if mid not in loaded_ids else ACCENT)
                console.print(row, end="")
                console.print(size, end="")
                if tag:
                    console.print(tag)
                else:
                    console.print()
        console.print()

    async def _model_load(self, identifier: str) -> None:
        """Load *identifier* via lms and reconnect the SDK model handle."""
        if self._client_ref is None:
            console.print(f"[{ERROR}]not connected to LM Studio[/]\n")
            return

        console.print(f"[{TEXT_MUTED}]loading {identifier} …[/]")
        with Live(
            Spinner(_SPINNER, text=f" loading {identifier}…", style=ACCENT),
            transient=True,
            console=console,
        ):
            ok = await asyncio.to_thread(load_model, identifier)

        if not ok:
            console.print(
                f"[{ERROR}]failed to load '{identifier}'[/] "
                f"[{TEXT_MUTED}]— check the identifier with /model list[/]\n"
            )
            return

        try:
            new_model, resolved_id = await _get_model(self._client_ref, identifier)
        except Exception as exc:
            console.print(f"[{ERROR}]model loaded but SDK reconnect failed:[/] {exc}\n")
            return

        self._model_ref = new_model
        self._model_display = resolved_id
        self._max_file_bytes, self._ctx_len = await _compute_max_file_bytes(new_model, resolved_id)
        self._chat = None
        self._raw_history.clear()
        self._ctx_warned = False

        console.print(
            f"[{ACCENT_BRIGHT}]switched to {resolved_id}[/] "
            f"[{TEXT_MUTED}]— conversation history cleared[/]\n"
        )

    async def _model_import(self, path: str) -> None:
        """Import an external .gguf model file via lms."""
        console.print(f"[{TEXT_MUTED}]importing {path} …[/]")
        with Live(
            Spinner(_SPINNER, text=f" importing {path}… (this may take a moment)", style=ACCENT),
            transient=True,
            console=console,
        ):
            from lmcode.lms_bridge import import_model

            ok = await asyncio.to_thread(import_model, path)

        if ok:
            console.print(
                f"[{SUCCESS}]imported successfully[/] "
                f"[{TEXT_MUTED}]— use /model list to see it[/]\n"
            )
        else:
            console.print(
                f"[{ERROR}]failed to import[/] "
                f"[{TEXT_MUTED}]— verify the file exists and is a valid .gguf[/]\n"
            )

    async def _model_unload(self) -> None:
        """Unload the current model from LM Studio memory."""
        if not self._model_display:
            console.print(f"[{TEXT_MUTED}]no model to unload[/]\n")
            return

        console.print(
            f"[{WARNING}]this will unload '{self._model_display}' "
            "from memory — lmcode will stop working until you load another model.[/]"
        )
        console.print(f"[{TEXT_MUTED}]run /model load <id> to reload, or restart lmcode[/]\n")

        ok = await asyncio.to_thread(unload_model, self._model_display)
        if ok:
            console.print(f"[{TEXT_MUTED}]unloaded {self._model_display}[/]\n")
            self._model_ref = None
        else:
            console.print(f"[{ERROR}]unload failed — is lms installed?[/]\n")

    # ------------------------------------------------------------------
    # Response rendering
    # ------------------------------------------------------------------

    async def _reveal_markdown(self, text: str) -> None:
        """Render *text* as Markdown, revealing it line by line.

        Waits for the full LLM response before starting so the Markdown
        parser always sees complete syntax (closed code fences, matched
        bold markers, etc.).  Uses a :class:`~rich.live.Live` display that
        accumulates lines at ~12 ms each — long enough to feel like smooth
        reveal, fast enough that even 100-line responses finish in ~1 s.
        Empty lines and lines consisting only of whitespace are shown
        immediately (no sleep) to avoid stuttering on blank separators.
        """
        lines = text.splitlines(keepends=True)
        accumulated = ""
        with Live(
            Markdown(" "),
            console=console,
            refresh_per_second=30,
            transient=False,
        ) as live:
            for line in lines:
                accumulated += line
                live.update(Markdown(accumulated))
                if line.strip():
                    await asyncio.sleep(0.012)

    # ------------------------------------------------------------------
    # _run_turn — single agent iteration
    # ------------------------------------------------------------------

    def _wrap_tool(self, fn: Any) -> Any:
        _params = list(inspect.signature(fn).parameters.keys())

        @functools.wraps(fn)
        def _wrapper(*args: Any, **kwargs: Any) -> str:
            merged = {_params[i]: v for i, v in enumerate(args)}
            merged.update(kwargs)
            name = fn.__name__

            old_content: str | None = None
            if name == "write_file":
                try:
                    fp = pathlib.Path(merged.get("path", ""))
                    old_content = fp.read_text(encoding="utf-8") if fp.exists() else None
                except Exception:
                    pass

            is_dangerous = name in ("write_file", "run_shell")

            if is_dangerous and self._mode == "ask" and name not in self._always_allowed_tools:
                _print_tool_preview(name, merged, old_content=old_content)
                path_or_cmd = merged.get("path") or merged.get("command") or ""

                live_obj = getattr(self, "_current_live", None)
                if live_obj:
                    live_obj.stop()

                try:
                    ans = display_interactive_approval(name, str(path_or_cmd))
                finally:
                    if live_obj:
                        live_obj.start()

                if ans is None:
                    return "error: Tool execution cancelled by user."
                elif ans == "no":
                    return "error: Tool execution denied by user."
                elif ans == "always":
                    self._always_allowed_tools.add(name)
                elif ans not in ("yes", "always"):
                    return (
                        f"error: Tool execution denied. "
                        f"User provided this instruction instead: {ans}"
                    )

            if self._verbose:
                _print_tool_call(name, merged)

            result: str = fn(*args, **kwargs)

            if self._verbose:
                _print_tool_result(name, str(result), merged, old_content=old_content)

            return result

        return _wrapper

    async def _run_turn(self, model: Any, user_input: str, live: Any = None) -> tuple[str, str]:
        """Send one user message, run the tool loop, return ``(response, stats_line)``.

        ``model.act()`` handles the full tool-calling cycle internally, so we
        only need to supply callbacks.  The response text is captured via
        ``on_message`` because ``ActResult`` only carries timing metadata.

        When *live* is a :class:`~rich.live.Live` instance, a keepalive task
        updates the spinner label every 100 ms and rotates tips every ~8 s.

        When :attr:`_verbose` is ``True``, each tool is wrapped with
        :func:`_wrap_tool_verbose` to print its call and result inline.
        """
        self._current_live = live
        chat = self._ensure_chat()
        chat.add_user_message(user_input)

        captured: list[str] = []
        # Spinner base label (without animated-dots suffix).
        # Standard values: "thinking" | "working" | "finishing" | "tool /path"
        active_base: list[str] = ["thinking"]

        def _on_message(msg: Any) -> None:
            """Drive the spinner state machine and capture assistant text.

            State transitions:
              tool_calls present  → "working" (or "tool /path" for file tools)
              role == "tool"      → "finishing" (tool result received)
              assistant content   → appended to *captured* for display
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
            """Capture per-round ``PredictionResult.stats`` for the post-response summary."""
            if hasattr(result, "stats"):
                stats_capture.append(result.stats)

        tok_count: list[int] = [0]

        def _on_fragment(fragment: Any, _round_index: int) -> None:
            """Count generated tokens for the spinner label."""
            tok_count[0] += 1

        tools = [self._wrap_tool(t) for t in self._tools]

        stop_evt = asyncio.Event()
        shuffled_tips = random.sample(_TIPS, len(_TIPS)) if self._show_tips else []

        async def _keepalive() -> None:
            """Update the spinner label every 100 ms; animate dots; rotate tips every ~8 s.

            Runs on the main event loop alongside ``model.act()``.  Gets CPU time
            whenever the SDK yields back to the loop during async HTTP prefill.
            """
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
                        label = (
                            f" {base}{dots}  {tok} tok"
                            if base == "thinking" and tok > 0
                            else f" {base}{dots}"
                        )
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
                config=self._inference_config if self._inference_config else None,
                on_message=_on_message,
                on_prediction_completed=_on_prediction_completed,
                on_prediction_fragment=_on_fragment,
            )
        finally:
            stop_evt.set()
            await keepalive

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

    # ------------------------------------------------------------------
    # run — main event loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Connect to LM Studio and run the interactive chat loop.

        Tab cycles the permission mode (ask → auto → strict) in-place.
        Slash commands (/help, /clear, /mode, /exit, …) are handled inline.
        Ctrl+C mid-generation cancels the current turn, rolls back the chat
        history, and returns to the prompt without exiting lmcode.
        Exits cleanly on EOF (Ctrl+D) or ``/exit``.
        """
        settings = get_settings()

        def _cycle_mode() -> None:
            """Advance to the next mode in-place (prompt redraws via invalidate)."""
            self._mode = next_mode(self._mode)

        session = make_session(cycle_mode=_cycle_mode)

        try:
            async with lms.AsyncClient() as client:
                self._client_ref = client
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

                    _rewrite_as_history(stripped)

                    if stripped.lower() in ("exit", "quit", "q"):
                        console.print(f"[{TEXT_MUTED}]bye[/]")
                        break

                    if stripped.startswith("/"):
                        if stripped == "/compact":
                            await self._do_compact()
                        elif stripped.startswith("/log"):
                            await self._do_log(stripped)
                        elif stripped.startswith("/model"):
                            await self._do_model(stripped)
                        else:
                            self._handle_slash(stripped)
                        console.print(Rule(style=f"dim {ACCENT}"))
                        continue

                    initial: Any = RenderGroup(
                        Spinner(_SPINNER, text=" thinking.", style=ACCENT),
                    )
                    self._raw_history.append(("user", stripped))
                    _interrupted = False
                    with Live(
                        initial,
                        transient=True,
                        console=console,
                        refresh_per_second=10,
                    ) as live:
                        try:
                            response, stats = await self._run_turn(model, user_input, live=live)
                        except (KeyboardInterrupt, asyncio.CancelledError):
                            # Python 3.12 asyncio raises CancelledError (not
                            # KeyboardInterrupt) inside coroutines on Ctrl+C.
                            # Uncancel the task so the loop does not re-raise.
                            _task = asyncio.current_task()
                            if _task is not None and _task.cancelling() > 0:
                                _task.uncancel()
                            _interrupted = True

                    if _interrupted:
                        # Roll back: pop the user message and rebuild the chat
                        # so no orphaned message remains in the history.
                        self._raw_history.pop()
                        self._chat = self._init_chat()
                        for _role, _msg in self._raw_history:
                            if _role == "user":
                                self._chat.add_user_message(_msg)
                            else:
                                self._chat.add_assistant_response(_msg)
                        console.print(f"\n[{TEXT_MUTED}]^C[/]")
                        console.print(f"[italic {TEXT_MUTED}]interrupted[/]")
                        console.print(Rule(style=f"dim {ACCENT}"))
                        continue

                    self._raw_history.append(("assistant", response))

                    header = Text()
                    header.append("\nlmcode", style=ACCENT_BRIGHT)
                    header.append("  ›")
                    console.print(header, highlight=False)
                    await self._reveal_markdown(response)
                    if stats and self._show_stats:
                        console.print(Align.right(Text(stats, style=f"dim {ACCENT}")))
                    console.print()

                    if self._ctx_len and not self._ctx_warned:
                        used = self._last_prompt_tokens
                        if used and used / self._ctx_len >= CTX_WARN_THRESHOLD:
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
        except (lms.LMStudioWebsocketError, lms.LMStudioServerError):
            _print_lmstudio_closed()
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
# Entry point
# ---------------------------------------------------------------------------


def run_chat(model_id: str = "auto") -> None:
    """Synchronous entry point — runs :meth:`Agent.run` via :func:`asyncio.run`."""
    asyncio.run(Agent(model_id).run())
