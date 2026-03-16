<p align="center">
  <img src="assets/lmcode.svg" alt="lmcode" width="220" />
</p>

<h1 align="center">lmcode</h1>

<p align="center">
  A local coding agent CLI powered by LM Studio.<br/>
  Open source, fully private, no cloud required.
</p>

<p align="center">
  <a href="https://github.com/VforVitorio/lmcode"><img src="https://img.shields.io/badge/status-in%20development-orange" alt="status" /></a>
  <a href="https://www.python.org"><img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="python" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="license" /></a>
  <a href="https://docs.astral.sh/uv"><img src="https://img.shields.io/badge/managed%20with-uv-blueviolet" alt="uv" /></a>
</p>

---

---

**lmcode** is a coding agent for your terminal that runs entirely on your machine using [LM Studio](https://lmstudio.ai) as the inference backend. Think Claude Code or Aider, but local, open source, and extensible via plugins and MCP servers.

> **This project is under active development. The API and features are not stable yet.**

---

## Why

Cloud coding assistants are powerful but they send your code to external servers. Local models have gotten good enough to be genuinely useful for coding tasks, but no good agentic layer exists for LM Studio — it only provides inference. lmcode fills that gap.

```
LM Studio   →   lmcode agent   →   your codebase
(inference)     (tools + loop)      (stays local)
```

---

## Features

- **Agent loop** — iterative tool-calling loop powered by `model.act()` from the LM Studio Python SDK
- **Coding tools** — read files, write files, run shell commands, search code, run tests
- **Session recorder** — every agent action saved as a structured event stream (JSONL)
- **Session viewer** — TUI timeline of what the agent did, with diff viewer and replay
- **MCP support** — connect any [MCP](https://modelcontextprotocol.io) server to give the agent new capabilities
- **OpenAPI → MCP** — point lmcode at any OpenAPI spec and the endpoints become agent tools automatically (powered by [FastMCP](https://github.com/jlowin/fastmcp))
- **Plugin system** — extend lmcode with plugins via entry points (pluggy-based)
- **LMCODE.md** — per-repo memory file, like CLAUDE.md

---

## Status

| Component | Status |
|---|---|
| CLI skeleton (Typer + Rich) | 🔲 planned |
| LM Studio adapter | 🔲 planned |
| Agent loop + basic tools | 🔲 planned |
| Session recorder | 🔲 planned |
| MCP client | 🔲 planned |
| OpenAPI → MCP dynamic servers | 🔲 planned |
| Plugin system (pluggy) | 🔲 planned |
| Session viewer (Textual TUI) | 🔲 planned |
| VSCode extension | 🔲 planned |

---

## Requirements

- Python 3.11+
- [LM Studio](https://lmstudio.ai) running locally with a model loaded
- [uv](https://docs.astral.sh/uv) (recommended) or pip

---

## Install

```bash
# with uv (recommended)
uv tool install lmcode

# or with pipx
pipx install lmcode

# or with pip
pip install lmcode
```

> Not published to PyPI yet. Install from source in the meantime:
> ```bash
> git clone https://github.com/VforVitorio/lmcode
> cd lmcode
> uv sync
> uv run lmcode --help
> ```

---

## Quick start

Make sure LM Studio is running with a model loaded and the local server enabled.

```bash
# start a chat session in the current repo
lmcode chat

# ask the agent to do something
lmcode run "fix the failing tests in src/api/"

# view what the agent did in the last session
lmcode session view

# connect an OpenAPI spec as tools
lmcode mcp add --openapi https://petstore3.swagger.io/api/v3/openapi.json
```

---

## How it works

```
lmcode chat
     │
     ▼
Agent Core
     │
     ├── LM Studio SDK (model.act)
     │
     ├── Tool Runner
     │      ├── read_file / write_file / list_files
     │      ├── run_shell
     │      ├── search_code (ripgrep)
     │      ├── git (status, diff, commit)
     │      └── [MCP tools, plugin tools]
     │
     └── Session Recorder
            │
            ▼
       sessions/session_001.jsonl
```

### MCP + OpenAPI

lmcode can dynamically create MCP servers from OpenAPI specs using [FastMCP](https://github.com/jlowin/fastmcp):

```bash
# any REST API becomes agent tools
lmcode mcp add --openapi ./my-api-spec.yaml --name my-api
```

Under the hood, FastMCP parses the spec and generates MCP-compatible tools for each endpoint. The agent can then call those tools natively in its loop.

### Plugin system

```bash
pip install lmcode-docker-plugin
# plugin is auto-discovered via entry_points — no config needed
```

Third-party plugins can add new tools, hooks, and MCP servers by implementing pluggy hookspecs.

---

## Project structure

```
src/lmcode/
├── cli/          # Typer commands
├── agent/        # agent loop and context management
├── tools/        # built-in coding tools
├── mcp/          # MCP client + OpenAPI → MCP dynamic servers
├── plugins/      # pluggy hookspecs and manager
├── session/      # recorder, storage, event models
├── ui/           # Textual TUI session viewer
└── config/       # settings and LMCODE.md handling
```

---

## Contributing

This project is in early development. Contributions, feedback, and ideas are very welcome.

- Open an issue to discuss ideas before opening a PR
- Keep PRs focused — one thing at a time
- All code is formatted with `ruff` and type-checked with `mypy`

```bash
git clone https://github.com/VforVitorio/lmcode
cd lmcode
uv sync --all-extras
uv run pytest
```

---

## Roadmap

**v0.1 — MVP**
- [ ] `lmcode chat` with basic tools
- [ ] Session recording
- [ ] Auto-connect to LM Studio

**v0.2 — MCP + plugins**
- [ ] MCP client
- [ ] OpenAPI → MCP
- [ ] Plugin system

**v0.3 — Session viewer**
- [ ] Textual TUI
- [ ] Diff viewer
- [ ] Session replay

**v1.0**
- [ ] Stable API
- [ ] VSCode extension
- [ ] Docs site

---

## Inspiration

- [Claude Code](https://claude.ai/claude-code) — the gold standard for coding agents
- [Aider](https://aider.chat) — great open source coding assistant
- [Open Interpreter](https://openinterpreter.com) — local code execution agent
- [LM Studio](https://lmstudio.ai) — local LLM inference

---

## License

MIT — see [LICENSE](LICENSE)
