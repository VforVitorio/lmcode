"""Base types for the lmcode tool system."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    """Return type for all lmcode tools."""

    output: str
    success: bool = True
    metadata: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.output


# A Tool is just a plain Python callable.
# The LM Studio SDK converts type hints + docstring → JSON schema automatically.
Tool = Callable[..., str]
