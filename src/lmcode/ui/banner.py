"""
ASCII art banner shown at lmcode chat startup.

Design: "LM" in accent purple + "─►" arrow in bright violet + "CODE" in white.
Palette from src/lmcode/ui/colors.py
"""

from __future__ import annotations

import shutil
import sys

from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from lmcode.ui.colors import (
    ACCENT,
    ACCENT_BRIGHT,
    BORDER,
    ERROR,
    SUCCESS,
    TEXT_MUTED,
    TEXT_PRIMARY,
)

# ---------------------------------------------------------------------------
# ASCII art — "LM" + "─►" + "CODE"
# Each list is one column of the banner, indexed by line number (0–5).
# ---------------------------------------------------------------------------

_LM = [
    " ██╗     ███╗   ███╗",
    " ██║     ████╗ ████║",
    " ██║     ██╔████╔██║",
    " ██║     ██║╚██╔╝██║",
    " ███████╗██║ ╚═╝ ██║",
    " ╚══════╝╚═╝     ╚═╝",
]

_ARROW = [
    "      ",
    "      ",
    "  ─►  ",
    "      ",
    "      ",
    "      ",
]

_CODE = [
    "██████╗ ██████╗ ██████╗ ███████╗",
    "██╔════╝██╔═══██╗██╔══██╗██╔════╝",
    "██║     ██║   ██║██║  ██║█████╗  ",
    "██║     ██║   ██║██║  ██║██╔══╝  ",
    "╚██████╗╚██████╔╝██████╔╝███████╗",
    " ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝",
]


def _build_art() -> Text:
    """Assemble the multi-colour ASCII art block as a Rich Text object."""
    art = Text(justify="center", no_wrap=True)
    for lm, arrow, code in zip(_LM, _ARROW, _CODE, strict=True):
        art.append(lm, style=f"bold {ACCENT}")
        art.append(arrow, style=f"bold {ACCENT_BRIGHT}")
        art.append(code + "\n", style=f"bold {TEXT_PRIMARY}")
    return art


def _status_dot(ok: bool) -> tuple[str, str]:
    """Return a (character, rich_style) pair for the LM Studio connection indicator."""
    return ("●", SUCCESS) if ok else ("●", ERROR)


def get_banner(
    version: str,
    model: str = "",
    lmstudio_connected: bool = False,
) -> Panel:
    """
    Build and return the startup banner as a Rich Panel.

    Args:
        version: lmcode version string
        model: loaded model name (empty = unknown)
        lmstudio_connected: whether LM Studio is reachable
    """
    content = Text(justify="center", no_wrap=True)

    # ASCII art block
    content.append_text(_build_art())
    content.append("\n")

    # Tagline
    content.append("  local coding agent", style=TEXT_MUTED)
    content.append("  ·  ", style=BORDER)
    content.append("powered by LM Studio\n\n", style=TEXT_MUTED)

    # Status row
    dot, dot_style = _status_dot(lmstudio_connected)
    content.append(f"  {dot} ", style=dot_style)
    content.append(
        "LM Studio connected" if lmstudio_connected else "LM Studio not found",
        style=TEXT_MUTED,
    )

    if model:
        content.append("  ·  ", style=BORDER)
        content.append(model, style=ACCENT)

    content.append("  ·  ", style=BORDER)
    content.append(f"v{version}\n", style=TEXT_MUTED)

    return Panel(
        Align.center(content),
        border_style=ACCENT,
        padding=(1, 2),
    )


def _print_compact_banner(
    console: Console,
    version: str,
    model: str,
    lmstudio_connected: bool,
) -> None:
    """Print a narrow-terminal-friendly banner with no Panel or ASCII art.

    Used when the terminal is fewer than 90 columns wide.  Two styled lines:
      lmcode  ─►  local coding agent
      ● LM Studio connected  ·  model  ·  v0.1.0
    """
    line1 = Text()
    line1.append("  lmcode", style=f"bold {ACCENT}")
    line1.append("  ─►  ", style=f"bold {ACCENT_BRIGHT}")
    line1.append("local coding agent", style=TEXT_MUTED)
    console.print(line1)

    line2 = Text()
    dot, dot_style = _status_dot(lmstudio_connected)
    line2.append(f"  {dot} ", style=dot_style)
    line2.append(
        "LM Studio connected" if lmstudio_connected else "LM Studio not found",
        style=TEXT_MUTED,
    )
    if model:
        line2.append("  ·  ", style=BORDER)
        line2.append(model, style=ACCENT)
    line2.append("  ·  ", style=BORDER)
    line2.append(f"v{version}", style=TEXT_MUTED)
    console.print(line2)


def print_banner(
    version: str,
    model: str = "",
    lmstudio_connected: bool = False,
) -> None:
    """Print the banner to stdout.

    Detects terminal width and chooses between a full Panel with ASCII art
    (width >= 90) and a compact two-line fallback (width < 90).
    """
    # Ensure stdout uses UTF-8 so Unicode block characters render correctly
    # on Windows terminals that default to cp1252.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    width = shutil.get_terminal_size((100, 24)).columns
    # The ASCII art block is ~60 chars; Panel border + padding adds ~8.
    # Full banner needs at least 70 columns; below that use the compact form.
    console = Console(legacy_windows=False, width=min(width, 100))
    if width >= 70:
        console.print(get_banner(version, model, lmstudio_connected))
    else:
        _print_compact_banner(console, version, model, lmstudio_connected)
