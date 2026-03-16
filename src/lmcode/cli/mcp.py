"""lmcode mcp — manage MCP server connections."""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer()
console = Console()


@app.command("add")
def mcp_add(
    openapi: str = typer.Option(None, "--openapi", help="OpenAPI spec URL or file path."),
    name: str = typer.Option(..., "--name", help="Name for this MCP connection."),
) -> None:
    """Add an MCP server or OpenAPI spec as agent tools."""
    console.print("[yellow]lmcode mcp add — not implemented yet (feat/mcp-openapi)[/yellow]")


@app.command("list")
def mcp_list() -> None:
    """List configured MCP connections."""
    console.print("[yellow]lmcode mcp list — not implemented yet (feat/mcp-openapi)[/yellow]")


@app.command("remove")
def mcp_remove(name: str = typer.Argument(...)) -> None:
    """Remove an MCP connection."""
    console.print("[yellow]lmcode mcp remove — not implemented yet (feat/mcp-openapi)[/yellow]")
