"""lmcode chat — interactive agent session."""

from __future__ import annotations

import typer

import lmstudio as lms
from lmcode import __version__
from lmcode.agent.core import run_chat
from lmcode.ui.banner import print_banner

app = typer.Typer()


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


@app.callback(invoke_without_command=True)
def chat(
    model: str = typer.Option("auto", "--model", "-m", help="Model ID (default: auto-detect)."),
    max_rounds: int = typer.Option(50, "--max-rounds", help="Maximum agent loop iterations."),
) -> None:
    """Start an interactive coding agent session in the current directory."""
    connected, detected_model = _probe_lmstudio()
    display_model = str(detected_model if model == "auto" else model)
    print_banner(__version__, model=display_model, mode="ask", lmstudio_connected=connected)
    run_chat(model_id=model)
