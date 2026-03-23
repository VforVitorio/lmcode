"""Tests for lmcode.cli.chat — startup banner enrichment helpers."""

from __future__ import annotations

from unittest.mock import patch

from lmcode.cli.chat import _build_model_meta
from lmcode.lms_bridge import LoadedModel


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
