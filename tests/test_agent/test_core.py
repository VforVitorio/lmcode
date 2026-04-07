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


def _make_mock_model(response_text: str, rounds: int = 1) -> MagicMock:
    """Build a mock model whose act() calls on_message with a fake AssistantResponse.

    The returned ``ActResult``-shaped mock has a real ``rounds`` int
    (default ``1``, well below the default ``max_rounds=10`` cap) so
    the post-act limit check in :meth:`Agent._run_turn` does not crash
    on a ``MagicMock >= int`` comparison. Pass ``rounds=N`` to simulate
    a turn that used all N rounds for the limit-warning test.
    """

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
        # Return an ActResult-shaped mock with concrete numeric fields so
        # `getattr(result, "rounds", 0) >= max_prediction_rounds` works.
        result = MagicMock()
        result.rounds = rounds
        result.total_time_seconds = 0.1
        return result

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


def _make_mock_respond_model(response_text: str) -> MagicMock:
    """Build a mock model whose respond() returns a PredictionResult-like object.

    Mirrors :func:`_make_mock_model` but for the strict-mode path that
    uses ``model.respond()`` instead of ``model.act()``.  The side effect
    invokes ``on_prediction_fragment`` with a **single** positional arg,
    exactly like the real SDK does in ``json_api.py:1486`` — that shape
    mismatch with ``act()``'s two-arg callback was the source of a
    regression during #99 development.
    """

    async def respond_side_effect(
        history: object,
        on_message: object = None,
        on_prediction_fragment: object = None,
        **kwargs: object,
    ) -> MagicMock:
        if callable(on_prediction_fragment):
            fragment = MagicMock()
            fragment.content = "tok "
            on_prediction_fragment(fragment)  # <-- 1 arg, not 2
        text_part = MagicMock()
        text_part.text = response_text
        result = MagicMock()
        result.content = [text_part]
        result.stats = MagicMock(
            prompt_tokens_count=10,
            predicted_tokens_count=20,
            tokens_per_second=50.0,
        )
        return result

    mock = MagicMock()
    mock.respond = AsyncMock(side_effect=respond_side_effect)
    mock.act = AsyncMock()  # should never be awaited in strict mode
    return mock


@pytest.mark.asyncio
async def test_run_turn_strict_mode_uses_respond_not_act() -> None:
    """Strict mode (#99) must route through ``model.respond()`` — not ``act()``.

    ``model.act()`` refuses ``tools=[]`` with ``LMStudioValueError``, so
    strict has to take a completely different SDK path.  This test pins
    that routing: respond is awaited once, act is never awaited.
    """
    agent = Agent()
    agent._mode = "strict"
    mock_model = _make_mock_respond_model("strict reply")

    with patch("lmcode.agent.core.read_lmcode_md", return_value=None):
        response, _stats = await agent._run_turn(mock_model, "hello in strict")

    mock_model.respond.assert_awaited_once()
    mock_model.act.assert_not_awaited()
    assert response == "strict reply"
    # Ensure ``tools`` was not passed to respond — respond() doesn't
    # accept that kwarg at all.
    call_kwargs = mock_model.respond.await_args.kwargs
    assert "tools" not in call_kwargs


