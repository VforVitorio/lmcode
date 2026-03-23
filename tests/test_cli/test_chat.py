"""Tests for lmcode.cli.chat — startup banner enrichment and startup recovery."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import typer

from lmcode.cli.chat import (
    _build_model_meta,
    _exit_no_model,
    _try_load_first_model,
    _try_start_server,
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
# _try_load_first_model — auto-load at startup
# ---------------------------------------------------------------------------


def test_try_load_first_model_loads_and_returns_name(capsys: pytest.CaptureFixture[str]) -> None:
    dm = DownloadedModel(path="/models/Qwen.gguf", identifier="Qwen2.5-Coder-7B")
    with (
        patch("lmcode.cli.chat.is_available", return_value=True),
        patch("lmcode.cli.chat.list_downloaded_models", return_value=[dm]),
        patch("lmcode.cli.chat.load_model", return_value=True),
    ):
        result = _try_load_first_model()
    assert result == "Qwen2.5-Coder-7B"
    assert "loading" in capsys.readouterr().out


def test_try_load_first_model_returns_empty_when_lms_absent() -> None:
    with patch("lmcode.cli.chat.is_available", return_value=False):
        assert _try_load_first_model() == ""


def test_try_load_first_model_returns_empty_when_no_downloads() -> None:
    with (
        patch("lmcode.cli.chat.is_available", return_value=True),
        patch("lmcode.cli.chat.list_downloaded_models", return_value=[]),
    ):
        assert _try_load_first_model() == ""


def test_try_load_first_model_returns_empty_when_load_fails() -> None:
    dm = DownloadedModel(path="/models/Qwen.gguf", identifier="Qwen2.5-Coder-7B")
    with (
        patch("lmcode.cli.chat.is_available", return_value=True),
        patch("lmcode.cli.chat.list_downloaded_models", return_value=[dm]),
        patch("lmcode.cli.chat.load_model", return_value=False),
    ):
        assert _try_load_first_model() == ""


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
# _try_start_server (#34)
# ---------------------------------------------------------------------------


def test_try_start_server_returns_false_when_lms_absent() -> None:
    with patch("lmcode.cli.chat.is_available", return_value=False):
        assert _try_start_server() is False


def test_try_start_server_returns_true_when_server_becomes_reachable() -> None:
    with (
        patch("lmcode.cli.chat.is_available", return_value=True),
        patch("lmcode.cli.chat.server_start", return_value=True),
        patch("lmcode.cli.chat._probe_lmstudio", return_value=(True, "MyModel")),
        patch("lmcode.cli.chat.time") as mock_time,
    ):
        mock_time.sleep = lambda _: None
        result = _try_start_server()
    assert result is True


def test_try_start_server_returns_false_when_server_never_responds() -> None:
    with (
        patch("lmcode.cli.chat.is_available", return_value=True),
        patch("lmcode.cli.chat.server_start", return_value=False),
        patch("lmcode.cli.chat._probe_lmstudio", return_value=(False, "")),
        patch("lmcode.cli.chat.time") as mock_time,
    ):
        mock_time.sleep = lambda _: None
        result = _try_start_server()
    assert result is False
