"""lmcode chat — interactive agent session."""

from __future__ import annotations

import sys
import time

import lmstudio as lms
import typer
from rich.console import Console
from rich.text import Text

from lmcode import __version__
from lmcode.agent.core import run_chat
from lmcode.config.settings import get_settings
from lmcode.lms_bridge import (
    daemon_up,
    is_available,
    list_downloaded_models,
    list_loaded_models,
    load_model,
    server_start,
    suggest_load_commands,
)
from lmcode.ui.banner import print_banner, print_menu_header
from lmcode.ui.colors import (
    ACCENT,
    ERROR,
    SUCCESS,
    TEXT_MUTED,
    WARNING,
)

app = typer.Typer()

_console = Console()

#: Seconds to poll after ``lms server start`` before giving up.
_SERVER_START_TIMEOUT: int = 5

#: Seconds to poll after ``lms daemon up`` before giving up.
_DAEMON_START_TIMEOUT: int = 30

#: Seconds between connection retries.
_SERVER_POLL_INTERVAL: float = 1.0

# ---------------------------------------------------------------------------
# Arrow-key picker — pure ANSI, no prompt_toolkit Application
# ---------------------------------------------------------------------------

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


def _pick(title: str, choices: list[tuple[str, str]]) -> str | None:
    """Arrow-key list selector — returns selected key or None on cancel/Esc.

    Renders a minimal text menu using direct ANSI escape codes so there are no
    cursor-highlight artifacts from prompt_toolkit's Application renderer.
    """
    fg_accent = _ansi_fg(ACCENT)
    fg_muted = _ansi_fg(TEXT_MUTED)
    idx = [0]
    # blank + title + blank + N choices + blank + hint = N+4 lines total
    total_lines = len(choices) + 4

    def draw(first: bool = False) -> None:
        if not first:
            sys.stdout.write(f"\033[{total_lines}A\033[J")
        sys.stdout.write(f"\n  {fg_accent}{title}{_RESET}\n\n")
        for i, (_, label) in enumerate(choices):
            if i == idx[0]:
                sys.stdout.write(f"  {fg_accent}>{_RESET} {label}\n")
            else:
                sys.stdout.write(f"    {fg_muted}{label}{_RESET}\n")
        sys.stdout.write(f"\n  {fg_muted}↑↓ navigate  ·  Enter confirm  ·  Esc cancel{_RESET}")
        sys.stdout.flush()

    sys.stdout.write(_HIDE_CURSOR)
    sys.stdout.flush()
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
                sys.stdout.write(f"\033[{total_lines}A\033[J")
                sys.stdout.flush()
                return choices[idx[0]][0]
            elif key in ("escape", "ctrl_c"):
                sys.stdout.write(f"\033[{total_lines}A\033[J")
                sys.stdout.flush()
                return None
    finally:
        sys.stdout.write(_SHOW_CURSOR)
        sys.stdout.flush()


# ---------------------------------------------------------------------------
# LM Studio connectivity helpers
# ---------------------------------------------------------------------------


def _probe_lmstudio() -> tuple[bool, str]:
    """Quick synchronous check — returns (connected, model_identifier).

    Tries to list loaded models. Returns the first loaded model's identifier
    if available, empty string if the server is up but no model is loaded.

    A socket pre-check with a 0.5 s timeout is used to avoid the multi-second
    SDK connection timeout when the server is simply not running.
    """
    import socket

    try:
        with socket.create_connection(("127.0.0.1", 1234), timeout=0.5):
            pass
    except OSError:
        return False, ""
    try:
        with lms.Client() as client:
            loaded = client.llm.list_loaded()
            if loaded:
                return True, loaded[0].identifier
            return True, ""
    except Exception:
        return False, ""


