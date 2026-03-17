"""Agent core — connects the CLI to LM Studio via model.act()."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import lmstudio as lms
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

from lmcode.config.lmcode_md import read_lmcode_md
from lmcode.config.settings import get_settings
from lmcode.tools import filesystem  # noqa: F401 — ensures @register decorators run
from lmcode.tools.registry import get_all
from lmcode.ui.colors import ACCENT_BRIGHT, ERROR, SUCCESS, TEXT_MUTED
from lmcode.ui.status import MODES, build_prompt, build_status_line, next_mode

console = Console()

_BASE_SYSTEM_PROMPT = """\
You are lmcode, a local AI coding agent. You help users understand, write,
debug, and refactor code. Be concise and direct.
When you need to inspect files, always use the available tools — never guess
at file contents.
"""

# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------

_SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/help", "Show this help message"),
    ("/clear", "Clear conversation history"),
    ("/mode [ask|auto|strict]", "Show or change the permission mode"),
    ("/model", "Show the current model"),
    ("/exit", "Exit lmcode"),
]


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
    """Print a one-line tip shown once at session start."""
    console.print(
        f"[{TEXT_MUTED}]tip: Tab cycles mode  ·  /help for commands"
        f"  ·  lmcode --help for CLI flags[/]\n"
    )


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

        Supported commands: /help, /clear, /mode [ask|auto|strict], /exit.
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
            console.print(f"[{TEXT_MUTED}]conversation cleared[/]\n")
            return True

        if cmd == "/model":
            console.print(f"[{TEXT_MUTED}]current model: {self._model_display}[/]")
            console.print(
                f"[{TEXT_MUTED}]to switch model, restart with: lmcode --model <id>[/]\n"
            )
            return True

        if cmd == "/mode":
            if len(parts) > 1:
                requested = parts[1].lower()
                if requested in MODES:
                    self._mode = requested
                    console.print(f"[{TEXT_MUTED}]mode → {self._mode}[/]\n")
                else:
                    valid = ", ".join(MODES)
                    console.print(f"[{ERROR}]unknown mode '{requested}'[/] — valid: {valid}\n")
            else:
                console.print(f"[{TEXT_MUTED}]current mode: {self._mode}[/]\n")
            return True

        console.print(f"[{ERROR}]unknown command '{cmd}'[/] — type /help for the list\n")
        return True

    async def _run_turn(self, model: Any, user_input: str) -> str:
        """Send one user message, run the tool loop, and return the response text.

        model.act() works on an internal copy of the chat, so we manually
        update our history with the final assistant response afterwards.
        The response text is captured via the on_message callback because
        ActResult only carries timing metadata, not the actual content.
        """
        chat = self._ensure_chat()
        chat.add_user_message(user_input)

        captured: list[str] = []

        def _on_message(msg: Any) -> None:
            """Capture the final AssistantResponse text.

            msg.content is a list of TextData objects — join their .text fields.
            """
            if hasattr(msg, "content") and hasattr(msg, "role"):
                parts = msg.content
                if isinstance(parts, list):
                    text = "".join(p.text for p in parts if hasattr(p, "text"))
                else:
                    text = str(parts)
                captured.append(text)

        await model.act(chat, tools=self._tools, on_message=_on_message)

        response_text = captured[-1] if captured else "(no response)"
        chat.add_assistant_response(response_text)
        return response_text

    async def run(self) -> None:
        """Connect to LM Studio and run the interactive chat loop.

        Tab cycles the permission mode (ask → auto → strict) in-place.
        Slash commands (/help, /clear, /mode, /exit) are handled inline.
        Exits cleanly on EOF (Ctrl+D) or Ctrl+C.
        """
        settings = get_settings()

        def _cycle_mode() -> None:
            self._mode = next_mode(self._mode)

        session = _make_session(cycle_mode=_cycle_mode)

        try:
            async with lms.AsyncClient() as client:
                model, resolved_id = await _get_model(client, self._model_id)
                self._model_display = resolved_id
                console.print(build_status_line(resolved_id) + "\n")
                _print_startup_tip()

                while True:
                    try:
                        user_input = await session.prompt_async(
                            lambda: build_prompt(self._model_display, self._mode)
                        )
                    except EOFError:
                        break

                    stripped = user_input.strip()
                    if not stripped:
                        continue

                    if stripped.lower() in ("exit", "quit", "q"):
                        console.print(f"[{TEXT_MUTED}]bye[/]")
                        break

                    if stripped.startswith("/"):
                        self._handle_slash(stripped)
                        continue

                    with Live(
                        Spinner("dots", text=" thinking…"),
                        transient=True,
                        console=console,
                        refresh_per_second=10,
                    ):
                        response = await self._run_turn(model, user_input)

                    console.print(f"\n[{ACCENT_BRIGHT}]lmcode[/]  › {response}\n")

        except SystemExit:
            pass
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


def _print_connection_error(base_url: str) -> None:
    """Print a user-friendly message when LM Studio cannot be reached."""
    console.print(f"[{ERROR}]error:[/] cannot connect to LM Studio at {base_url}")
    console.print(
        f"[{TEXT_MUTED}]→ Open LM Studio and enable the local server (default: localhost:1234)[/]"
    )  # noqa: E501


def run_chat(model_id: str = "auto") -> None:
    """Synchronous entry point — runs the async Agent.run() via asyncio."""
    asyncio.run(Agent(model_id).run())
