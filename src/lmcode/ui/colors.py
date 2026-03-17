"""
Color palette for lmcode terminal UI.

Adapted from the project's web palette to Rich markup hex colors.
Use these constants everywhere instead of hardcoded hex strings.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Accent / brand
# ---------------------------------------------------------------------------

ACCENT = "#a78bfa"  # violet — main brand color, headings, highlights
ACCENT_BRIGHT = "#c4b5fd"  # lighter violet — arrow, secondary accents

# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

TEXT_PRIMARY = "#ffffff"  # white — main content
TEXT_SECONDARY = "#d1d5db"  # light gray — body text, descriptions
TEXT_MUTED = "#9ca3af"  # medium gray — hints, metadata, timestamps

# ---------------------------------------------------------------------------
# Backgrounds (for Textual widgets / Panel borders)
# ---------------------------------------------------------------------------

BG_PRIMARY = "#121127"  # very dark navy — main background
BG_SECONDARY = "#1e1b4b"  # dark indigo — sidebars, panels
BG_CONTENT = "#181633"  # dark purple — content areas

# ---------------------------------------------------------------------------
# Borders / separators
# ---------------------------------------------------------------------------

BORDER = "#2d2d3a"  # subtle dark border

# ---------------------------------------------------------------------------
# Status colors
# ---------------------------------------------------------------------------

SUCCESS = "#10b981"  # green  — tool success, tests passing
WARNING = "#f59e0b"  # amber  — warnings, "not implemented yet"
ERROR = "#ef4444"  # red    — errors, failures
INFO = "#3b82f6"  # blue   — info messages, model output

# ---------------------------------------------------------------------------
# Semantic aliases (use these in UI code)
# ---------------------------------------------------------------------------

TOOL_CALL = ACCENT_BRIGHT  # color for tool call names
TOOL_RESULT = TEXT_SECONDARY
MODEL_OUTPUT = TEXT_PRIMARY
USER_INPUT = ACCENT
SESSION_META = TEXT_MUTED
DIFF_ADD = SUCCESS
DIFF_REMOVE = ERROR