@pytest.mark.asyncio
async def test_run_turn_strict_mode_uses_strict_system_prompt() -> None:
    """Strict mode must pass a chat seeded with the hard strict system prompt.

    The SDK-level fix (routing through ``model.respond()``) stops the
    model from emitting *real* tool calls, but it cannot stop it from
    *fabricating* tool output in plain text — e.g. replying with "Here
    is the file content:" followed by invented code.  The strict
    system prompt is the second layer of defence that forbids that
    behaviour explicitly.

    This test pins three properties of the strict branch:

    1. ``_build_strict_system_prompt`` is actually invoked.
    2. The chat passed to ``respond()`` is a *separate* object from
       ``agent._chat`` — so switching back to ask/auto keeps the base
       prompt intact.
    3. The chat passed to ``respond()`` has a system message that
       contains the strict-mode marker.
    """
    agent = Agent()
    agent._mode = "strict"
    # run() normally appends to _raw_history before calling _run_turn; mirror
    # that here so _build_strict_chat has the current user message to replay.
    agent._raw_history = [("user", "what's in calculator.py?")]
    mock_model = _make_mock_respond_model("strict reply")

    with (
        patch("lmcode.agent.core.read_lmcode_md", return_value=None),
        patch(
            "lmcode.agent.core._build_strict_system_prompt",
            wraps=__import__(
                "lmcode.agent.core", fromlist=["_build_strict_system_prompt"]
            )._build_strict_system_prompt,
        ) as mock_builder,
    ):
        await agent._run_turn(mock_model, "what's in calculator.py?")

    mock_builder.assert_called_once()

    # The chat passed to respond() must not be the persistent chat.
    sdk_chat = mock_model.respond.await_args.args[0]
    assert sdk_chat is not agent._chat, (
        "strict mode must build a *separate* chat so self._chat retains "
        "the base system prompt for when the user switches back to ask/auto"
    )

    # The strict chat's system message must contain the hard marker.
    system_msg = sdk_chat._messages[0]
    system_text = "".join(p.text for p in system_msg.content if hasattr(p, "text"))
    assert "STRICT MODE" in system_text, (
        f"strict chat system prompt must contain 'STRICT MODE' marker, got:\n{system_text[:200]}"
    )


@pytest.mark.asyncio
async def test_run_turn_strict_mode_replays_history_into_strict_chat() -> None:
    """Prior turns in ``_raw_history`` must be replayed into the strict chat.

    Switching to strict mode mid-conversation must not lobotomise the
    model — it still needs to see what was said before so it can answer
    contextually (e.g. "explain the function we just discussed").
    """
    agent = Agent()
    agent._mode = "strict"
    # Seed two completed turns before the strict request.
    agent._raw_history = [
        ("user", "earlier question"),
        ("assistant", "earlier answer"),
        ("user", "follow-up in strict"),  # the current turn (already recorded by run())
    ]
    mock_model = _make_mock_respond_model("strict follow-up reply")

    with patch("lmcode.agent.core.read_lmcode_md", return_value=None):
        await agent._run_turn(mock_model, "follow-up in strict")

    sdk_chat = mock_model.respond.await_args.args[0]
    # Expect: system + 3 history messages = 4 total.
    roles = [m.__class__.__name__ for m in sdk_chat._messages]
    assert roles[0] == "SystemPrompt"
    assert len(sdk_chat._messages) == 4, (
        f"strict chat should replay 3 history entries after system msg, got roles={roles}"
    )
    # The last user message must be the current one.
    last = sdk_chat._messages[-1]
    last_text = "".join(p.text for p in last.content if hasattr(p, "text"))
    assert "follow-up in strict" in last_text


@pytest.mark.asyncio
async def test_run_turn_non_strict_modes_use_act_with_tools() -> None:
    """Ask and auto modes keep using ``model.act()`` with the full tool list.

    Regression for #99 — the strict-mode fix must not silently reroute
    the other permission modes through ``respond()``.
    """
    for mode in ("ask", "auto"):
        agent = Agent()
        agent._mode = mode
        mock_model = _make_mock_model("ok")

        with patch("lmcode.agent.core.read_lmcode_md", return_value=None):
            await agent._run_turn(mock_model, "hi")

        mock_model.act.assert_awaited_once()
        call_kwargs = mock_model.act.await_args.kwargs
        assert len(call_kwargs["tools"]) == len(agent._tools), (
            f"mode={mode} should pass all {len(agent._tools)} tools, "
            f"got {len(call_kwargs['tools'])}"
        )


# ---------------------------------------------------------------------------
# max_rounds safety boundary (#97)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_turn_passes_max_rounds_to_act() -> None:
    """``max_prediction_rounds`` must flow from the agent config into ``model.act()``.

    Pins the config→SDK plumbing: if someone removes the kwarg from the
    ``act()`` call, auto mode is once again unbounded and can loop
    forever — the exact bug #97 was filed to fix.
    """
    agent = Agent()
    agent._mode = "auto"
    mock_model = _make_mock_model("ok")

    # Patch get_settings so the test does not depend on ~/.config state.
    mock_settings = MagicMock()
    mock_settings.agent.max_rounds = 7
    mock_settings.agent.max_file_bytes = 100_000
    with (
        patch("lmcode.agent.core.read_lmcode_md", return_value=None),
        patch("lmcode.agent.core.get_settings", return_value=mock_settings),
    ):
        await agent._run_turn(mock_model, "hi")

    call_kwargs = mock_model.act.await_args.kwargs
    assert call_kwargs["max_prediction_rounds"] == 7


