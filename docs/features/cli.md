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

## Banner

The terminal banner is defined in `src/lmcode/ui/banner.py`. It renders block-letter ASCII art `LM─►CODE` using Unicode box-drawing characters, colored with Rich markup:

- **LM** — accent purple (`#a78bfa`)
- **─►** — lavender (`#c4b5fd`)
- **CODE** — white

The banner includes a status line showing LM Studio connection state, active model, run mode, and version.
