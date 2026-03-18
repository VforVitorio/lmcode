"""Agent core — connects the CLI to LM Studio via model.act()."""

from __future__ import annotations

import asyncio
import functools
import inspect
import random
from collections.abc import Callable
from typing import Any

import lmstudio as lms
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from rich.align import Align
from rich.console import Console
from rich.console import Group as RenderGroup
from rich.live import Live
from rich.rule import Rule
from rich.spinner import Spinner
from rich.text import Text

from lmcode import __version__
from lmcode.config.lmcode_md import read_lmcode_md
from lmcode.config.settings import get_settings
from lmcode.tools import filesystem  # noqa: F401 — ensures @register decorators run
from lmcode.tools.registry import get_all
from lmcode.ui.colors import ACCENT, ACCENT_BRIGHT, ERROR, SUCCESS, TEXT_MUTED, WARNING
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
_SPINNER = "dots"

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
You are lmcode, a local AI coding agent. You help users understand, write,
debug, and refactor code. Be concise and direct.

Only call a tool when the user's request explicitly requires reading or
writing files, running a shell command, or searching through code.
For greetings, general questions, explanations, or anything you can answer
from your own knowledge — respond directly without calling any tools.
When you do need to inspect a file, always use the available tools rather
than guessing at its contents.

Never output raw XML, HTML tags, JSON schemas, or tool definitions in your
responses. Always reply in plain text or Markdown.
"""

# ---------------------------------------------------------------------------
# Context window usage indicator
# ---------------------------------------------------------------------------

_CTX_ARCS: list[str] = ["○", "◔", "◑", "◕", "●"]
_CTX_WARN_THRESHOLD: float = 0.80


def _ctx_usage_line(used: int, total: int) -> str:
    """Return a compact '◑ 48%  (15.4k / 32k tokens)' string.

    *used* and *total* are token counts.  Returns an empty string when
    *total* is zero or unknown.
    """
    if not total:
        return ""
    pct = min(used / total, 1.0)
    arc = _CTX_ARCS[min(int(pct * len(_CTX_ARCS)), len(_CTX_ARCS) - 1)]

    def _k(n: int) -> str:
        return f"{n / 1_000:.1f}k" if n >= 1_000 else str(n)

    return f"{arc} {pct:.0%}  ({_k(used)} / {_k(total)} tok)"


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
    ("/status", "Show current session state"),
    ("/version", "Show the running lmcode version"),
    ("/exit", "Exit lmcode"),
]

# Rotate tips every N poll ticks inside _run_turn (1 tick = 100 ms).
_TIP_ROTATE_TICKS: int = 80  # ≈ 8 seconds per tip


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
    """Return the system prompt, appending any LMCODE.md context found in the tree."""
    extra = read_lmcode_md()
    if extra:
        return f"{_BASE_SYSTEM_PROMPT}\n\n## Project context (LMCODE.md)\n\n{extra}"
    return _BASE_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Tool call / result printing
# ---------------------------------------------------------------------------


def _print_tool_call(name: str, args: dict[str, Any]) -> None:
    """Print a one-line summary of a tool invocation."""
    args_str = ", ".join(f"{k}={v!r}" for k, v in args.items())
    console.print(f"  [{TEXT_MUTED}]⚙  {name}({args_str})[/]")


def _print_tool_result(name: str, result: str) -> None:
    """Print a short preview of a tool result."""
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
        result = fn(*args, **kwargs)
        _print_tool_result(fn.__name__, str(result))
        return result

    return _wrapper


# ---------------------------------------------------------------------------
# PromptSession factory
# ---------------------------------------------------------------------------


def _make_session(cycle_mode: Callable[[], None]) -> PromptSession:  # type: ignore[type-arg]
    """Create a PromptSession with in-place Tab mode-cycling.

    cycle_mode is called on Tab; the prompt redraws in-place via invalidate()
    without creating a new line. The dynamic prompt lambda is passed to each
    prompt_async() call so it reflects the updated mode immediately.
    """
    kb = KeyBindings()

    @kb.add("tab")
    def _cycle(event: Any) -> None:
        """Cycle mode and redraw the prompt without starting a new line."""
        cycle_mode()
        event.app.invalidate()

    return PromptSession(key_bindings=kb)


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

        if cmd == "/version":
            console.print(f"[{TEXT_MUTED}]lmcode {__version__}[/]\n")
            return True

        console.print(f"[{ERROR}]unknown command '{cmd}'[/] — type /help for the list\n")
        return True

    async def _do_compact(self) -> None:
        """Summarise the conversation history and replace it with the summary.

        Calls the model with the full raw history and asks for a concise
        paragraph summary.  The chat is then reset and the summary injected
        as an assistant context note so the model retains the gist of the
        session without the full token cost.
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

        text = summary[0] if summary else "(no summary generated)"
        msgs_compacted = len(self._raw_history)

        # Reset chat, inject summary as context note.
        self._chat = self._init_chat()
        self._chat.add_user_message("[context from compacted history]\n" + text)
        self._raw_history.clear()
        self._ctx_warned = False

        # Show result panel.
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

        model.act() is dispatched in a background thread with its own event loop
        so that synchronous tool execution (read_file, run_shell, etc.) does not
        block the main asyncio loop.  The main loop polls every 100 ms and drives
        all live.update() calls, keeping the spinner animated throughout prefill
        and tool execution phases.

        Callbacks only update shared-state lists — they never touch the Live
        display directly, which avoids cross-thread Rich Console conflicts.
        """
        chat = self._ensure_chat()
        chat.add_user_message(user_input)

        captured: list[str] = []
        stats_capture: list[Any] = []
        tok_count: list[int] = [0]
        # Spinner label updated by callbacks; consumed by the main-loop refresh.
        active_label: list[str] = [" thinking…"]

        def _on_message(msg: Any) -> None:
            """Update active_label with tool/file info; capture assistant text."""
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    path = (tc.arguments or {}).get("path", "")
                    if path:
                        active_label[0] = f" {tc.name} {path[-40:]}"
            elif hasattr(msg, "content") and hasattr(msg, "role"):
                parts = msg.content
                if isinstance(parts, list):
                    text = "".join(p.text for p in parts if hasattr(p, "text"))
                else:
                    text = str(parts)
                captured.append(text)
                active_label[0] = " thinking…"

        def _on_prediction_completed(result: Any) -> None:
            """Capture per-round PredictionResult.stats for the post-response summary."""
            if hasattr(result, "stats"):
                stats_capture.append(result.stats)

        def _on_fragment(fragment: Any, _round_index: int) -> None:
            """Count generated tokens; label is picked up by the main-loop refresh."""
            tok_count[0] += 1
            active_label[0] = f" thinking…  {tok_count[0]} tok"

        tools = [_wrap_tool_verbose(t) for t in self._tools] if self._verbose else self._tools

        # Keepalive task: updates the spinner label every 100 ms on the main
        # event loop.  model.act() must stay on the main loop (the SDK's
        # AsyncTaskManager is bound to it), so we use create_task instead of
        # a background thread.  The task runs whenever model.act() yields back
        # to the loop (async HTTP I/O during prefill and between tool calls).
        # Synchronous tool execution briefly blocks the loop, but Rich's own
        # auto_refresh thread keeps the spinner dots animated during that gap.
        stop_evt = asyncio.Event()
        shuffled_tips = random.sample(_TIPS, len(_TIPS)) if self._show_tips else []

        async def _keepalive() -> None:
            """Update spinner label every 100 ms; rotate tips every 8 s."""
            tip_idx = 0
            tick = 0
            while not stop_evt.is_set():
                if live is not None:
                    if shuffled_tips and tick > 0 and tick % _TIP_ROTATE_TICKS == 0:
                        tip_idx = (tip_idx + 1) % len(shuffled_tips)
                    rows: list[Any] = [Spinner(_SPINNER, text=active_label[0], style=ACCENT)]
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
        # _last_prompt_tokens tracks the most recent turn's prompt size, which
        # equals the current conversation history size in tokens — the right
        # value to compare against the model's context window.
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

                    self._raw_history.append(("user", stripped))
                    with Live(
                        Spinner(_SPINNER, text=" thinking…", style=ACCENT),
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
                    # One-time warning when context window is ≥ 80% full.
                    # Use last-turn prompt tokens: that equals the current
                    # conversation history size sent to the model in one request.
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
                    console.print()
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

    Returns a tuple of (max_file_bytes, ctx_len_tokens) so the caller can
    store the raw context length for usage tracking.
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
