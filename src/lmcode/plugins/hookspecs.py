"""pluggy hookspecs — defines all lifecycle hooks available to plugins."""

from __future__ import annotations

import pluggy

hookspec = pluggy.HookspecMarker("lmcode")
hookimpl = pluggy.HookimplMarker("lmcode")


class LMCodeSpec:
    @hookspec
    def on_session_start(self, session_id: str, working_dir: str) -> None:
        """Fired when an agent session begins."""

    @hookspec
    def on_session_end(self, session_id: str) -> None:
        """Fired when an agent session ends."""

    @hookspec
    def on_tool_call(self, tool_name: str, args: dict) -> dict | None:  # type: ignore[type-arg]
        """
        Fired before a tool executes.
        A plugin may return a modified args dict to override the call,
        or return None to leave args unchanged.
        """

    @hookspec
    def on_tool_result(self, tool_name: str, result: str) -> str | None:
        """
        Fired after a tool executes.
        A plugin may return a modified result string, or None to leave unchanged.
        """

    @hookspec
    def on_model_response(self, content: str) -> None:
        """Fired each time the model produces output (streaming chunk or full response)."""
