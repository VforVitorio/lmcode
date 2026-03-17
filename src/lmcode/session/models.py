"""Pydantic models for session events written to JSONL."""

from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field


def _now() -> float:
    """Return the current Unix timestamp."""
    return time.time()


class BaseEvent(BaseModel):
    """Shared fields present in every session event."""

    ts: float = Field(default_factory=_now)
    session_id: str


class SessionStartEvent(BaseEvent):
    """Emitted once when an agent session begins."""

    type: Literal["session_start"] = "session_start"
    working_dir: str


class SessionEndEvent(BaseEvent):
    """Emitted once when an agent session ends."""

    type: Literal["session_end"] = "session_end"
    rounds: int


class UserMessageEvent(BaseEvent):
    """Emitted for each message the user sends."""

    type: Literal["user_message"] = "user_message"
    content: str


class ModelResponseEvent(BaseEvent):
    """Emitted for each response produced by the model."""

    type: Literal["model_response"] = "model_response"
    content: str


class ToolCallEvent(BaseEvent):
    """Emitted when the agent invokes a tool."""

    type: Literal["tool_call"] = "tool_call"
    tool: str
    args: dict[str, Any]


class ToolResultEvent(BaseEvent):
    """Emitted with the result after a tool call completes."""

    type: Literal["tool_result"] = "tool_result"
    tool: str
    result: str
    success: bool = True


class FileEditEvent(BaseEvent):
    """Emitted when a tool modifies a file (carries the unified diff)."""

    type: Literal["file_edit"] = "file_edit"
    path: str
    diff: str


SessionEvent = (
    SessionStartEvent
    | SessionEndEvent
    | UserMessageEvent
    | ModelResponseEvent
    | ToolCallEvent
    | ToolResultEvent
    | FileEditEvent
)
