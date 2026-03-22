"""Tests for src/lmcode/agent/_noise.py — SDK noise suppression."""

from __future__ import annotations

import logging
from io import StringIO
from unittest.mock import MagicMock

from lmcode.agent._noise import SDK_NOISE, _FilterSDKNoise, _FilteredLastResort


# ---------------------------------------------------------------------------
# SDK_NOISE constant
# ---------------------------------------------------------------------------


def test_sdk_noise_contains_expected_phrases() -> None:
    """SDK_NOISE includes the two known noisy phrases."""
    assert any("already closed channel" in s for s in SDK_NOISE)
    assert any("Websocket failed" in s for s in SDK_NOISE)


# ---------------------------------------------------------------------------
# _FilterSDKNoise
# ---------------------------------------------------------------------------


def test_filter_sdk_noise_passes_clean_text() -> None:
    """Normal text is written through to the underlying stream."""
    buf = StringIO()
    wrapper = _FilterSDKNoise(buf)
    wrapper.write("hello world\n")
    assert buf.getvalue() == "hello world\n"


def test_filter_sdk_noise_suppresses_channel_noise() -> None:
    """'already closed channel' lines are dropped silently."""
    buf = StringIO()
    wrapper = _FilterSDKNoise(buf)
    wrapper.write('{"event": "already closed channel", "id": 1}\n')
    assert buf.getvalue() == ""


def test_filter_sdk_noise_suppresses_websocket_noise() -> None:
    """'Websocket failed, terminating session' lines are dropped silently."""
    buf = StringIO()
    wrapper = _FilterSDKNoise(buf)
    wrapper.write('{"event": "Websocket failed, terminating session.", "ws_url": "ws://..."}\n')
    assert buf.getvalue() == ""


def test_filter_sdk_noise_returns_full_length() -> None:
    """write() always returns len(text) even when the text is suppressed."""
    buf = StringIO()
    wrapper = _FilterSDKNoise(buf)
    text = '{"event": "already closed channel"}\n'
    result = wrapper.write(text)
    assert result == len(text)


def test_filter_sdk_noise_flush_delegates() -> None:
    """flush() is forwarded to the underlying stream."""
    mock_stream = MagicMock()
    wrapper = _FilterSDKNoise(mock_stream)
    wrapper.flush()
    mock_stream.flush.assert_called_once()


def test_filter_sdk_noise_getattr_delegates() -> None:
    """Attribute access falls through to the underlying stream."""
    mock_stream = MagicMock()
    mock_stream.name = "stderr"
    wrapper = _FilterSDKNoise(mock_stream)
    assert wrapper.name == "stderr"


# ---------------------------------------------------------------------------
# _FilteredLastResort
# ---------------------------------------------------------------------------


def _make_record(message: str, level: int = logging.ERROR) -> logging.LogRecord:
    """Create a LogRecord with the given message string."""
    record = logging.LogRecord(
        name="test",
        level=level,
        pathname="",
        lineno=0,
        msg=message,
        args=(),
        exc_info=None,
    )
    return record


def test_filtered_last_resort_passes_clean_record() -> None:
    """Records without noise phrases are forwarded to the original handler."""
    original = MagicMock()
    wrapper = _FilteredLastResort(original)
    record = _make_record("normal log message")
    wrapper.handle(record)
    original.handle.assert_called_once_with(record)


def test_filtered_last_resort_drops_channel_noise() -> None:
    """Records containing 'already closed channel' are dropped."""
    original = MagicMock()
    wrapper = _FilteredLastResort(original)
    record = _make_record('{"event": "already closed channel"}')
    wrapper.handle(record)
    original.handle.assert_not_called()


def test_filtered_last_resort_drops_websocket_noise() -> None:
    """Records containing 'Websocket failed' are dropped."""
    original = MagicMock()
    wrapper = _FilteredLastResort(original)
    record = _make_record('{"event": "Websocket failed, terminating session.", "ws_url": "x"}')
    wrapper.handle(record)
    original.handle.assert_not_called()


def test_filtered_last_resort_level_proxied() -> None:
    """The level property is proxied from the original handler."""
    original = MagicMock()
    original.level = logging.WARNING
    wrapper = _FilteredLastResort(original)
    assert wrapper.level == logging.WARNING
