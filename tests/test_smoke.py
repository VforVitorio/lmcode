"""Smoke tests — verifies the package is importable and the CLI loads."""

from __future__ import annotations

from typer.testing import CliRunner

import lmcode
from lmcode.cli.app import app

runner = CliRunner()


def test_version_string() -> None:
    assert isinstance(lmcode.__version__, str)
    assert lmcode.__version__ == "0.5.0"


def test_cli_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "lmcode" in result.output


def test_cli_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.5.0" in result.output


def test_lmcode_md_no_file(tmp_path) -> None:
    """Should return None when no LMCODE.md exists."""
    from lmcode.config.lmcode_md import read_lmcode_md

    assert read_lmcode_md(tmp_path) is None


def test_lmcode_md_found(tmp_path) -> None:
    """Should find and return content of LMCODE.md."""
    from lmcode.config.lmcode_md import read_lmcode_md

    (tmp_path / "LMCODE.md").write_text("# My project context")
    result = read_lmcode_md(tmp_path)
    assert result is not None
    assert "My project context" in result
