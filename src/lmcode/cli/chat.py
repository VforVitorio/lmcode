"""lmcode chat — interactive agent session."""

from __future__ import annotations

import time

import lmstudio as lms
import typer
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
from lmcode.ui.colors import ERROR, SUCCESS, TEXT_MUTED, WARNING

app = typer.Typer()

_console = Console()

#: How long to wait for the server to become reachable after ``lms server start``.
_SERVER_START_TIMEOUT: int = 20

#: Seconds between connection retries while waiting for the server.
_SERVER_POLL_INTERVAL: float = 1.0


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


def _try_load_first_model() -> str:
    """Auto-load the first downloaded model when none is loaded.

    Called at startup when the server is reachable but no model is active.
    If ``lms`` is on PATH and at least one model is downloaded, loads it
    automatically and returns its identifier.  Returns an empty string on
    any failure or when ``lms`` is unavailable.
    """
    if not is_available():
        return ""
    downloaded = list_downloaded_models()
    if not downloaded:
        return ""
    first = downloaded[0]
    name = first.load_name()
    size = first.format_size()
    size_str = f"  [{TEXT_MUTED}]({size})[/]" if size else ""
    _console.print(f"[{TEXT_MUTED}]→ no model loaded — loading {name}{size_str}…[/]")
    if not load_model(name):
        return ""
    _console.print(f"[{SUCCESS}]✓[/] [{TEXT_MUTED}]loaded {name}[/]")
    return name


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
    _console.print(f"[{TEXT_MUTED}]  → Load a model, then run lmcode again[/]\n")
    raise typer.Exit(1)


def _exit_no_model() -> None:
    """Print a guided startup error when no model could be loaded.

    Reached only when auto-load failed or lms is unavailable.  Shows
    ``lms get`` commands when nothing is downloaded yet, or a plain message
    when ``lms`` is not installed.
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
            # Auto-load was attempted and failed.
            _console.print(
                f"[{TEXT_MUTED}]  → could not load model automatically[/]\n"
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
        # Server is up but no model is loaded — try to load one automatically (#19/#34).
        detected_model = _try_load_first_model()
        if not detected_model:
            _exit_no_model()

    display_model = detected_model if model == "auto" else model
    model_meta = _build_model_meta(display_model) if display_model else ""
    print_banner(__version__, model=display_model, lmstudio_connected=True, model_meta=model_meta)
    run_chat(model_id=model)
