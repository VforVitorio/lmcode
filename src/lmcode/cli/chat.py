"""lmcode chat — interactive agent session."""

from __future__ import annotations

import lmstudio as lms
import typer
from rich.console import Console
from rich.text import Text

from lmcode import __version__
from lmcode.agent.core import run_chat
from lmcode.config.settings import get_settings
from lmcode.ui.banner import print_banner
from lmcode.ui.colors import ERROR, TEXT_MUTED, WARNING

app = typer.Typer()

_console = Console()


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
    """Print a clear startup error when no model is loaded in LM Studio."""
    _console.print(f"[{WARNING}]no model loaded[/]")
    msg = f"[{TEXT_MUTED}]  → In LM Studio, load a model first, then run lmcode again[/]\n"
    _console.print(msg)
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
        _exit_no_server(settings.lmstudio.base_url)

    if model == "auto" and not detected_model:
        _exit_no_model()

    display_model = detected_model if model == "auto" else model
    print_banner(__version__, model=display_model, lmstudio_connected=True)
    run_chat(model_id=model)