def _auto_bring_up() -> bool:
    """Automatically bring up LM Studio and its inference server with animated feedback.

    First tries ``lms server start`` (fast path when LM Studio GUI is open but
    server is off), then falls back to ``lms daemon up`` (headless, no GUI).
    Shows animated dots throughout so the user is never left looking at a frozen
    terminal.

    Returns ``True`` if the server becomes reachable, ``False`` otherwise.
    """
    fg_muted = _ansi_fg(TEXT_MUTED)
    fg_success = _ansi_fg(SUCCESS)
    fg_error = _ansi_fg(ERROR)

    import threading

    sys.stdout.write("\n")
    sys.stdout.write(_HIDE_CURSOR)
    sys.stdout.flush()

    def _poll_with_animation(label: str, max_rounds: int) -> bool:
        """Animate *label* with cycling dots while polling.  Returns True on connect."""
        for _ in range(max_rounds):
            for frame in (".", "..", "..."):
                sys.stdout.write(f"\r  {fg_muted}→ {label}{frame}{_RESET}      ")
                sys.stdout.flush()
                time.sleep(1.0 / 3)
            connected, _ = _probe_lmstudio()
            if connected:
                sys.stdout.write(f"\r  {fg_success}✓ {label} ready{_RESET}              \n")
                sys.stdout.flush()
                return True
        return False

    try:
        # Fast path: fire lms server start in background so animation starts immediately.
        threading.Thread(target=server_start, daemon=True).start()
        if _poll_with_animation("starting LM Studio server", _SERVER_START_TIMEOUT):
            return True

        # Slow path: full headless daemon (LM Studio not running at all).
        threading.Thread(target=daemon_up, daemon=True).start()
        if _poll_with_animation("starting LM Studio", _DAEMON_START_TIMEOUT):
            return True

        sys.stdout.write(f"\r  {fg_error}LM Studio did not start in time{_RESET}\n")
        sys.stdout.flush()
        return False
    finally:
        sys.stdout.write(_SHOW_CURSOR)
        sys.stdout.flush()


def _startup_recovery() -> str:
    """Interactive arrow-key menu shown when no model is loaded at startup.

    Presents a two-level selection:
    1. Main menu — Load a model / Exit
    2. Model submenu — one entry per downloaded model

    After the user picks a model, loads it via ``lms load`` and returns the
    model identifier.  Raises :class:`typer.Exit` if the user exits or loading
    fails.
    """
    # --- main menu ---
    print_menu_header(__version__)
    action = _pick(
        "Welcome to lmcode  ─►  no model loaded yet",
        [("load", "Load a model"), ("exit", "Exit")],
    )

    if not action or action == "exit":
        raise typer.Exit(0)

    fg_muted = _ansi_fg(TEXT_MUTED)
    fg_success = _ansi_fg(SUCCESS)
    fg_error = _ansi_fg(ERROR)

    # --- model selection submenu (fetch list with brief feedback) ---
    sys.stdout.write(f"\n  {fg_muted}→ fetching model list…{_RESET}  ")
    sys.stdout.flush()
    downloaded = list_downloaded_models()
    sys.stdout.write(f"\r{' ' * 40}\r")
    sys.stdout.flush()

    if not downloaded:
        _console.print(f"\n[{WARNING}]no models downloaded yet[/]")
        _console.print(f"[{TEXT_MUTED}]  → run: lms get <model-name>[/]\n")
        raise typer.Exit(1)

    model_values = [(m.load_name(), f"{m.load_name()}  {m.format_size()}") for m in downloaded]
    selected = _pick("select a model", model_values)

    if not selected:
        raise typer.Exit(0)

    # --- load with animated dots (load_model blocks for up to 120 s) ---
    import threading

    result: list[bool] = []
    thread = threading.Thread(target=lambda: result.append(load_model(selected)), daemon=True)
    thread.start()

    sys.stdout.write("\n")
    sys.stdout.write(_HIDE_CURSOR)
    sys.stdout.flush()
    ok = False
    try:
        while thread.is_alive():
            for frame in (".", "..", "..."):
                sys.stdout.write(f"\r  {fg_muted}→ loading {selected}{frame}{_RESET}      ")
                sys.stdout.flush()
                time.sleep(1.0 / 3)
                if not thread.is_alive():
                    break
        thread.join()
        ok = result[0] if result else False
        if ok:
            sys.stdout.write(f"\r  {fg_success}✓ loaded {selected}{_RESET}              \n")
        else:
            sys.stdout.write(f"\r  {fg_error}failed to load '{selected}'{_RESET}              \n")
        sys.stdout.flush()
    finally:
        sys.stdout.write(_SHOW_CURSOR)
        sys.stdout.flush()

    if not ok:
        _console.print(f"[{TEXT_MUTED}]  → verify with: lms load {selected}[/]")
        _console.print(f"[{TEXT_MUTED}]  → or load a model in LM Studio and run lmcode again[/]\n")
        raise typer.Exit(1)

    return selected


