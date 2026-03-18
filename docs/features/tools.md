# Tool System

Tools are the actions the agent can take. Each tool is a plain Python function registered via the `@register` decorator in `src/lmcode/tools/`.

## Built-in tools

All built-in tools are registered at import time. The agent core imports `lmcode.tools.filesystem` which triggers all `@register` decorators, and the registry is queried with `get_all()` to pass tools to `model.act()`.

| Tool | File | Description |
|------|------|-------------|
| `read_file` | `tools/filesystem.py` | Read file contents (token-aware byte cap) |
| `write_file` | `tools/filesystem.py` | Write or overwrite a file (binary types blocked) |
| `list_files` | `tools/filesystem.py` | List files matching a glob pattern, up to 500 entries |
| `run_shell` | `tools/shell.py` | Run a shell command and capture output (capped at 10 000 chars) |
| `search_code` | `tools/search.py` | Search for a regex pattern across files (ripgrep or pure-Python fallback) |

### `read_file(path: str) -> str`

Reads a text file. The byte cap is derived from the model's context window at startup (formula: `clamp(ctx_tokens * 4 bytes * 0.20, 50_000, 500_000)`). Binary files are rejected. When truncated, the output includes a notice with the file size and current limit.

### `write_file(path: str, content: str) -> str`

Writes UTF-8 content to a file, creating parent directories as needed. Refuses to write files with binary extensions (`.pyc`, `.exe`, `.zip`, images, etc.). Returns `"wrote N bytes to path"` on success.

### `list_files(path: str = ".", pattern: str = "*") -> str`

Recursively lists files under `path` matching `pattern`. Skips `.git/`, `__pycache__/`, and `.venv/`. Returns newline-joined relative paths, capped at 500 entries.

### `run_shell(command: str, timeout: int = 30) -> str`

Runs `command` in a system shell (`shell=True`). Returns combined stdout and stderr (stderr prefixed with `[stderr]`), capped at 10 000 characters. Returns a timeout message if the process exceeds `timeout` seconds.

> WARNING: This tool runs arbitrary shell commands with the same privileges as the lmcode process. Only use in trusted environments.

### `search_code(pattern: str, path: str = ".", file_glob: str = "**/*") -> str`

Searches for a regex pattern across files. Uses `rg` (ripgrep) when available on PATH; falls back to a pure-Python `re` walk. Returns up to 200 `path:line: content` matches. Returns `"(no matches found)"` when nothing matched.

## Anatomy of a tool

```python
from lmcode.tools.registry import register

@register
def my_tool(path: str, limit: int = 100) -> str:
    """Short description shown to the model.

    Longer explanation if needed.
    """
    return "result"
```

**Rules:**
- Type hints on all parameters are required — they drive the JSON schema that LM Studio sees.
- The docstring becomes the tool description shown to the model.
- Return a plain `str`. The agent loop (`model.act()`) expects string results.
- Catch exceptions and return error strings rather than raising — the agent handles error strings gracefully.

## `ToolResult` dataclass

Located in `src/lmcode/tools/base.py`. Provides a structured envelope for tool output:

```python
@dataclass
class ToolResult:
    output: str
    success: bool = True
    metadata: dict[str, Any] | None = None
```

`ToolResult.__str__` returns `self.output`, so a `ToolResult` can be passed wherever a string is expected.

## `Tool` type alias

```python
from collections.abc import Callable
Tool = Callable[..., str]
```

## Registry

`src/lmcode/tools/registry.py` maintains a module-level dict `_registry: dict[str, Callable[..., str]]`. The `@register` decorator inserts the function using its `__name__` as the key.

```python
from lmcode.tools.registry import register, get_all, get

tools = get_all()        # list[Callable[..., str]] — pass to model.act(tools=tools)
fn    = get("my_tool")  # Callable[..., str] | None
```

## Verbose mode

When verbose is on (default), each tool call and its result are printed inline:

```
  ⚙  read_file(path='src/main.py')
  ✓  read_file  def main(): ...
```

Toggle with `/verbose`.

## Adding a custom tool

Create a module and decorate a function with `@register`, then ensure it is imported before the agent starts:

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
