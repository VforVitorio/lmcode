"""SDK noise suppression — silences LM Studio WebSocket log noise at the terminal.

When LM Studio closes or a Ctrl+C interrupt fires, the SDK's background threads
emit structured JSON log lines (e.g. ``{"event": "Websocket failed, terminating
session.", ...}``) via Python's :mod:`logging` module.  Because the SDK loggers
have no configured handlers, records reach :data:`logging.lastResort` directly,
bypassing root-logger filters.  This module intercepts noise at two levels:

1. **``logging.lastResort`` override** — wraps the fallback handler so noisy
   records are dropped before they can write to stderr.
2. **``sys.stderr`` wrapper** — belt-and-suspenders guard for any direct writes
   that bypass the logging system.

Both are installed as module-level side effects when this module is first imported.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Phrases to suppress
# ---------------------------------------------------------------------------

#: Substrings that identify SDK noise records.
SDK_NOISE: tuple[str, ...] = (
    "already closed channel",
    "Websocket failed, terminating session",
)


# ---------------------------------------------------------------------------
# stderr wrapper
# ---------------------------------------------------------------------------


class _FilterSDKNoise:
    """Transparent :data:`sys.stderr` wrapper that silences SDK noise lines.

    Any write whose text contains a :data:`SDK_NOISE` substring is dropped
    silently.  All other writes pass through to the underlying stream unchanged.
    """

    def __init__(self, stream: Any) -> None:
        self._stream = stream

    def write(self, text: str) -> int:
        """Write *text* to the underlying stream unless it is SDK noise."""
        if not any(s in text for s in SDK_NOISE):
            self._stream.write(text)
        return len(text)

    def flush(self) -> None:
        """Flush the underlying stream."""
        self._stream.flush()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)


# ---------------------------------------------------------------------------
# logging.lastResort wrapper
# ---------------------------------------------------------------------------


class _FilteredLastResort:
    """Wraps :data:`logging.lastResort` to drop SDK noise records before emit.

    Records from loggers with no configured handlers bypass root-logger filters
    and arrive at :data:`logging.lastResort` directly.  This wrapper is the
    only reliable interception point for those records.
    """

    def __init__(self, original: Any) -> None:
        self._original = original

    @property
    def level(self) -> int:
        """Proxy the ``level`` attribute so logging internals still work."""
        return self._original.level  # type: ignore[no-any-return]

    def handle(self, record: logging.LogRecord) -> None:
        """Drop noisy records; forward everything else to the original handler."""
        if not any(s in record.getMessage() for s in SDK_NOISE):
            self._original.handle(record)


# ---------------------------------------------------------------------------
# Install — runs once at import time
# ---------------------------------------------------------------------------

logging.lastResort = _FilteredLastResort(logging.lastResort)  # type: ignore[assignment]
sys.stderr = _FilterSDKNoise(sys.stderr)
