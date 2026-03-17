# Architecture Overview

lmcode is a local coding agent CLI that runs entirely on your machine using [LM Studio](https://lmstudio.ai/) as the inference backend. It is designed around a simple pipeline:

```
CLI (Typer + Rich)
  └── Agent Core
        ├── LM Studio SDK  ←→  model.act() agent loop
        ├── Tool Runner    ←→  registered tools (read/write/shell/search)
        ├── Plugin Manager ←→  lifecycle hooks (pluggy)
        └── Session Recorder  →  JSONL event stream
```

## Layers

### 1. CLI layer (`src/lmcode/cli/`)

Entry point via the `lmcode` command. Built with [Typer](https://typer.tiangolo.com/) + [Rich](https://rich.readthedocs.io/). Subcommands:

| Command | Description |
|---------|-------------|
| `lmcode chat` | Interactive ask/agent mode |
| `lmcode run <task>` | Non-interactive single task |
| `lmcode session` | Browse and replay past sessions |
| `lmcode mcp` | Manage MCP server connections |

### 2. Config layer (`src/lmcode/config/`)

- **`settings.py`** — pydantic-settings backed by `~/.config/lmcode/config.toml`. Groups: `LMStudioSettings`, `AgentSettings`, `SessionSettings`.
- **`paths.py`** — platformdirs for cross-platform config/data dirs.
- **`lmcode_md.py`** — Discovers `LMCODE.md` per-repo memory files by walking up the directory tree.

### 3. Tools layer (`src/lmcode/tools/`)

Tools are plain Python functions registered with the `@register` decorator. They return `ToolResult` dataclasses and are passed to `model.act()` as a list. See [tool system docs](../features/tools.md).

### 4. Agent Core (`src/lmcode/agent/`)

Thin wrapper around LM Studio's `model.act()`. Handles:
- Building the system prompt (base prompt + LMCODE.md context)
- Round limit enforcement
- Streaming output to the terminal

### 5. Plugin system (`src/lmcode/plugins/`)

Based on [pluggy](https://pluggy.readthedocs.io/). Plugins declare implementations of hookspecs and are auto-discovered via `entry_points(group="lmcode.plugins")`. See [plugin API docs](../api/plugins.md).

### 6. Session recording (`src/lmcode/session/`)

Every agent run produces a JSONL file in `~/.local/share/lmcode/sessions/`. Each line is a serialized `SessionEvent` (Pydantic union type). See [session format docs](../features/session.md).

### 7. MCP integration (`src/lmcode/mcp/`)

Dynamic MCP server generation via [FastMCP](https://github.com/jlowin/fastmcp) from OpenAPI specs. Allows connecting lmcode to any REST API as a tool source.

## Data flow (single agent turn)

```
user input
  → Agent.run(prompt)
      → build_system_prompt()       # base + LMCODE.md
      → model.act(prompt, tools=[]) # LM Studio SDK
          → tool_call detected
              → ToolRunner.execute(name, args)
                  → plugin.on_tool_call(name, args)
                  → tool_fn(**args) → ToolResult
                  → plugin.on_tool_result(name, result)
                  → SessionRecorder.append(ToolCallEvent, ToolResultEvent)
          → model response
              → plugin.on_model_response(text)
              → SessionRecorder.append(ModelResponseEvent)
              → stream to terminal
```

## Multi-agent pattern

For complex tasks, an **Orchestrator** agent spawns **Worker** agents via `asyncio.gather`. Workers don't share state — they communicate only through their return values. LM Studio serializes GPU access at the server level, so workers run concurrently at the CPU/IO level but queue at the GPU.

```
Orchestrator
  ├── Worker A  (e.g. write tests)
  ├── Worker B  (e.g. write implementation)
  └── Worker C  (e.g. update docs)
         ↓ results gathered
  Orchestrator synthesizes final output
```
