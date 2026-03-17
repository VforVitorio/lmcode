"""lmcode run — one-shot task execution."""

from __future__ import annotations

import typer
from rich.console import Console

console = Console()


def run(
    task: str = typer.Argument(..., help="Task for the agent to perform."),
    model: str = typer.Option("auto", "--model", "-m", help="Model ID to use."),
) -> None:
    """Run a one-shot task and exit."""
    console.print(f"[yellow]lmcode run '{task}' — not implemented yet (feat/agent-core)[/yellow]")
    raise typer.Exit()
