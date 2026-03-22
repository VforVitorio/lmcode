"""Prompt-toolkit session factory for the lmcode interactive input loop.

Responsible for:
- Ghost-text slash-command autocomplete (fish-shell style, Tab or → to accept)
- History-based ghost text for regular input (from persistent ``~/.lmcode/history``)
- Tab key binding: cycles the permission mode when not in a slash command,
  accepts the current ghost-text suggestion when one is active
- Ctrl+R / Up-arrow persistent history search across sessions
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.application import get_app
from prompt_toolkit.auto_suggest import AutoSuggest, AutoSuggestFromHistory, Suggestion
from prompt_toolkit.filters import Condition
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style as PTStyle

from lmcode.agent._display import SLASH_COMMANDS

# ---------------------------------------------------------------------------
# Completion style
# ---------------------------------------------------------------------------

#: Style applied to the ghost-text suggestion: dim violet so it reads as a
#: natural extension of the ACCENT colour without drawing the eye.
COMPLETION_STYLE = PTStyle.from_dict({"auto-suggestion": "#4b4575"})

# ---------------------------------------------------------------------------
# History file
# ---------------------------------------------------------------------------

#: Path to the persistent prompt history file.
HISTORY_PATH: pathlib.Path = pathlib.Path.home() / ".lmcode" / "history"

# ---------------------------------------------------------------------------
# Auto-suggest providers
# ---------------------------------------------------------------------------


class _SlashAutoSuggest(AutoSuggest):
    """Ghost text for slash commands: first matching command appears dim after the cursor.

    Right-arrow or Ctrl-E accepts the full suggestion.  Only activates when
    the current input starts with ``/``.
    """

    def get_suggestion(self, buffer: Any, document: Any) -> Suggestion | None:
        """Return the suffix of the first slash command that matches the current input."""
        text = document.text
        if not text.startswith("/"):
            return None
        for cmd, _desc in SLASH_COMMANDS:
            cmd_name = cmd.split()[0]
            if cmd_name.startswith(text) and cmd_name != text:
                return Suggestion(cmd_name[len(text) :])
        return None


class _CombinedAutoSuggest(AutoSuggest):
    """Delegates to slash or history suggester based on input prefix.

    - Input starts with ``/`` → :class:`_SlashAutoSuggest`
    - All other input       → :class:`~prompt_toolkit.auto_suggest.AutoSuggestFromHistory`
    """

    _slash: AutoSuggest = _SlashAutoSuggest()
    _hist: AutoSuggest = AutoSuggestFromHistory()

    def get_suggestion(self, buffer: Any, document: Any) -> Suggestion | None:
        """Return a ghost-text suggestion appropriate for the current input."""
        if document.text.startswith("/"):
            return self._slash.get_suggestion(buffer, document)
        return self._hist.get_suggestion(buffer, document)


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------


def make_session(cycle_mode: Callable[[], None]) -> PromptSession:  # type: ignore[type-arg]
    """Create a :class:`~prompt_toolkit.PromptSession` with lmcode keybindings.

    Keybindings installed:
    - **Tab** (non-slash input): call *cycle_mode* to advance the permission mode
    - **Tab** (slash input): accept the current ghost-text slash suggestion inline
    - **Ctrl+R** / **Up-arrow**: search persistent :data:`HISTORY_PATH`

    Args:
        cycle_mode: Zero-argument callable that advances the permission mode
                    and invalidates the prompt display.
    """
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
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
        history=FileHistory(str(HISTORY_PATH)),
        auto_suggest=_CombinedAutoSuggest(),
        enable_history_search=True,
        style=COMPLETION_STYLE,
    )
