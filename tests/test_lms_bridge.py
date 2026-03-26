"""Tests for lmcode.lms_bridge — lms CLI subprocess wrapper."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from lmcode.lms_bridge import (
    DownloadedModel,
    LoadedModel,
    _int_or_none,
    _run_json,
    _str_or_none,
    is_available,
    list_downloaded_models,
    list_loaded_models,
    load_model,
    server_start,
    server_stop,
    stream_model_log,
    suggest_load_commands,
    unload_model,
)

# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------


def test_is_available_true_when_lms_on_path() -> None:
    with patch("shutil.which", return_value="/usr/local/bin/lms"):
        assert is_available() is True


def test_is_available_false_when_lms_missing() -> None:
    with patch("shutil.which", return_value=None):
        assert is_available() is False


# ---------------------------------------------------------------------------
# LoadedModel
# ---------------------------------------------------------------------------


def test_loaded_model_from_dict_full() -> None:
    data = {
        "identifier": "Qwen2.5-Coder-7B",
        "architecture": "llama",
        "sizeBytes": 4_500_000_000,
        "contextLength": 32768,
        "type": "llm",
        "extra_key": "ignored_but_stored",
    }
    m = LoadedModel.from_dict(data)
    assert m.identifier == "Qwen2.5-Coder-7B"
    assert m.architecture == "llama"
    assert m.size_bytes == 4_500_000_000
    assert m.context_length == 32768
    assert m.model_type == "llm"
    assert "extra_key" in m.extra


def test_loaded_model_from_dict_minimal() -> None:
    m = LoadedModel.from_dict({"identifier": "my-model"})
    assert m.identifier == "my-model"
    assert m.architecture is None
    assert m.size_bytes is None
    assert m.context_length is None
    assert m.model_type is None


def test_loaded_model_from_dict_missing_identifier() -> None:
    m = LoadedModel.from_dict({})
    assert m.identifier == ""


def test_loaded_model_format_size_gb() -> None:
    m = LoadedModel(identifier="x", size_bytes=4_831_838_208)
    assert "GB" in m.format_size()
    assert "4." in m.format_size()


def test_loaded_model_format_size_unknown() -> None:
    m = LoadedModel(identifier="x", size_bytes=None)
    assert m.format_size() == ""


def test_loaded_model_format_context_k() -> None:
    m = LoadedModel(identifier="x", context_length=32000)
    assert "ctx" in m.format_context()
    assert "32" in m.format_context()


def test_loaded_model_format_context_unknown() -> None:
    m = LoadedModel(identifier="x", context_length=None)
    assert m.format_context() == ""


# ---------------------------------------------------------------------------
# DownloadedModel
# ---------------------------------------------------------------------------


def test_downloaded_model_from_dict_full() -> None:
    data = {
        "path": "/models/Qwen2.5-Coder-7B.gguf",
        "identifier": "Qwen2.5-Coder-7B",
        "architecture": "llama",
        "sizeBytes": 4_500_000_000,
    }
    m = DownloadedModel.from_dict(data)
    assert m.path == "/models/Qwen2.5-Coder-7B.gguf"
    assert m.identifier == "Qwen2.5-Coder-7B"
    assert m.architecture == "llama"
    assert m.size_bytes == 4_500_000_000


def test_downloaded_model_from_dict_minimal() -> None:
    m = DownloadedModel.from_dict({"path": "/some/file.gguf"})
    assert m.path == "/some/file.gguf"
    assert m.identifier is None


def test_downloaded_model_from_dict_uses_model_key_when_no_identifier() -> None:
    """lms ls --json returns 'modelKey', not 'identifier'."""
    data = {"path": "/models/file.gguf", "modelKey": "qwen2.5-coder-7b-instruct"}
    m = DownloadedModel.from_dict(data)
    assert m.identifier == "qwen2.5-coder-7b-instruct"
    assert m.load_name() == "qwen2.5-coder-7b-instruct"


def test_downloaded_model_load_name_uses_identifier_when_present() -> None:
    m = DownloadedModel(path="/models/file.gguf", identifier="qwen2.5-coder-7b")
    assert m.load_name() == "qwen2.5-coder-7b"


def test_downloaded_model_load_name_strips_gguf_extension() -> None:
    m = DownloadedModel(path="/models/qwen2.5-coder-7b-q4_k_m.gguf", identifier=None)
    assert m.load_name() == "qwen2.5-coder-7b-q4_k_m"
    assert ".gguf" not in m.load_name()


def test_downloaded_model_load_name_handles_windows_path() -> None:
    m = DownloadedModel(path="C:\\models\\my-model.gguf", identifier=None)
    assert m.load_name() == "my-model"


def test_downloaded_model_format_size() -> None:
    m = DownloadedModel(path="/x", size_bytes=4_831_838_208)
    assert "GB" in m.format_size()
    assert m.format_size() != ""


def test_downloaded_model_format_size_unknown() -> None:
    m = DownloadedModel(path="/x", size_bytes=None)
    assert m.format_size() == ""


# ---------------------------------------------------------------------------
# list_loaded_models
# ---------------------------------------------------------------------------


def _make_ps_output(models: list[dict[str, object]]) -> MagicMock:
    """Return a mock subprocess.run result with JSON stdout."""
    mock = MagicMock()
    mock.stdout = json.dumps(models)
    return mock


def test_list_loaded_models_returns_models() -> None:
    payload = [
        {
            "identifier": "ModelA",
            "architecture": "llama",
            "sizeBytes": 1000,
            "contextLength": 4096,
            "type": "llm",
        },
        {"identifier": "ModelB", "type": "embedding"},
    ]
    with patch("shutil.which", return_value="/usr/bin/lms"):
        with patch("subprocess.run", return_value=_make_ps_output(payload)):
            result = list_loaded_models()
    assert len(result) == 2
    assert result[0].identifier == "ModelA"
    assert result[0].architecture == "llama"
    assert result[1].identifier == "ModelB"


def test_list_loaded_models_empty_list() -> None:
    with patch("shutil.which", return_value="/usr/bin/lms"):
        with patch("subprocess.run", return_value=_make_ps_output([])):
            result = list_loaded_models()
    assert result == []


def test_list_loaded_models_lms_absent() -> None:
    with patch("shutil.which", return_value=None):
        result = list_loaded_models()
    assert result == []


def test_list_loaded_models_invalid_json() -> None:
    mock = MagicMock()
    mock.stdout = "not json {"
    with patch("shutil.which", return_value="/usr/bin/lms"):
        with patch("subprocess.run", return_value=mock):
            result = list_loaded_models()
    assert result == []


def test_list_loaded_models_subprocess_error() -> None:
    with patch("shutil.which", return_value="/usr/bin/lms"):
        with patch("subprocess.run", side_effect=subprocess.SubprocessError):
            result = list_loaded_models()
    assert result == []


def test_list_loaded_models_timeout() -> None:
    with patch("shutil.which", return_value="/usr/bin/lms"):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="lms", timeout=5)):
            result = list_loaded_models()
    assert result == []


def test_list_loaded_models_non_list_json() -> None:
    mock = MagicMock()
    mock.stdout = json.dumps({"error": "something"})
    with patch("shutil.which", return_value="/usr/bin/lms"):
        with patch("subprocess.run", return_value=mock):
            result = list_loaded_models()
    assert result == []


# ---------------------------------------------------------------------------
# list_downloaded_models
# ---------------------------------------------------------------------------


def test_list_downloaded_models_returns_models() -> None:
    payload = [
        {"path": "/models/a.gguf", "identifier": "ModelA", "sizeBytes": 1000},
        {"path": "/models/b.gguf"},
    ]
    with patch("shutil.which", return_value="/usr/bin/lms"):
        with patch("subprocess.run", return_value=_make_ps_output(payload)):
            result = list_downloaded_models()
    assert len(result) == 2
    assert result[0].path == "/models/a.gguf"


def test_list_downloaded_models_lms_absent() -> None:
    with patch("shutil.which", return_value=None):
        assert list_downloaded_models() == []


# ---------------------------------------------------------------------------
# stream_model_log
# ---------------------------------------------------------------------------


def test_stream_model_log_returns_popen_when_available() -> None:
    mock_proc = MagicMock(spec=subprocess.Popen)
    with patch("shutil.which", return_value="/usr/bin/lms"):
        with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
            result = stream_model_log()
    assert result is mock_proc
    cmd = mock_popen.call_args[0][0]
    assert "lms" in cmd
    assert "log" in cmd
    assert "--json" in cmd


def test_stream_model_log_returns_none_when_lms_absent() -> None:
    with patch("shutil.which", return_value=None):
        result = stream_model_log()
    assert result is None


def test_stream_model_log_returns_none_on_oserror() -> None:
    with patch("shutil.which", return_value="/usr/bin/lms"):
        with patch("subprocess.Popen", side_effect=OSError):
            result = stream_model_log()
    assert result is None


# ---------------------------------------------------------------------------
# suggest_load_commands
# ---------------------------------------------------------------------------


def test_suggest_load_commands_default() -> None:
    cmds = suggest_load_commands()
    assert len(cmds) == 3
    assert any("lms get" in c for c in cmds)
    assert any("lms load" in c for c in cmds)
    assert any("lms ps" in c for c in cmds)


def test_suggest_load_commands_custom_model() -> None:
    cmds = suggest_load_commands("my-model")
    assert any("my-model" in c for c in cmds)


def test_suggest_load_commands_contains_quant() -> None:
    cmds = suggest_load_commands()
    get_cmd = next(c for c in cmds if "lms get" in c)
    assert "@" in get_cmd  # e.g. @q4_k_m


# ---------------------------------------------------------------------------
# load_model
# ---------------------------------------------------------------------------


def _ok_run() -> MagicMock:
    m = MagicMock()
    m.returncode = 0
    return m


def _fail_run() -> MagicMock:
    m = MagicMock()
    m.returncode = 1
    return m


def test_load_model_returns_true_on_success() -> None:
    with patch("shutil.which", return_value="/usr/bin/lms"):
        with patch("subprocess.run", return_value=_ok_run()):
            assert load_model("Qwen2.5-Coder-7B") is True


def test_load_model_returns_false_on_nonzero_exit() -> None:
    with patch("shutil.which", return_value="/usr/bin/lms"):
        with patch("subprocess.run", return_value=_fail_run()):
            assert load_model("bad-model") is False


def test_load_model_returns_false_when_lms_absent() -> None:
    with patch("shutil.which", return_value=None):
        assert load_model("any") is False


def test_load_model_passes_gpu_and_context_flags() -> None:
    with patch("shutil.which", return_value="/usr/bin/lms"):
        with patch("subprocess.run", return_value=_ok_run()) as mock_run:
            load_model("M", gpu="max", context_length=8192)
    cmd = mock_run.call_args[0][0]
    assert "--gpu" in cmd
    assert "max" in cmd
    assert "--context-length" in cmd
    assert "8192" in cmd


def test_load_model_includes_yes_flag() -> None:
    with patch("shutil.which", return_value="/usr/bin/lms"):
        with patch("subprocess.run", return_value=_ok_run()) as mock_run:
            load_model("M")
    cmd = mock_run.call_args[0][0]
    assert "--yes" in cmd


def test_load_model_returns_false_on_timeout() -> None:
    with patch("shutil.which", return_value="/usr/bin/lms"):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="lms", timeout=120)):
            assert load_model("M") is False


# ---------------------------------------------------------------------------
# unload_model
# ---------------------------------------------------------------------------


def test_unload_model_by_identifier() -> None:
    with patch("shutil.which", return_value="/usr/bin/lms"):
        with patch("subprocess.run", return_value=_ok_run()) as mock_run:
            assert unload_model("my-model") is True
    cmd = mock_run.call_args[0][0]
    assert "unload" in cmd
    assert "my-model" in cmd


def test_unload_model_all() -> None:
    with patch("shutil.which", return_value="/usr/bin/lms"):
        with patch("subprocess.run", return_value=_ok_run()) as mock_run:
            assert unload_model(all_models=True) is True
    cmd = mock_run.call_args[0][0]
    assert "--all" in cmd


def test_unload_model_returns_false_when_lms_absent() -> None:
    with patch("shutil.which", return_value=None):
        assert unload_model("x") is False


def test_unload_model_returns_false_with_no_args() -> None:
    with patch("shutil.which", return_value="/usr/bin/lms"):
        assert unload_model() is False


# ---------------------------------------------------------------------------
# server_start / server_stop
# ---------------------------------------------------------------------------


def test_server_start_returns_true_on_success() -> None:
    with patch("shutil.which", return_value="/usr/bin/lms"):
        with patch("subprocess.run", return_value=_ok_run()):
            assert server_start() is True


def test_server_start_passes_port() -> None:
    with patch("shutil.which", return_value="/usr/bin/lms"):
        with patch("subprocess.run", return_value=_ok_run()) as mock_run:
            server_start(port=1234)
    cmd = mock_run.call_args[0][0]
    assert "--port" in cmd
    assert "1234" in cmd


def test_server_start_returns_false_when_lms_absent() -> None:
    with patch("shutil.which", return_value=None):
        assert server_start() is False


def test_server_start_returns_false_on_failure() -> None:
    with patch("shutil.which", return_value="/usr/bin/lms"):
        with patch("subprocess.run", return_value=_fail_run()):
            assert server_start() is False


def test_server_stop_returns_true_on_success() -> None:
    with patch("shutil.which", return_value="/usr/bin/lms"):
        with patch("subprocess.run", return_value=_ok_run()):
            assert server_stop() is True


def test_server_stop_returns_false_when_lms_absent() -> None:
    with patch("shutil.which", return_value=None):
        assert server_stop() is False


# ---------------------------------------------------------------------------
# _run_json (internal)
# ---------------------------------------------------------------------------


def test_run_json_returns_parsed_object() -> None:
    mock = MagicMock()
    mock.stdout = json.dumps({"key": "value"})
    with patch("shutil.which", return_value="/usr/bin/lms"):
        with patch("subprocess.run", return_value=mock):
            result = _run_json(["lms", "ps", "--json"])
    assert result == {"key": "value"}


def test_run_json_returns_none_when_lms_absent() -> None:
    with patch("shutil.which", return_value=None):
        assert _run_json(["lms", "ps"]) is None


def test_run_json_returns_none_on_bad_json() -> None:
    mock = MagicMock()
    mock.stdout = "{"
    with patch("shutil.which", return_value="/usr/bin/lms"):
        with patch("subprocess.run", return_value=mock):
            assert _run_json(["lms", "ps"]) is None


# ---------------------------------------------------------------------------
# _str_or_none / _int_or_none (helpers)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("hello", "hello"),
        ("", None),
        (None, None),
        (42, "42"),
    ],
)
def test_str_or_none(value: object, expected: str | None) -> None:
    assert _str_or_none(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        (42, 42),
        ("100", 100),
        (None, None),
        ("not_a_number", None),
        ([], None),
    ],
)
def test_int_or_none(value: object, expected: int | None) -> None:
    assert _int_or_none(value) == expected
