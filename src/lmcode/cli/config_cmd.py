"""lmcode config — read and write settings in the config TOML."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from lmcode.config.paths import config_file
from lmcode.config.settings import get_settings, reset_settings

config_app = typer.Typer(
    name="config",
    help="Read and write lmcode settings.",
    no_args_is_help=True,
)

console = Console()

# Ordered list of (section, [(field_name, ...)]). Drives the `list` output order.
_SECTIONS: list[str] = ["lmstudio", "agent", "session"]


# ---------------------------------------------------------------------------
# TOML helpers
# ---------------------------------------------------------------------------


def _load_toml(path: Path) -> dict[str, Any]:
    """Load *path* as a TOML document.

    Returns an empty dict when the file does not exist yet.
    """
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _dump_toml(data: dict[str, Any], path: Path) -> None:
    """Write *data* to *path* as TOML.

    Uses ``tomli_w`` when available; falls back to a minimal built-in
    serialiser that handles the nested string/int/float/bool/Path values
    produced by pydantic-settings.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import tomli_w  # type: ignore[import-untyped]

        with path.open("wb") as fh:
            tomli_w.dump(data, fh)
    except ModuleNotFoundError:
        _dump_toml_fallback(data, path)


def _toml_value(value: Any) -> str:
    """Serialise a single TOML value to its string representation.

    Handles str, int, float, bool, and Path.  Everything else is stringified.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    # Path and str both stringify as TOML quoted strings.
    return f'"{value}"'


def _dump_toml_fallback(data: dict[str, Any], path: Path) -> None:
    """Minimal TOML writer for flat-or-one-level-deep dicts.

    Sufficient for lmcode's config structure (top-level sections each
    containing only scalar values).  Does NOT handle arrays or nested tables
    deeper than one level.
    """
    lines: list[str] = []
    scalars: dict[str, Any] = {}
    tables: dict[str, dict[str, Any]] = {}

    for key, value in data.items():
        if isinstance(value, dict):
            tables[key] = value
        else:
            scalars[key] = value

    for key, value in scalars.items():
        lines.append(f"{key} = {_toml_value(value)}")

    for section, fields in tables.items():
        if lines:
            lines.append("")
        lines.append(f"[{section}]")
        for field_name, field_value in fields.items():
            lines.append(f"{field_name} = {_toml_value(field_value)}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Type coercion for `set`
# ---------------------------------------------------------------------------


def _coerce_value(raw: str) -> Any:
    """Coerce *raw* string to the most appropriate Python scalar type.

    Tries int → float → bool → str in that order.
    """
    # int
    try:
        return int(raw)
    except ValueError:
        pass
    # float
    try:
        return float(raw)
    except ValueError:
        pass
    # bool
    if raw.lower() == "true":
        return True
    if raw.lower() == "false":
        return False
    # str
    return raw


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------


@config_app.command("list")
def config_list() -> None:
    """Print all current settings grouped by section."""
    settings = get_settings()

    table = Table(show_header=False, box=None, padding=(0, 2, 0, 2))
    table.add_column("section/key", style="bold cyan")
    table.add_column("value")

    section_objs: dict[str, Any] = {
        "lmstudio": settings.lmstudio,
        "agent": settings.agent,
        "session": settings.session,
    }

    for section_name in _SECTIONS:
        table.add_row(f"[bold]{section_name}[/bold]", "")
        section_obj = section_objs[section_name]
        for field_name in section_obj.model_fields:
            raw_value = getattr(section_obj, field_name)
            table.add_row(f"  {field_name}", str(raw_value))

    console.print(table)


@config_app.command("get")
def config_get(
    key: str = typer.Argument(..., help="Dot-notation key, e.g. agent.max_file_bytes"),
) -> None:
    """Print the current value of a single setting key."""
    value = _resolve_key(key)
    if value is None:
        console.print(f"[red]error:[/red] unknown key '{key}'")
        raise typer.Exit(1)
    console.print(str(value))


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Dot-notation key, e.g. agent.max_file_bytes"),
    value: str = typer.Argument(..., help="New value to write"),
) -> None:
    """Write a new value for the given key to the config TOML file."""
    # Validate that the key exists in the current settings.
    existing = _resolve_key(key)
    if existing is None:
        console.print(f"[red]error:[/red] unknown key '{key}'")
        raise typer.Exit(1)

    parts = key.split(".", maxsplit=1)
    if len(parts) != 2:  # noqa: PLR2004
        console.print(
            f"[red]error:[/red] key must use dot notation (<section>.<field>), got '{key}'"
        )
        raise typer.Exit(1)

    section, field = parts
    coerced = _coerce_value(value)

    cfg_path = config_file()
    data = _load_toml(cfg_path)

    if section not in data:
        data[section] = {}
    data[section][field] = coerced

    _dump_toml(data, cfg_path)
    reset_settings()

    console.print(f"[green]ok:[/green] {key} = {coerced!r}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_key(key: str) -> Any | None:
    """Return the live settings value for a dot-notation *key*, or None if not found.

    Supports two-segment keys only: ``<section>.<field>``.
    """
    parts = key.split(".", maxsplit=1)
    if len(parts) != 2:  # noqa: PLR2004
        return None

    section_name, field_name = parts
    settings = get_settings()

    section_obj: Any | None = getattr(settings, section_name, None)
    if section_obj is None:
        return None

    value = getattr(section_obj, field_name, None)
    if value is None and field_name not in section_obj.model_fields:
        return None
    return value
