"""Tests for lmcode.cli.chat — startup banner enrichment and startup recovery."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import typer

from lmcode.cli.chat import (
    _auto_bring_up,
    _build_model_meta,
    _exit_no_model,
)
from lmcode.lms_bridge import DownloadedModel, LoadedModel


def _model(
    identifier: str,
    architecture: str | None = None,
    size_bytes: int | None = None,
    context_length: int | None = None,
) -> LoadedModel:
    return LoadedModel(
        identifier=identifier,
        architecture=architecture,
        size_bytes=size_bytes,
        context_length=context_length,
    )


# ---------------------------------------------------------------------------
# _build_model_meta
# ---------------------------------------------------------------------------


def test_build_model_meta_full() -> None:
    m = _model("Qwen2.5-Coder-7B", "llama", 4_831_838_208, 32000)
    with patch("lmcode.cli.chat.list_loaded_models", return_value=[m]):
        result = _build_model_meta("Qwen2.5-Coder-7B")
    assert "llama" in result
    assert "GB" in result
    assert "ctx" in result


def test_build_model_meta_partial_no_size() -> None:
    m = _model("MyModel", "mistral", None, 8192)
    with patch("lmcode.cli.chat.list_loaded_models", return_value=[m]):
        result = _build_model_meta("MyModel")
    assert "mistral" in result
    assert "GB" not in result
    assert "8k ctx" in result


def test_build_model_meta_no_metadata() -> None:
    m = _model("Bare")
    with patch("lmcode.cli.chat.list_loaded_models", return_value=[m]):
        result = _build_model_meta("Bare")
    assert result == ""


def test_build_model_meta_lms_absent() -> None:
    with patch("lmcode.cli.chat.list_loaded_models", return_value=[]):
        result = _build_model_meta("SomeModel")
    assert result == ""


def test_build_model_meta_falls_back_to_first_model() -> None:
    """When the exact identifier isn't found, fall back to first loaded model."""
    m = _model("ActualModel", "qwen", 1_000_000_000, 4096)
    with patch("lmcode.cli.chat.list_loaded_models", return_value=[m]):
        result = _build_model_meta("DifferentIdentifier")
    assert "qwen" in result


def test_build_model_meta_only_architecture() -> None:
    m = _model("M", "llama")
    with patch("lmcode.cli.chat.list_loaded_models", return_value=[m]):
        result = _build_model_meta("M")
    assert result == "llama"
    assert "·" not in result


# ---------------------------------------------------------------------------
# _exit_no_model — last-resort error (no downloads or auto-load failed)
# ---------------------------------------------------------------------------


def test_exit_no_model_lms_absent_shows_gui_hint(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch("lmcode.cli.chat.is_available", return_value=False),
        pytest.raises(typer.Exit),
    ):
        _exit_no_model()
    out = capsys.readouterr().out
    assert "LM Studio" in out


def test_exit_no_model_lms_available_no_downloads(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch("lmcode.cli.chat.is_available", return_value=True),
        patch("lmcode.cli.chat.list_downloaded_models", return_value=[]),
        patch(
            "lmcode.cli.chat.suggest_load_commands",
            return_value=["lms get MyModel@q4_k_m", "lms load MyModel", "lms ps"],
        ),
        pytest.raises(typer.Exit),
    ):
        _exit_no_model()
    out = capsys.readouterr().out
    assert "lms get" in out


def test_exit_no_model_lms_available_load_failed(capsys: pytest.CaptureFixture[str]) -> None:
    # When downloads exist but auto-load failed, show a manual fallback command.
    dm = DownloadedModel(path="/models/Qwen.gguf", identifier="Qwen2.5-Coder-7B")
    with (
        patch("lmcode.cli.chat.is_available", return_value=True),
        patch("lmcode.cli.chat.list_downloaded_models", return_value=[dm]),
        pytest.raises(typer.Exit),
    ):
        _exit_no_model()
    out = capsys.readouterr().out
    assert "Qwen2.5-Coder-7B" in out


def test_exit_no_model_always_exits_1() -> None:
    with (
        patch("lmcode.cli.chat.is_available", return_value=False),
        pytest.raises(typer.Exit) as exc_info,
    ):
        _exit_no_model()
    assert exc_info.value.exit_code == 1


# ---------------------------------------------------------------------------
# _auto_bring_up (#34)
# ---------------------------------------------------------------------------


def test_auto_bring_up_returns_true_when_server_start_succeeds() -> None:
    with (
        patch("lmcode.cli.chat.server_start"),
        patch("lmcode.cli.chat._probe_lmstudio", return_value=(True, "")),
        patch("lmcode.cli.chat.time") as mock_time,
        patch("lmcode.cli.chat.sys") as mock_sys,
    ):
        mock_time.sleep = lambda _: None
        mock_sys.stdout.write = lambda _: None
        mock_sys.stdout.flush = lambda: None
        result = _auto_bring_up()
    assert result is True


def test_auto_bring_up_falls_back_to_daemon_when_server_start_fails() -> None:
    # First _poll_with_animation (server start) always fails;
    # second (daemon up) succeeds on first try.
    probe_results = [(False, "")] * 4 + [(True, "")]
    with (
        patch("lmcode.cli.chat.server_start"),
        patch("lmcode.cli.chat.daemon_up"),
        patch("lmcode.cli.chat._probe_lmstudio", side_effect=probe_results),
        patch("lmcode.cli.chat.time") as mock_time,
        patch("lmcode.cli.chat.sys") as mock_sys,
    ):
        mock_time.sleep = lambda _: None
        mock_sys.stdout.write = lambda _: None
        mock_sys.stdout.flush = lambda: None
        result = _auto_bring_up()
    assert result is True


def test_auto_bring_up_returns_false_when_nothing_starts() -> None:
    with (
        patch("lmcode.cli.chat.server_start"),
        patch("lmcode.cli.chat.daemon_up"),
        patch("lmcode.cli.chat._probe_lmstudio", return_value=(False, "")),
        patch("lmcode.cli.chat.time") as mock_time,
        patch("lmcode.cli.chat.sys") as mock_sys,
    ):
        mock_time.sleep = lambda _: None
        mock_sys.stdout.write = lambda _: None
        mock_sys.stdout.flush = lambda: None
        result = _auto_bring_up()
    assert result is False
