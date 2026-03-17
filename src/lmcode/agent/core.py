"""Agent core — connects the CLI to LM Studio via model.act()."""

from __future__ import annotations

import asyncio
from typing import Any

import lmstudio as lms
from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner

from lmcode.config.lmcode_md import read_lmcode_md
from lmcode.config.settings import get_settings
from lmcode.tools import filesystem  # noqa: F401 — ensures @register decorators run
from lmcode.tools.registry import get_all
from lmcode.ui.colors import ACCENT, ACCENT_BRIGHT, ERROR, SUCCESS, TEXT_MUTED

console = Console()

_BASE_SYSTEM_PROMPT = """\
You are lmcode, a local AI coding agent. You help users understand, write,
debug, and refactor code. Be concise and direct.
When you need to inspect files, always use the available tools — never guess
at file contents.
"""


def _build_system_prompt() -> str:
    """Return the system prompt, appending any LMCODE.md context found in the tree."""
    extra = read_lmcode_md()
    if extra:
        return f"{_BASE_SYSTEM_PROMPT}\n\n## Project context (LMCODE.md)\n\n{extra}"
    return _BASE_SYSTEM_PROMPT


def _print_tool_call(name: str, args: dict[str, Any]) -> None:
    """Print a one-line summary of a tool invocation."""
    args_str = ", ".join(f"{k}={v!r}" for k, v in args.items())
    console.print(f"  [{TEXT_MUTED}]⚙  {name}({args_str})[/]")


def _print_tool_result(name: str, result: str) -> None:
    """Print a short preview of a tool result."""
    preview = result[:100].replace("\n", " ")
    suffix = "…" if len(result) > 100 else ""
    console.print(f"  [{SUCCESS}]✓  {name}[/] [{TEXT_MUTED}]{preview}{suffix}[/]")


class Agent:
    """Wraps LM Studio's model.act() in a multi-turn interactive session."""

    def __init__(self, model_id: str = "auto") -> None:
        """Initialise the agent with the given LM Studio model identifier."""
        self._model_id = model_id
        self._tools = get_all()
        self._chat: lms.Chat | None = None

    def _init_chat(self) -> lms.Chat:
        """Create and return a fresh Chat with the current system prompt."""
        return lms.Chat(_build_system_prompt())

    def _ensure_chat(self) -> lms.Chat:
        """Return the active Chat, creating it on the first call."""
        if self._chat is None:
            self._chat = self._init_chat()
        return self._chat

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

        Exits cleanly on 'exit'/'quit', EOF (Ctrl+D), or Ctrl+C.
        Prints a friendly error if LM Studio is unreachable.
        """
        settings = get_settings()

        try:
            async with lms.AsyncClient() as client:
                model, resolved_id = await _get_model(client, self._model_id)
                console.print(f"[{SUCCESS}]●[/]  connected — model: [{ACCENT}]{resolved_id}[/]\n")

                while True:
                    try:
                        user_input = console.input(f"[{ACCENT}]you[/]  › ")
                    except EOFError:
                        break

                    if not user_input.strip():
                        continue

                    if user_input.strip().lower() in ("exit", "quit", "q", "/exit"):
                        console.print(f"[{TEXT_MUTED}]bye[/]")
                        break

                    with Live(
                        Spinner("dots", text=f"[{TEXT_MUTED}]thinking…[/]"),
                        refresh_per_second=10,
                        console=console,
                    ):
                        response = await self._run_turn(model, user_input)

                    console.print(f"\n[{ACCENT_BRIGHT}]lmcode[/]  › {response}\n")

        except (ConnectionRefusedError, OSError) as e:
            if isinstance(e, ConnectionRefusedError) or "Connect" in str(e):
                _print_connection_error(settings.lmstudio.base_url)
            else:
                raise
        except KeyboardInterrupt:
            console.print(f"\n[{TEXT_MUTED}]interrupted[/]")


async def _get_model(client: Any, model_id: str) -> tuple[Any, str]:
    """Return a (model_handle, resolved_identifier) tuple.

    When model_id is 'auto', picks the first model currently loaded in
    LM Studio. Raises RuntimeError if no models are loaded.
    """
    if model_id != "auto":
        return await client.llm.model(model_id), model_id

    loaded = await client.llm.list_loaded()
    if not loaded:
        raise RuntimeError(
            "No models are loaded in LM Studio. Load a model first, then retry."
        )
    first = loaded[0]
    return first, first.identifier


def _print_connection_error(base_url: str) -> None:
    """Print a user-friendly message when LM Studio cannot be reached."""
    console.print(f"[{ERROR}]error:[/] cannot connect to LM Studio at {base_url}")
    console.print(f"[{TEXT_MUTED}]→ Open LM Studio and enable the local server (default: localhost:1234)[/]")


def run_chat(model_id: str = "auto") -> None:
    """Synchronous entry point — runs the async Agent.run() via asyncio."""
    asyncio.run(Agent(model_id).run())
