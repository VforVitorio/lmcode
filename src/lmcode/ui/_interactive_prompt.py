from __future__ import annotations

import sys

from lmcode.ui.colors import ACCENT, ACCENT_BRIGHT, TEXT_MUTED

_RESET = "\033[0m"
_HIDE_CURSOR = "\033[?25l"
_SHOW_CURSOR = "\033[?25h"


def _ansi_fg(hex_color: str) -> str:
    """Convert ``#rrggbb`` to an ANSI 24-bit foreground escape sequence."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"\033[38;2;{r};{g};{b}m"


def _read_key() -> str:
    """Read one keypress and return a normalised name.

    Handles arrow keys, Enter, Escape, and Ctrl-C cross-platform.
    """
    if sys.platform == "win32":
        import msvcrt

        raw = msvcrt.getch()
        if raw == b"\r":
            return "enter"
        if raw == b"\x1b":
            return "escape"
        if raw == b"\x03":
            return "ctrl_c"
        if raw in (b"\xe0", b"\x00"):
            raw2 = msvcrt.getch()
            if raw2 == b"H":
                return "up"
            if raw2 == b"P":
                return "down"
        return "other"
    else:
        import termios
        import tty

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch in ("\r", "\n"):
                return "enter"
            if ch == "\x1b":
                nxt = sys.stdin.read(1)
                if nxt == "[":
                    nxt2 = sys.stdin.read(1)
                    if nxt2 == "A":
                        return "up"
                    if nxt2 == "B":
                        return "down"
                return "escape"
            if ch == "\x03":
                return "ctrl_c"
            return "other"
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


def display_interactive_approval(tool_name: str, path_or_cmd: str) -> str | None:
    """Arrow-key list selector to approve a tool execution securely.
    Returns the user's decision or alternate instructions.
    Calls `_read_key()` directly to avoid prompt_toolkit layout artifacts.
    """
    choices = [
        ("yes", "Yes"),
        ("no", "No / Tell lmcode what to do instead"),
        ("always", "Yes — and allow this tool automatically from now on"),
    ]
    title = f"Allow this change? ({tool_name})"

    fg_accent = _ansi_fg(ACCENT)
    fg_muted = _ansi_fg(TEXT_MUTED)
    idx = [0]
    total_lines = len(choices) + 4

    def draw(first: bool = False) -> None:
        if not first:
            sys.stdout.write(f"\r\033[{total_lines}A\033[J")
        sys.stdout.write(f"\r\n  {fg_accent}{title}{_RESET}\n\n")
        for i, (_, label) in enumerate(choices):
            if i == idx[0]:
                sys.stdout.write(f"  {fg_accent}❯{_RESET} {label}\n")
            else:
                sys.stdout.write(f"    {fg_muted}{label}{_RESET}\n")
        sys.stdout.write(f"\n  {fg_muted}↑↓ navigate  ·  Enter confirm  ·  Esc cancel{_RESET}")
        sys.stdout.flush()

    sys.stdout.write(_HIDE_CURSOR)
    sys.stdout.flush()

    result_code: str | None = None
    try:
        draw(first=True)
        while True:
            key = _read_key()
            if key == "up":
                idx[0] = max(0, idx[0] - 1)
                draw()
            elif key == "down":
                idx[0] = min(len(choices) - 1, idx[0] + 1)
                draw()
            elif key == "enter":
                sys.stdout.write(f"\r\033[{total_lines}A\033[J")  # clear menu fully
                sys.stdout.flush()
                result_code = choices[idx[0]][0]
                break
            elif key in ("escape", "ctrl_c"):
                sys.stdout.write(f"\r\033[{total_lines}A\033[J")  # clear menu fully
                sys.stdout.flush()
                return None
    finally:
        sys.stdout.write(_SHOW_CURSOR)
        sys.stdout.flush()

    if result_code == "no":
        fg_accent_bright = _ansi_fg(ACCENT_BRIGHT)
        sys.stdout.write(
            f"\r\033[K  {fg_accent_bright}❯{_RESET} {fg_muted}Tell lmcode what to do instead: {_RESET}"
        )
        sys.stdout.flush()
        try:
            instructions = input().strip()
            if instructions:
                return instructions
            return "no"
        except (KeyboardInterrupt, EOFError):
            return None

    return result_code
