"""lmcode session — view and manage past sessions."""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer()
console = Console()


@app.command("list")
def session_list() -> None:
    """List past agent sessions."""
    console.print("[yellow]lmcode session list — not implemented yet (feat/session-recording)[/yellow]")


@app.command("view")
def session_view(
    session_id: str = typer.Argument("latest", help="Session ID or 'latest'."),
) -> None:
    """Open the session viewer TUI."""
    console.print("[yellow]lmcode session view — not implemented yet (feat/session-viewer)[/yellow]")
