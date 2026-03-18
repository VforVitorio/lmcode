# CLI Reference

The `lmcode` command is built with [Typer](https://typer.tiangolo.com/) and [Rich](https://rich.readthedocs.io/).

## Invocation

Running `lmcode` with no arguments starts an interactive chat session immediately (equivalent to `lmcode chat`).

```
lmcode [OPTIONS] [COMMAND]

Options:
  --version, -V   Show version and exit.
  --verbose, -v   Enable verbose output.
  --help          Show help.
```

## Commands

### `lmcode chat`

Start an interactive coding agent session in the current directory.

```
lmcode chat [OPTIONS]

Options:
  --model, -m TEXT    LM Studio model ID (default: auto-detect)
  --max-rounds INT    Maximum agent loop iterations (default: 50)
```

On startup, lmcode probes the LM Studio server. If the server is unreachable or no model is loaded, it prints a clear error message and exits with code 1. Otherwise it prints the banner and enters the interactive loop.

The prompt format is:

```
● lmcode (model-name)  [mode]  ›
```

Where `mode` is color-coded: amber for `ask`, blue for `auto`, red for `strict`. The model name can be hidden with `/hide-model`.

#### In-session commands

All slash commands are handled inline without sending a message to the model:

| Command | Description |
|---------|-------------|
| `/help` | Show the command reference |
| `/clear` | Reset conversation history |
| `/mode [ask\|auto\|strict]` | Show or change the permission mode |
| `/model` | Show the current loaded model |
| `/verbose` | Toggle tool call visibility (on by default) |
| `/tips` | Toggle rotating tips shown during thinking |
| `/stats` | Toggle per-response token stats |
| `/tokens` | Show session-wide token usage totals |
| `/hide-model` | Toggle model name in the prompt |
| `/tools` | List available tools with their signatures |
| `/status` | Show current session state (model, mode, context usage, …) |
| `/version` | Show the running lmcode version |
| `/exit` | Exit lmcode |

#### Permission modes

| Mode | Behaviour |
|------|-----------|
| `ask` | Confirms before each tool call (default) |
| `auto` | Tools run automatically |
| `strict` | No tools — pure chat only |

Press **Tab** at the prompt to cycle modes in-place (ask → auto → strict → ask). The prompt redraws immediately without creating a new line.

#### Spinner and tips

While the model is running, a dots-style spinner is shown. If `show_tips` is enabled (default), rotating tips appear below the spinner and change every ~8 seconds. Tips and stats can be toggled with `/tips` and `/stats`.

#### Context window indicator

`/status` and `/tokens` show a compact context usage line:

```
◔ 48%  (15.4k / 32k tok)
```

The arc character cycles through `○ ◔ ◑ ◕ ●` as usage increases. A one-time warning is printed when usage reaches 80%.

#### Token stats

After each response, a right-aligned stats line is printed when `show_stats` is on:

```
↑ 1.2k  ↓ 384  ·  45 tok/s  ·  2.3s
```

### `lmcode run`

Run a single non-interactive task and exit.

```
lmcode run TASK [OPTIONS]
```

> Not yet fully implemented.

### `lmcode session`

Browse and replay past recorded sessions.

```
lmcode session [SUBCOMMAND]
  list     List all sessions
  view     Open a session in the Textual TUI viewer
```

> Session recording is planned for a future release.

### `lmcode mcp`

Manage MCP server connections.

```
lmcode mcp [SUBCOMMAND]
  add      Register a new MCP server (URL or OpenAPI spec path)
  list     List registered servers
  remove   Remove a server
```

> MCP support is planned for a future release.

### `lmcode config`

Read and write lmcode settings.

```
lmcode config [SUBCOMMAND]
```

## Banner

The terminal banner is defined in `src/lmcode/ui/banner.py`. It uses Unicode block art and Rich markup with the project color palette (`#a78bfa` accent purple, `#c4b5fd` lavender). A compact version is shown when the terminal is narrower than 90 columns.

After the banner, a status line confirms the connection and model:

```
●  lmcode (qwen2.5-coder-7b-instruct)  connected
```

Followed by a startup tip rule:

```
─── Tab cycles mode  ·  /help for commands  ·  /verbose to hide tool calls ───
```
