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
        return ToolResult(output="", error=f"File not found: {path}").error
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
    output: str = ""
    error: str = ""
    truncated: bool = False
```

Located in `src/lmcode/tools/base.py`. Provides a standard envelope for tool output.

## Registry

`src/lmcode/tools/registry.py` maintains a dict of `name → callable`. The `@register` decorator adds the function using its `__name__` as the key.

```python
from lmcode.tools.registry import get_all, get

tools = get_all()   # list[Callable] — pass to model.act(tools=tools)
fn = get("read_file")  # Callable | None
```

## Built-in tools

| Tool | File | Description |
|------|------|-------------|
| `read_file` | `tools/builtin/files.py` | Read file contents |
| `write_file` | `tools/builtin/files.py` | Write or overwrite a file |
| `list_files` | `tools/builtin/files.py` | List files matching a glob pattern |
| `run_shell` | `tools/builtin/shell.py` | Run a shell command and capture output |
| `search_code` | `tools/builtin/search.py` | Grep for a pattern across files |

> These tools are implemented in `feat/tools-base`.

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
