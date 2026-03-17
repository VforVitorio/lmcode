# Plugin API

lmcode has a first-class plugin system built on [pluggy](https://pluggy.readthedocs.io/). Plugins can hook into the agent lifecycle to add logging, telemetry, custom tool sources, or UI integrations.

## How plugins are discovered

Plugins are Python packages that declare an entry point in the `lmcode.plugins` group:

```toml
# your plugin's pyproject.toml
[project.entry-points."lmcode.plugins"]
my_plugin = "my_plugin:Plugin"
```

lmcode loads all registered plugins at startup via:

```python
from importlib.metadata import entry_points
eps = entry_points(group="lmcode.plugins")
```

## Hookspecs

Defined in `src/lmcode/plugins/hookspecs.py`:

```python
class LMCodeSpec:

    @hookspec
    def on_session_start(self, session_id: str, model: str, cwd: str) -> None:
        """Called when an agent session begins."""

    @hookspec
    def on_session_end(self, session_id: str, rounds: int, exit_reason: str) -> None:
        """Called when an agent session ends."""

    @hookspec
    def on_tool_call(self, session_id: str, tool: str, args: dict) -> None:
        """Called before a tool is executed."""

    @hookspec
    def on_tool_result(self, session_id: str, tool: str, output: str, error: str) -> None:
        """Called after a tool returns."""

    @hookspec
    def on_model_response(self, session_id: str, content: str) -> None:
        """Called when the model produces a response chunk."""
```

## Writing a plugin

```python
# my_plugin/__init__.py
import pluggy

hookimpl = pluggy.HookimplMarker("lmcode")

class Plugin:
    @hookimpl
    def on_tool_call(self, session_id: str, tool: str, args: dict) -> None:
        print(f"[{session_id}] calling tool: {tool} with {args}")

    @hookimpl
    def on_session_end(self, session_id: str, rounds: int, exit_reason: str) -> None:
        print(f"Session {session_id} ended after {rounds} rounds: {exit_reason}")
```

Then declare the entry point in `pyproject.toml`:

```toml
[project.entry-points."lmcode.plugins"]
my_plugin = "my_plugin:Plugin"
```

Install your plugin in the same environment as lmcode (`uv add my-plugin` or `uv pip install -e .`) and it will be loaded automatically.

## Plugin manager

The plugin manager singleton is in `src/lmcode/plugins/manager.py`:

```python
from lmcode.plugins.manager import get_plugin_manager

pm = get_plugin_manager()
pm.hook.on_tool_call(session_id="abc", tool="read_file", args={"path": "x.py"})
```

`get_plugin_manager()` is lazy — plugins are discovered on first call.
