"""lmcode chat — interactive agent session."""

from __future__ import annotations

import typer
from rich.console import Console

from lmcode import __version__
from lmcode.ui.banner import print_banner
from lmcode.ui.colors import WARNING

app = typer.Typer()
console = Console()


@app.callback(invoke_without_command=True)
def chat(
    model: str = typer.Option("auto", "--model", "-m", help="Model ID (default: auto-detect)."),
    max_rounds: int = typer.Option(50, "--max-rounds", help="Maximum agent loop iterations."),
) -> None:
    """Start an interactive coding agent session in the current directory."""
    print_banner(__version__, model=model if model != "auto" else "", mode="ask")
    console.print(f"[{WARNING}]agent loop not implemented yet — coming in feat/agent-core[/]")
    raise typer.Exit()
