"""Status line and prompt rendering for the chat UI."""

from __future__ import annotations

from prompt_toolkit.formatted_text import HTML

# Mode cycle order and their hex colours
MODES: list[str] = ["ask", "auto", "strict"]

_MODE_COLORS: dict[str, str] = {
    "ask": "#f59e0b",
    "auto": "#3b82f6",
    "strict": "#ef4444",
}

_ACCENT = "#a78bfa"
_SUCCESS = "#10b981"
_MUTED = "#6b7280"


def next_mode(current: str) -> str:
    """Return the next mode in the cycle: ask → auto → strict → ask."""
    idx = MODES.index(current) if current in MODES else 0
    return MODES[(idx + 1) % len(MODES)]


def build_status_line(model: str) -> str:
    """Return a Rich markup string shown once after connecting to LM Studio.

    Example: ● lmcode (qwen2.5-1.5b-instruct)  ·  connected
    Mode is intentionally omitted — it is always visible in the live prompt.
    """
    model_str = f" ({model})" if model else ""
    return f"[{_SUCCESS}]●[/]  [{_ACCENT}]lmcode{model_str}[/]  [{_MUTED}]connected[/]"


def build_prompt(model: str, mode: str) -> HTML:
    """Return the prompt HTML for prompt_toolkit, including model and mode.

    Example: ● lmcode (qwen2.5-1.5b-instruct)  [ask]  ›
    Called on every redraw, so Tab-cycling the mode updates it in-place.
    """
    color = _MODE_COLORS.get(mode, _MUTED)
    model_str = f" ({model})" if model else ""
    return HTML(
        f'<style fg="{_SUCCESS}">●</style>'
        f'  <style fg="{_ACCENT}">lmcode{model_str}</style>'
        f'  <style fg="{color}">[{mode}]</style>'
        "  › "
    )
