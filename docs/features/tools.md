# Tool System

Tools are the actions the agent can take. Each tool is a plain Python function registered via the `@register` decorator in `src/lmcode/tools/`.

## Anatomy of a tool

```python
from lmcode.tools.registry import register
from lmcode.tools.base import ToolResult

@register
def read_file(path: str) -> str:
    """Read the contents of a file at the given path."""
    try:
        content = Path(path).read_text(encoding="utf-8")
        return ToolResult(output=content).output
    except FileNotFoundError:
        return ToolResult(output=f"File not found: {path}", success=False).output
```

**Rules:**
- The function signature drives the JSON schema that LM Studio sees. Type hints are required.
- The docstring becomes the tool description shown to the model.
- Return a plain `str`. The agent loop (`model.act()`) expects string results.
- Catch exceptions and return error strings rather than raising — the agent loop handles error strings gracefully.

## `ToolResult` dataclass

```python
@dataclass
class ToolResult:
    output: str
    success: bool = True
    metadata: dict[str, Any] | None = None
```

Located in `src/lmcode/tools/base.py`. Provides a standard envelope for tool output. The `__str__` method returns `self.output`, so a `ToolResult` can be passed directly wherever a string is expected.

## `Tool` type alias

`src/lmcode/tools/base.py` exports a `Tool` type alias:

```python
from collections.abc import Callable
Tool = Callable[..., str]
```

This alias is used throughout the registry and any code that passes tools around.

## Registry

`src/lmcode/tools/registry.py` maintains a module-level dict `_registry: dict[str, Callable[..., str]]`. The `@register` decorator inserts the function using its `__name__` as the key and returns the function unchanged (so it can be used without wrapping).

```python
from lmcode.tools.registry import register, get_all, get

@register
def my_tool(x: str) -> str:
    """Example tool."""
    return x

tools = get_all()        # list[Callable[..., str]] — pass to model.act(tools=tools)
fn    = get("my_tool")  # Callable[..., str] | None
```

## Built-in tools

The tool implementation files (`tools/filesystem.py`, `tools/shell.py`, `tools/search.py`, `tools/git.py`) are currently empty stubs. No built-in tools are registered yet; they will be filled in as the `feat/tools-base` branch progresses.

| Planned tool | Planned file | Description |
|------|------|-------------|
| `read_file` | `tools/filesystem.py` | Read file contents |
| `write_file` | `tools/filesystem.py` | Write or overwrite a file |
| `list_files` | `tools/filesystem.py` | List files matching a glob pattern |
| `run_shell` | `tools/shell.py` | Run a shell command and capture output |
| `search_code` | `tools/search.py` | Grep for a pattern across files |
| `git_*` | `tools/git.py` | Git operations |

## Adding a custom tool

Create a module anywhere in the project (or in a plugin package) and decorate a function with `@register`:

```python
# my_plugin/tools.py
from lmcode.tools.registry import register

@register
def fetch_url(url: str) -> str:
    """Fetch the text content of a URL."""
    import urllib.request
    with urllib.request.urlopen(url) as r:
        return r.read().decode("utf-8")[:4000]
```

Then expose the module in your plugin's entry point so it gets imported at startup. See [plugin docs](../api/plugins.md).
