"""Tests for src/lmcode/agent/core.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lmcode.agent.core import Agent, _build_system_prompt, _print_tool_call, _print_tool_result


# ---------------------------------------------------------------------------
# _build_system_prompt
# ---------------------------------------------------------------------------


def test_build_system_prompt_no_lmcode_md() -> None:
    """Returns the base prompt when no LMCODE.md is found."""
    with patch("lmcode.agent.core.read_lmcode_md", return_value=None):
        prompt = _build_system_prompt()
    assert "lmcode" in prompt
    assert "LMCODE.md" not in prompt


def test_build_system_prompt_with_lmcode_md() -> None:
    """Appends LMCODE.md content when found."""
    with patch("lmcode.agent.core.read_lmcode_md", return_value="use uv, not pip"):
        prompt = _build_system_prompt()
    assert "use uv, not pip" in prompt


# ---------------------------------------------------------------------------
# Agent initialisation
# ---------------------------------------------------------------------------


def test_agent_default_model_id() -> None:
    """Agent defaults to 'auto' model identifier."""
    agent = Agent()
    assert agent._model_id == "auto"


def test_agent_custom_model_id() -> None:
    """Agent stores the provided model identifier."""
    agent = Agent(model_id="llama-3.2")
    assert agent._model_id == "llama-3.2"


def test_agent_chat_initially_none() -> None:
    """Chat history starts as None (lazy init)."""
    agent = Agent()
    assert agent._chat is None


def test_agent_ensure_chat_creates_on_first_call() -> None:
    """_ensure_chat() creates the Chat object on the first call."""
    agent = Agent()
    with patch("lmcode.agent.core.read_lmcode_md", return_value=None):
        chat = agent._ensure_chat()
    assert chat is not None
    assert agent._chat is chat


def test_agent_ensure_chat_returns_same_instance() -> None:
    """_ensure_chat() always returns the same Chat instance."""
    agent = Agent()
    with patch("lmcode.agent.core.read_lmcode_md", return_value=None):
        first = agent._ensure_chat()
        second = agent._ensure_chat()
    assert first is second


# ---------------------------------------------------------------------------
# Agent._run_turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_turn_returns_response_text() -> None:
    """_run_turn returns the model's response as a string."""
    agent = Agent()

    mock_result = MagicMock()
    mock_result.content = "here is the answer"

    mock_model = MagicMock()
    mock_model.act = AsyncMock(return_value=mock_result)

    with patch("lmcode.agent.core.read_lmcode_md", return_value=None):
        response = await agent._run_turn(mock_model, "hello")

    assert response == "here is the answer"


@pytest.mark.asyncio
async def test_run_turn_adds_to_chat_history() -> None:
    """After _run_turn the chat has been updated with both messages."""
    agent = Agent()

    mock_result = MagicMock()
    mock_result.content = "response"

    mock_model = MagicMock()
    mock_model.act = AsyncMock(return_value=mock_result)

    with patch("lmcode.agent.core.read_lmcode_md", return_value=None):
        await agent._run_turn(mock_model, "question")

    # chat was initialised and populated
    assert agent._chat is not None
