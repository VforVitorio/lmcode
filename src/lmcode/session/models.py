"""Pydantic models for session events written to JSONL."""

from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, Field


def _now() -> float:
    return time.time()


class BaseEvent(BaseModel):
    ts: float = Field(default_factory=_now)
    session_id: str


class SessionStartEvent(BaseEvent):
    type: Literal["session_start"] = "session_start"
    working_dir: str


class SessionEndEvent(BaseEvent):
    type: Literal["session_end"] = "session_end"
    rounds: int


class UserMessageEvent(BaseEvent):
    type: Literal["user_message"] = "user_message"
    content: str


class ModelResponseEvent(BaseEvent):
    type: Literal["model_response"] = "model_response"
    content: str


class ToolCallEvent(BaseEvent):
    type: Literal["tool_call"] = "tool_call"
    tool: str
    args: dict[str, Any]


class ToolResultEvent(BaseEvent):
    type: Literal["tool_result"] = "tool_result"
    tool: str
    result: str
    success: bool = True


class FileEditEvent(BaseEvent):
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
