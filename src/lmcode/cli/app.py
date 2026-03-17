"""Root Typer application. Registers all sub-commands."""

from __future__ import annotations

import typer
from rich.console import Console

from lmcode import __version__

app = typer.Typer(
    name="lmcode",
    help="A local coding agent powered by LM Studio.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

console = Console()


def version_callback(value: bool) -> None:
    """Print version string and exit when --version is supplied."""
    if value:
        console.print(f"lmcode {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output."),
) -> None:
    """lmcode — local coding agent powered by LM Studio."""


# ---------------------------------------------------------------------------
# Sub-commands (imported here to register them)
# ---------------------------------------------------------------------------

from lmcode.cli.chat import app as chat_app  # noqa: E402
from lmcode.cli.mcp import app as mcp_app  # noqa: E402
from lmcode.cli.run import run  # noqa: E402
from lmcode.cli.session import app as session_app  # noqa: E402

app.add_typer(chat_app, name="chat", help="Start an interactive chat session.")
app.add_typer(session_app, name="session", help="View and manage past sessions.")
app.add_typer(mcp_app, name="mcp", help="Manage MCP server connections.")
app.command("run")(run)