@pytest.mark.asyncio
async def test_run_turn_max_rounds_none_when_config_zero() -> None:
    """A non-positive ``max_rounds`` disables the cap (passes ``None`` to the SDK).

    Users who explicitly set ``max_rounds = 0`` in config.toml are opting
    out of the safety boundary; we must not send ``0`` to the SDK because
    ``model.act()`` rejects values < 1 with ``LMStudioValueError``.
    """
    agent = Agent()
    agent._mode = "auto"
    mock_model = _make_mock_model("ok")

    mock_settings = MagicMock()
    mock_settings.agent.max_rounds = 0
    mock_settings.agent.max_file_bytes = 100_000
    with (
        patch("lmcode.agent.core.read_lmcode_md", return_value=None),
        patch("lmcode.agent.core.get_settings", return_value=mock_settings),
    ):
        await agent._run_turn(mock_model, "hi")

    call_kwargs = mock_model.act.await_args.kwargs
    assert call_kwargs["max_prediction_rounds"] is None


@pytest.mark.asyncio
async def test_run_turn_flags_limit_reached_when_rounds_equal_cap() -> None:
    """Well-behaved model case: ``ActResult.rounds == cap`` → set the flag.

    Even when the SDK closes the loop cleanly (model gave up tools on the
    final round and produced a text answer), reaching the cap means the
    task was likely truncated. ``self._last_turn_limit_reached`` must be
    set so ``run()`` prints the warning.
    """
    agent = Agent()
    agent._mode = "auto"
    mock_model = _make_mock_model("done", rounds=5)

    mock_settings = MagicMock()
    mock_settings.agent.max_rounds = 5
    mock_settings.agent.max_file_bytes = 100_000
    with (
        patch("lmcode.agent.core.read_lmcode_md", return_value=None),
        patch("lmcode.agent.core.get_settings", return_value=mock_settings),
    ):
        await agent._run_turn(mock_model, "hi")

    assert agent._last_turn_limit_reached is True


@pytest.mark.asyncio
async def test_run_turn_flags_limit_reached_on_final_round_error() -> None:
    """Stubborn model case: SDK raises ``LMStudioPredictionError`` on the final round.

    When the model ignores the tools-disabled signal on the final round
    and emits a tool_call anyway, the SDK raises unconditionally with a
    message containing ``"final prediction round"``. ``_run_turn`` must
    catch this *specific* error, set the limit flag, and NOT let it
    bubble to the ``run()`` top-level handler (which catches
    ``LMStudioServerError`` — the parent class — and would misinterpret
    the crash as a server disconnect).
    """
    import lmstudio as lms

    agent = Agent()
    agent._mode = "auto"

    async def _raise_final_round(
        chat: object, tools: object, on_message: object = None, **kwargs: object
    ) -> None:
        raise lms.LMStudioPredictionError("Model requested tool use on final prediction round.")

    mock_model = MagicMock()
    mock_model.act = AsyncMock(side_effect=_raise_final_round)

    mock_settings = MagicMock()
    mock_settings.agent.max_rounds = 3
    mock_settings.agent.max_file_bytes = 100_000
    with (
        patch("lmcode.agent.core.read_lmcode_md", return_value=None),
        patch("lmcode.agent.core.get_settings", return_value=mock_settings),
    ):
        # Must NOT raise — the error is caught and converted to a flag.
        await agent._run_turn(mock_model, "loop forever please")

    assert agent._last_turn_limit_reached is True


@pytest.mark.asyncio
async def test_run_turn_reraises_unrelated_prediction_error() -> None:
    """A prediction error that is NOT the final-round case must propagate.

    The catch in ``_run_turn`` is narrow on purpose — matching only the
    SDK's ``"final prediction round"`` marker. Any other
    ``LMStudioPredictionError`` (malformed tool schema, invalid
    response format, etc.) is a real bug the user needs to see.
    """
    import lmstudio as lms

    agent = Agent()
    agent._mode = "auto"

    async def _raise_other(
        chat: object, tools: object, on_message: object = None, **kwargs: object
    ) -> None:
        raise lms.LMStudioPredictionError("something else went wrong")

    mock_model = MagicMock()
    mock_model.act = AsyncMock(side_effect=_raise_other)

    with patch("lmcode.agent.core.read_lmcode_md", return_value=None):
        with pytest.raises(lms.LMStudioPredictionError, match="something else"):
            await agent._run_turn(mock_model, "hi")

    assert agent._last_turn_limit_reached is False


