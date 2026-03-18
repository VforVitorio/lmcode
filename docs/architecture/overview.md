# Architecture Overview

lmcode is a local coding agent CLI that runs entirely on your machine using [LM Studio](https://lmstudio.ai/) as the inference backend. It is designed around a simple pipeline:

```
CLI (Typer + Rich)
  └── Agent Core  (src/lmcode/agent/core.py)
        ├── LM Studio SDK  ←→  model.act() agent loop
        ├── Tool Runner    ←→  registered tools (read/write/shell/search)
        └── UI             ←→  spinner, prompt, stats, separator
```

## Layers

### 1. CLI layer (`src/lmcode/cli/`)

Entry point via the `lmcode` command. Built with [Typer](https://typer.tiangolo.com/) + [Rich](https://rich.readthedocs.io/).

`app.py` registers subcommands. Running `lmcode` with no subcommand invokes `chat` directly.

| Command | Description |
|---------|-------------|
| `lmcode` / `lmcode chat` | Interactive coding agent session |
| `lmcode run <task>` | Non-interactive single task (planned) |
| `lmcode session` | Browse and replay past sessions (planned) |
| `lmcode mcp` | Manage MCP server connections (planned) |
| `lmcode config` | Read and write settings |

`chat.py` performs a startup probe against LM Studio before entering the agent loop:
1. Check server reachability — exit with code 1 if unreachable.
2. Check that at least one model is loaded — exit with code 1 if none.
3. Print the banner and delegate to `agent.core.run_chat()`.

### 2. Config layer (`src/lmcode/config/`)

- **`settings.py`** — pydantic-settings backed by `lmcode.toml`. Groups: `LMStudioSettings`, `AgentSettings`, `UISettings`, `SessionSettings`. Supports env vars with `LMCODE_` prefix.
- **`paths.py`** — platformdirs for cross-platform config/data dirs.
- **`lmcode_md.py`** — discovers `LMCODE.md` per-repo memory files by walking up the directory tree.

### 3. Tools layer (`src/lmcode/tools/`)

Tools are plain Python functions registered with `@register`. They must:
- Have full type hints (drives JSON schema generation for the SDK)
- Return `str`
- Handle exceptions internally and return error strings

Registered tools are collected with `get_all()` and passed to `model.act()`. In verbose mode, each tool call and result is wrapped to print inline summaries before delegating to the real function.

Active built-in tools:

| Tool | Module |
|------|--------|
| `read_file` | `filesystem.py` |
| `write_file` | `filesystem.py` |
| `list_files` | `filesystem.py` |
| `run_shell` | `shell.py` |
| `search_code` | `search.py` |

### 4. Agent Core (`src/lmcode/agent/core.py`)

The `Agent` class wraps LM Studio's `model.act()` in a multi-turn interactive session. Responsibilities:

- **Prompt building** — base system prompt + LMCODE.md context
- **Permission modes** — `ask` (confirm), `auto` (silent), `strict` (no tools)
- **Tab mode cycling** — `prompt_toolkit` key binding, redraws in-place via `invalidate()`
- **Spinner + tips** — `rich.live.Live` with an asyncio keepalive task that rotates tips every 8 s
- **Token tracking** — accumulates `prompt_tokens_count` + `predicted_tokens_count` per turn; derives context usage percentage
- **Context window warning** — one-time warning printed at 80% usage
- **Slash command handling** — all `/cmd` inputs are handled in `_handle_slash()` before reaching the model
- **History rewriting** — after submission, the prompt line is overwritten with a dim history entry using ANSI cursor control

#### Async model execution

`model.act()` is awaited directly on the main event loop. An asyncio keepalive task polls every 100 ms to update the spinner label and rotate tips. Rich's own `auto_refresh` thread keeps the spinner animated during synchronous tool execution that briefly blocks the loop.

### 5. UI layer (`src/lmcode/ui/`)

- **`banner.py`** — startup banner with responsive layout (compact below 90 cols)
- **`status.py`** — `build_prompt()` and `build_status_line()` using prompt_toolkit HTML
- **`colors.py`** — named color constants (`ACCENT`, `ERROR`, `SUCCESS`, etc.)

## Data flow (single agent turn)

```
user input
  → _rewrite_as_history()         # dim the submitted prompt line in-place
  → Agent._run_turn(model, input)
      → chat.add_user_message()
      → model.act(chat, tools=[]) # LM Studio SDK handles tool-call loop
          → tool_call detected
              → tool_fn(**args)   # e.g. read_file, run_shell
              → result appended to chat
          → model final response
              → captured and returned
      → accumulate token stats
      → return (response_text, stats_line)
  → console.print(response)
  → print stats (right-aligned, if show_stats)
  → check 80% context warning
  → print Rule separator
```

## Future layers (planned)

| Layer | Module | Status |
|-------|--------|--------|
| Plugin system | `src/lmcode/plugins/` | planned |
| Session recording | `src/lmcode/session/` | planned |
| MCP integration | `src/lmcode/mcp/` | planned |
