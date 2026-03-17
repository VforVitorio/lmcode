# Tool Registry API

The tool registry (`src/lmcode/tools/registry.py`) is the central map of tool name → callable. It is the integration point between user-defined tools and the LM Studio SDK.

## Registering a tool

```python
from lmcode.tools.registry import register

@register
def my_tool(arg1: str, arg2: int = 0) -> str:
    """Short description shown to the model.

    Longer explanation if needed.
    """
    return f"result: {arg1} + {arg2}"
```

**Requirements:**
- Type hints on all parameters (required for JSON schema generation)
- A docstring (used as the tool description)
- Return type must be `str`

## Registry API

```python
from lmcode.tools.registry import register, get_all, get

# Decorator — adds function to registry under its __name__
@register
def my_tool(...) -> str: ...

# Get all registered tools as a list (pass to model.act)
tools: list[Callable] = get_all()

# Get a specific tool by name
fn: Callable | None = get("my_tool")
```

## Passing tools to the agent loop

```python
import lmstudio as lms
from lmcode.tools.registry import get_all

async with lms.AsyncClient() as client:
    model = await client.llm.model("auto")
    result = await model.act(
        "Fix the bug in main.py",
        tools=get_all(),
    )
```

`model.act()` automatically generates JSON schemas from the function signatures and handles the full tool-call loop until the model stops requesting tools.

## `ToolResult`

```python
from lmcode.tools.base import ToolResult

@dataclass
class ToolResult:
    output: str = ""   # successful output
    error: str = ""    # error message (empty = no error)
    truncated: bool = False  # True if output was clipped
```

Use `ToolResult` internally for structured handling, but always return `result.output` or `result.error` as a plain `str` from the tool function.