# ---------------------------------------------------------------------------
# auto mode UX — spinner colour, round counter, first-time warning (#97)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_turn_passes_on_round_start_to_act() -> None:
    """``on_round_start`` must be wired so the spinner can display ``round N/M``.

    The callback lives entirely inside ``_run_turn``'s closure (it updates a
    local ``current_round`` cell read by the keepalive task), so we assert on
    two things: (1) the kwarg was passed as a callable to ``model.act()``,
    and (2) calling it with a 0-based round index does not raise.
    """
    agent = Agent()
    agent._mode = "auto"
    mock_model = _make_mock_model("ok")

    with patch("lmcode.agent.core.read_lmcode_md", return_value=None):
        await agent._run_turn(mock_model, "hi")

    call_kwargs = mock_model.act.await_args.kwargs
    assert "on_round_start" in call_kwargs
    assert callable(call_kwargs["on_round_start"])
    # Must accept a 0-based round index without raising.
    call_kwargs["on_round_start"](0)
    call_kwargs["on_round_start"](2)


def test_agent_auto_warned_initially_false() -> None:
    """Fresh Agent starts with the first-time auto-mode warning un-fired."""
    agent = Agent()
    assert agent._auto_warned is False


def test_print_auto_warning_fires_once_per_session() -> None:
    """``_print_auto_warning`` sets the flag on first call and is a no-op afterwards.

    The warning is triggered from the ``_cycle_mode`` closure in ``run()`` via
    ``run_in_terminal``; we test the method directly so the test does not
    depend on prompt_toolkit's terminal plumbing. Calling it twice must
    print exactly once — the second call should exit immediately.
    """
    from lmcode.agent import _display

    agent = Agent()
    with patch.object(_display.console, "print") as mock_print:
        agent._print_auto_warning()
        assert agent._auto_warned is True
        assert mock_print.call_count == 1

        agent._print_auto_warning()
        # Flag still True and no additional prints — second call is a no-op.
        assert agent._auto_warned is True
        assert mock_print.call_count == 1


def test_cycle_mode_preserves_always_allowed_tools() -> None:
    """Tab-cycling the mode must not clear session-scoped always-allow grants.

    Regression guard for a subtle UX pitfall: if the user grants "always allow
    write_file" in ask mode and then Tab-cycles to auto → strict → ask, the
    grants should survive the round trip. The set is plain Agent state with
    no cycle hook touching it, but this test pins the invariant so a future
    refactor that adds ``_always_allowed_tools.clear()`` to the mode handler
    will be caught.
    """
    from lmcode.ui.status import next_mode

    agent = Agent()
    agent._mode = "ask"
    agent._always_allowed_tools = {"read_file", "write_file"}

    # Simulate three Tab presses: ask → auto → strict → ask.
    for _ in range(3):
        agent._mode = next_mode(agent._mode)

    assert agent._mode == "ask"
    assert agent._always_allowed_tools == {"read_file", "write_file"}


def test_print_status_includes_max_rounds_line() -> None:
    """``/status`` must surface the active ``max_rounds`` so users can verify the cap.

    The line is the only place in the running session that confirms which
    safety boundary is in effect (config / env var / CLI flag). We capture
    the Rich console output and assert the label is present.
    """
    from lmcode.agent import _display

    agent = Agent()
    mock_settings = MagicMock()
    mock_settings.agent.max_rounds = 13
    mock_settings.agent.max_file_bytes = 100_000

    printed: list[str] = []

    def _capture(obj: object = "", *args: object, **kwargs: object) -> None:
        printed.append(str(obj))

    with (
        patch("lmcode.agent.core.get_settings", return_value=mock_settings),
        patch.object(_display.console, "print", side_effect=_capture),
    ):
        agent._print_status()

    joined = "\n".join(printed)
    assert "max rounds" in joined
    assert "13" in joined


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
