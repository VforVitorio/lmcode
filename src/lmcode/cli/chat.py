"""lmcode chat — interactive agent session."""

from __future__ import annotations

import time

import lmstudio as lms
import typer
from prompt_toolkit.shortcuts import radiolist_dialog
from prompt_toolkit.styles import Style as PTStyle
from rich.console import Console
from rich.text import Text

from lmcode import __version__
from lmcode.agent.core import run_chat
from lmcode.config.settings import get_settings
from lmcode.lms_bridge import (
    is_available,
    list_downloaded_models,
    list_loaded_models,
    load_model,
    server_start,
    suggest_load_commands,
)
from lmcode.ui.banner import print_banner
from lmcode.ui.colors import (
    ACCENT,
    BG_PRIMARY,
    BG_SECONDARY,
    ERROR,
    SUCCESS,
    TEXT_MUTED,
    TEXT_PRIMARY,
    WARNING,
)

app = typer.Typer()

_console = Console()

#: How long to wait for the server to become reachable after ``lms server start``.
_SERVER_START_TIMEOUT: int = 20

#: Seconds between connection retries while waiting for the server.
_SERVER_POLL_INTERVAL: float = 1.0

#: prompt_toolkit dialog style matching the lmcode Catppuccin palette.
_DIALOG_STYLE = PTStyle.from_dict(
    {
        "dialog": f"bg:{BG_PRIMARY}",
        "dialog.body": f"bg:{BG_PRIMARY} {TEXT_PRIMARY}",
        "dialog frame.label": f"bg:{BG_SECONDARY} {ACCENT}",
        "dialog.body radiolist": f"bg:{BG_PRIMARY}",
        "dialog.body radiolist radio": TEXT_MUTED,
        "dialog.body radiolist radio-selected": f"bold {ACCENT}",
        "button": f"bg:{BG_SECONDARY} {TEXT_PRIMARY}",
        "button.focused": f"bg:{ACCENT} {BG_PRIMARY} bold",
    }
)


def _probe_lmstudio() -> tuple[bool, str]:
    """Quick synchronous check — returns (connected, model_identifier).

    Tries to list loaded models. Returns the first loaded model's identifier
    if available, empty string if the server is up but no model is loaded.
    """
    try:
        with lms.Client() as client:
            loaded = client.llm.list_loaded()
            if loaded:
                return True, loaded[0].identifier
            return True, ""
    except Exception:
        return False, ""


def _try_start_server() -> bool:
    """Attempt to auto-start the LM Studio inference server via ``lms server start``.

    Only attempted when ``lms`` is on PATH.  Polls ``_probe_lmstudio()`` every
    second for up to ``_SERVER_START_TIMEOUT`` seconds after the start command
    returns.

    Returns:
        ``True`` if the server becomes reachable, ``False`` otherwise.
    """
    if not is_available():
        return False
    _console.print(f"[{TEXT_MUTED}]→ starting LM Studio server via lms…[/]")
    server_start()
    for _ in range(_SERVER_START_TIMEOUT):
        connected, _ = _probe_lmstudio()
        if connected:
            _console.print(f"[{SUCCESS}]✓[/] [{TEXT_MUTED}]LM Studio server is ready[/]")
            return True
        time.sleep(_SERVER_POLL_INTERVAL)
    return False


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
    action = radiolist_dialog(
        title="lmcode — no model loaded",
        text="Use ↑↓ to navigate · Enter to confirm",
        values=[
            ("load", "Load a model"),
            ("exit", "Exit"),
        ],
        style=_DIALOG_STYLE,
    ).run()

    if not action or action == "exit":
        raise typer.Exit(0)

    # --- model selection submenu ---
    downloaded = list_downloaded_models()
    if not downloaded:
        _console.print(f"\n[{WARNING}]no models downloaded yet[/]")
        _console.print(f"[{TEXT_MUTED}]  → run: lms get <model-name>[/]\n")
        raise typer.Exit(1)

    model_values = [(m.load_name(), f"{m.load_name()}  {m.format_size()}") for m in downloaded]
    selected = radiolist_dialog(
        title="select a model",
        text="Use ↑↓ to navigate · Enter to load · Esc to cancel",
        values=model_values,
        style=_DIALOG_STYLE,
    ).run()

    if not selected:
        raise typer.Exit(0)

    # --- load ---
    _console.print(f"\n[{TEXT_MUTED}]→ loading {selected}…[/]")
    if not load_model(selected):
        _console.print(f"[{ERROR}]failed to load '{selected}'[/]")
        _console.print(
            f"[{TEXT_MUTED}]  → make sure LM Studio server is running (lms server start)[/]\n"
        )
        raise typer.Exit(1)

    _console.print(f"[{SUCCESS}]✓[/] [{TEXT_MUTED}]loaded {selected}[/]\n")
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
        # Try to auto-start the server before giving up (#34).
        connected, detected_model = _probe_lmstudio() if _try_start_server() else (False, "")
        if not connected:
            _exit_no_server(settings.lmstudio.base_url)

    if model == "auto" and not detected_model:
        if is_available():
            # Show interactive recovery menu (#50).
            detected_model = _startup_recovery()
        else:
            _exit_no_model()

    display_model = detected_model if model == "auto" else model
    model_meta = _build_model_meta(display_model) if display_model else ""
    print_banner(__version__, model=display_model, lmstudio_connected=True, model_meta=model_meta)
    run_chat(model_id=model)