def _build_model_meta(identifier: str) -> str:
    """Return a banner metadata string for the first loaded model matching *identifier*.

    Queries ``lms ps --json`` via lms_bridge and returns a dot-separated string
    of whichever metadata fields are available, e.g. ``"llama  ·  4.5 GB  ·  32k ctx"``.
    Returns an empty string when lms is absent, no models are loaded, or no
    metadata is available for the given identifier.
    """
    models = list_loaded_models()
    match = next((m for m in models if m.identifier == identifier), None)
    if match is None and models:
        match = models[0]
    if match is None:
        return ""
    parts = [p for p in [match.architecture, match.format_size(), match.format_context()] if p]
    return "  ·  ".join(parts)


def _exit_no_server(base_url: str) -> None:
    """Print a clear startup error when the LM Studio server is not reachable."""
    _console.print(f"[{ERROR}]error:[/] cannot reach LM Studio at {base_url}")
    row = Text()
    row.append("  → ", style=TEXT_MUTED)
    row.append("Open LM Studio", style=TEXT_MUTED)
    row.append(" and enable the local server ", style=TEXT_MUTED)
    row.append("(Developer → Start Server)", style=TEXT_MUTED)
    _console.print(row)
    _console.print(f"[{TEXT_MUTED}]  → then run lmcode again[/]\n")
    raise typer.Exit(1)


def _exit_no_model() -> None:
    """Print a static error when no model could be loaded and lms is unavailable.

    Only reached when ``lms`` is not on PATH so the interactive recovery menu
    cannot be shown.
    """
    _console.print(f"[{WARNING}]no model loaded[/]")

    if is_available():
        downloaded = list_downloaded_models()
        if not downloaded:
            _console.print(f"[{TEXT_MUTED}]  → no models downloaded yet — get and load one:[/]")
            for cmd in suggest_load_commands():
                _console.print(f"  [bold]{cmd}[/]")
            _console.print(f"[{TEXT_MUTED}]  → then run lmcode again[/]\n")
        else:
            _console.print(f"[{TEXT_MUTED}]  → could not load model automatically[/]")
            _console.print(
                f"[{TEXT_MUTED}]  → try manually: lms load {downloaded[0].load_name()}[/]\n"
            )
    else:
        _console.print(
            f"[{TEXT_MUTED}]  → In LM Studio, load a model first, then run lmcode again[/]\n"
        )

    raise typer.Exit(1)


@app.callback(invoke_without_command=True)
def chat(
    model: str = typer.Option("auto", "--model", "-m", help="Model ID (default: auto-detect)."),
    max_rounds: int = typer.Option(50, "--max-rounds", help="Maximum agent loop iterations."),
) -> None:
    """Start an interactive coding agent session in the current directory."""
    settings = get_settings()
    connected, detected_model = _probe_lmstudio()

    if not connected:
        if is_available():
            # Auto-start LM Studio (server or daemon) with animated feedback (#34).
            if not _auto_bring_up():
                _exit_no_server(settings.lmstudio.base_url)
            connected, detected_model = _probe_lmstudio()
            if not connected:
                _exit_no_server(settings.lmstudio.base_url)
        else:
            _exit_no_server(settings.lmstudio.base_url)

    if model == "auto" and not detected_model:
        if is_available():
            detected_model = _startup_recovery()
        else:
            _exit_no_model()

    display_model = detected_model if model == "auto" else model
    model_meta = _build_model_meta(display_model) if display_model else ""
    print_banner(__version__, model=display_model, lmstudio_connected=True, model_meta=model_meta)
    run_chat(model_id=model)
