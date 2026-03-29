"""Tests for src/lmcode/agent/core.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lmcode.agent.core import Agent, _build_system_prompt, _wrap_tool_verbose

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


def _make_mock_model(response_text: str) -> MagicMock:
    """Build a mock model whose act() calls on_message with a fake AssistantResponse."""

    async def act_side_effect(
        chat: object, tools: object, on_message: object = None, **kwargs: object
    ) -> MagicMock:
        if callable(on_message):
            text_part = MagicMock()
            text_part.text = response_text
            msg = MagicMock()
            msg.content = [text_part]
            msg.role = "assistant"
            msg.tool_calls = None
            on_message(msg)
        return MagicMock()

    mock = MagicMock()
    mock.act = AsyncMock(side_effect=act_side_effect)
    return mock


@pytest.mark.asyncio
async def test_run_turn_returns_response_text() -> None:
    """_run_turn returns the model's response as a string."""
    agent = Agent()
    mock_model = _make_mock_model("here is the answer")

    with patch("lmcode.agent.core.read_lmcode_md", return_value=None):
        response, stats = await agent._run_turn(mock_model, "hello")

    assert response == "here is the answer"
    assert isinstance(stats, str)


@pytest.mark.asyncio
async def test_run_turn_adds_to_chat_history() -> None:
    """After _run_turn the chat has been updated with both messages."""
    agent = Agent()
    mock_model = _make_mock_model("response")

    with patch("lmcode.agent.core.read_lmcode_md", return_value=None):
        await agent._run_turn(mock_model, "question")

    assert agent._chat is not None


# ---------------------------------------------------------------------------
# _wrap_tool_verbose — positional-arg merging
# ---------------------------------------------------------------------------


def test_wrap_tool_verbose_positional_args_merged() -> None:
    """Wrapper merges positional args into kwargs by name so panels can look up values."""

    def _my_tool(path: str, flag: bool = False) -> str:
        return "ok"

    wrapped = _wrap_tool_verbose(_my_tool)

    with (
        patch("lmcode.agent.core._print_tool_call") as mock_call,
        patch("lmcode.agent.core._print_tool_result") as mock_result,
    ):
        wrapped("/some/path", True)  # positional args, no kwargs

    # _print_tool_call must receive the named dict, not an empty one
    merged = mock_call.call_args[0][1]
    assert merged["path"] == "/some/path"
    assert merged["flag"] is True

    # _print_tool_result also gets the merged dict
    merged_result = mock_result.call_args[0][2]
    assert merged_result["path"] == "/some/path"


def test_wrap_tool_verbose_kwargs_still_work() -> None:
    """Wrapper handles pure keyword-argument calls correctly."""

    def _tool(command: str) -> str:
        return "done"

    wrapped = _wrap_tool_verbose(_tool)

    with (
        patch("lmcode.agent.core._print_tool_call") as mock_call,
        patch("lmcode.agent.core._print_tool_result"),
    ):
        wrapped(command="echo hi")

    merged = mock_call.call_args[0][1]
    assert merged["command"] == "echo hi"


# ---------------------------------------------------------------------------
# Ctrl+C interrupt — chat rollback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_turn_keyboard_interrupt_propagates() -> None:
    """KeyboardInterrupt raised inside model.act() propagates out of _run_turn."""
    agent = Agent()

    async def _raise_ki(chat: object, tools: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    mock_model = MagicMock()
    mock_model.act = AsyncMock(side_effect=_raise_ki)

    with patch("lmcode.agent.core.read_lmcode_md", return_value=None):
        with pytest.raises(KeyboardInterrupt):
            await agent._run_turn(mock_model, "test")


@pytest.mark.asyncio
async def test_ctrl_c_rollback_removes_orphaned_message() -> None:
    """After Ctrl+C, _raw_history is rolled back and chat is rebuilt clean."""
    agent = Agent()

    with patch("lmcode.agent.core.read_lmcode_md", return_value=None):
        agent._ensure_chat()

    # Simulate two completed turns in history
    agent._raw_history = [("user", "first"), ("assistant", "reply")]

    # Now simulate what the run() loop does on interrupt:
    # add user message, catch KI, roll back
    agent._raw_history.append(("user", "interrupted question"))
    agent._raw_history.pop()  # rollback
    agent._chat = agent._init_chat()
    for role, msg in agent._raw_history:
        if role == "user":
            agent._chat.add_user_message(msg)
        else:
            agent._chat.add_assistant_response(msg)

    assert len(agent._raw_history) == 2
    assert agent._raw_history[-1] == ("assistant", "reply")


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_do_log_calls_stream_with_stats() -> None:
    agent = Agent()
    with patch("lmcode.agent.core.stream_model_log") as mock_stream:
        # Mock the proc being None so it doesn't try to read stdout
        mock_stream.return_value = None
        await agent._do_log("/log --stats")
        mock_stream.assert_called_once_with(stats=True)


@pytest.mark.asyncio
async def test_do_log_calls_stream_without_stats() -> None:
    agent = Agent()
    with patch("lmcode.agent.core.stream_model_log") as mock_stream:
        mock_stream.return_value = None
        await agent._do_log("/log")
        mock_stream.assert_called_once_with(stats=False)


@pytest.mark.asyncio
async def test_do_model_import_calls_import_model() -> None:
    agent = Agent()
    with patch("lmcode.agent.core.asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
        mock_thread.return_value = True
        await agent._do_model("/model import test/path.gguf")

        # We need to verify that import_model was passed to to_thread
        from lmcode.lms_bridge import import_model

        # Check that it called to_thread with import_model and the path
        # Note: the first arg to to_thread is the function
        mock_thread.assert_called_once_with(import_model, "test/path.gguf")


@pytest.mark.asyncio
async def test_do_model_import_missing_path() -> None:
    agent = Agent()
    with patch("lmcode.agent.core.asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
        with patch("lmcode.agent.core.console.print") as mock_print:
            await agent._do_model("/model import")
            mock_thread.assert_not_called()
            assert any(
                "usage: /model import" in str(args) for args, kwargs in mock_print.call_args_list
            )
