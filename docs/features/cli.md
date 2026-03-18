# CLI Reference

The `lmcode` command is built with [Typer](https://typer.tiangolo.com/) and [Rich](https://rich.readthedocs.io/).

## Global flags

```
lmcode [OPTIONS] COMMAND [ARGS]...

Options:
  --version    Show version and exit.
  --verbose    Enable verbose/debug output.
  --help       Show help.
```

## Commands

### `lmcode chat`

Start an interactive session with the coding agent.

```
lmcode chat [OPTIONS]

Options:
  --model TEXT        LM Studio model identifier (default: auto)
  --max-rounds INT    Maximum agent loop iterations (default: 50)
```

On startup, prints the ASCII art banner with the current model name, mode, and LM Studio connection status. The banner uses the project color palette (`#a78bfa` accent, `#121127` background).

### `lmcode run`

Run a single non-interactive task and exit.

```
lmcode run TASK [OPTIONS]
```

> Not yet implemented — coming in `feat/agent-core`.

### `lmcode session`

Browse and replay past recorded sessions.

```
lmcode session [SUBCOMMAND]
  list     List all sessions
  view     Open a session in the Textual TUI viewer
  export   Export a session to markdown
```

> Not yet implemented — coming in `feat/session-viewer`.

### `lmcode mcp`

Manage MCP server connections.

```
lmcode mcp [SUBCOMMAND]
  add      Register a new MCP server (URL or OpenAPI spec path)
  list     List registered servers
  remove   Remove a server
```

> Not yet implemented — coming in `feat/mcp-support`.

## Slash commands

Slash commands are entered at the `lmcode chat` prompt and are processed client-side before the message is sent to the model.

| Command | Description |
|---------|-------------|
| `/help` | List all available slash commands |
| `/status` | Show session stats, model info, and context window usage arc |
| `/tokens` | Show session-wide prompt (↑) and generated (↓) token totals with context arc |
| `/compact` | Summarise conversation history via the model, reset the chat, and inject the summary as context |
| `/hide-model` | Toggle the model name in the live prompt (`● lmcode (model) [ask] ›` vs `● lmcode [ask] ›`) |
| `/verbose` | Toggle verbose tool-call output (tool name + preview after each call) |
| `/tips` | Toggle cycling tips below the thinking spinner |
| `/stats` | Toggle the per-turn stats line shown after each response |
| `/tools` | List all tools currently registered with the agent |

### /compact

`/compact` is used to reclaim context window space without starting a completely new session. When invoked:

1. A `bouncingBar` spinner is shown while the model generates a summary of the conversation so far.
2. The chat history is cleared.
3. The summary is injected as a system-level context message at the start of the new history.
4. A panel is displayed with a preview of the summary and the number of messages that were compacted.

### /tokens

`/tokens` prints the running session totals for:

- **Prompt tokens (↑)** — total tokens sent to the model across all turns.
- **Generated tokens (↓)** — total tokens produced by the model across all turns.
- **Context arc** — a visual indicator of context window fill, e.g. `◔ 38%  (14.2k / 32k tok)`.

The same context arc is also shown in `/status`.

### /hide-model

`/hide-model` toggles whether the loaded model identifier is shown in the interactive prompt.

- **Full prompt:** `● lmcode (qwen2.5-1.5b-instruct) [ask] ›`
- **Compact prompt:** `● lmcode [ask] ›`

This is useful when using a model with a long name that crowds the prompt line.

## Cycling tips

While the agent is thinking, a tip is shown below the spinner to help users discover features. Tips are drawn from a shuffled list and rotate automatically every 8 seconds. The list is reshuffled each time it is exhausted. Tips can be turned off with `/tips`.

## Context window indicator

The context window fill is represented with a five-step arc character sequence:

```
○  <20%
◔  20–39%
◑  40–59%
◕  60–79%
●  80–99%
```

The arc character, percentage, and absolute token counts are shown in `/status` and `/tokens`. When fill crosses 80 %, a one-time warning is printed suggesting the user run `/compact` to free context space.

## Banner

The terminal banner is defined in `src/lmcode/ui/banner.py`. It renders block-letter ASCII art `LM─►CODE` using Unicode box-drawing characters, colored with Rich markup:

- **LM** — accent purple (`#a78bfa`)
- **─►** — lavender (`#c4b5fd`)
- **CODE** — white

The banner includes a status line showing LM Studio connection state, active model, run mode, and version.
