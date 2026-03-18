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

> [!WARNING]
> **Honest disclaimer:** This is a personal side project. I'm not a LinkedIn AI guru with 47 certifications. I'm building this with [Claude Code](https://claude.ai/claude-code), so yes — there's probably some AI slop hiding somewhere in here. 🤖🫠
>
> PRs welcome. Learning out loud and figuring things out as I go also welcome. Stack Overflow-style "this question doesn't belong here, marked as duplicate of a 2009 thread" energy — not so much.

---

**lmcode** is a coding agent for your terminal that runs entirely on your machine using [LM Studio](https://lmstudio.ai) as the inference backend. Think Claude Code or Aider, but local, open source, and extensible.

> **This project is under active development. The API and features are not stable yet.**

---

## Why

Cloud coding assistants are powerful but they send your code to external servers. Local models have gotten good enough to be genuinely useful for coding tasks, but no good agentic layer exists for LM Studio — it only provides inference. lmcode fills that gap.

```
LM Studio   →   lmcode agent   →   your codebase
(inference)     (tools + loop)      (stays local)
```

---

## Features (v0.2.0)

- **Agent loop** — iterative tool-calling loop powered by `model.act()` from the LM Studio Python SDK
- **Auto-detect model** — connects to whatever model is loaded in LM Studio; no config needed
- **Coding tools** — `read_file`, `write_file`, `list_files`, `run_shell`, `search_code`
- **Three permission modes** — `ask` (confirm each tool call), `auto` (run tools freely), `strict` (no tools, pure chat)
- **Tab key mode cycling** — press Tab to cycle ask → auto → strict without breaking the prompt line
- **Slash commands** — `/help`, `/clear`, `/mode`, `/model`, `/verbose`, `/tips`, `/stats`, `/tokens`, `/hide-model`, `/tools`, `/status`, `/version`, `/exit`
- **Context window tracking** — token usage indicator (`◔ 48%` style) in `/status` and `/tokens`; warns at 80%
- **Per-response token stats** — right-aligned `↑ 1.2k  ↓ 384  ·  45 tok/s  ·  2.3s`, toggleable via `/stats`
- **Token-aware file read limit** — `read_file` byte cap derived from the model's actual context window
- **Spinner with rotating tips** — dots-style spinner; tips rotate every 8 s during inference
- **Separator Rule** — plain dim rule between exchanges keeps the scrollback clean
- **Submitted messages rewritten** — input line replaced in-place with a dim history entry after submission
- **Responsive banner** — compact layout under 90 columns
- **Early exit on startup failures** — clear error messages if LM Studio is unreachable or no model is loaded
- **UISettings** — configure `spinner`, `show_tips`, `show_stats` in `lmcode.toml`
- **LMCODE.md** — per-repo memory file, like CLAUDE.md — injected into the system prompt automatically

---

## Status

| Component | Status |
|---|---|
| CLI (`lmcode` command) | ✅ done |
| LM Studio adapter | ✅ done |
| Agent loop + tools | ✅ done |
| Permission modes (ask/auto/strict) | ✅ done |
| Context window tracking | ✅ done |
| Token stats | ✅ done |
| LMCODE.md support | ✅ done |
| UISettings (toml) | ✅ done |
| Session recorder | 🔲 planned |
| MCP client | 🔲 planned |
| OpenAPI → MCP dynamic servers | 🔲 planned |
| Plugin system (pluggy) | 🔲 planned |
| Session viewer (Textual TUI) | 🔲 planned |
| VSCode extension | 🔲 planned |

---

## Requirements

- Python 3.11+
- [LM Studio](https://lmstudio.ai) running locally with a model loaded and the local server enabled
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

Make sure LM Studio is running with a model loaded and the local server enabled (Developer → Start Server).

```bash
# start a session — model is auto-detected from LM Studio
lmcode

# or explicitly via the chat subcommand
lmcode chat

# specify a model by ID
lmcode chat --model "qwen2.5-coder-7b-instruct"
```

---

## How it works

```
lmcode
     │
     ▼
Agent Core  (src/lmcode/agent/core.py)
     │
     ├── LM Studio SDK (model.act)
     │
     ├── Tool Runner
     │      ├── read_file / write_file / list_files  (filesystem.py)
     │      ├── run_shell                             (shell.py)
     │      └── search_code                          (search.py)
     │
     └── UI
            ├── Spinner + rotating tips
            ├── Separator Rule between exchanges
            └── Token stats + context usage
```

### Permission modes

| Mode | Behaviour |
|------|-----------|
| `ask` | Confirms before each tool call (default) |
| `auto` | Tools run automatically |
| `strict` | No tools — pure chat only |

Press **Tab** at the prompt to cycle modes in-place, or use `/mode [ask|auto|strict]`.

### Slash commands

| Command | Description |
|---------|-------------|
| `/help` | Show the command reference |
| `/clear` | Reset conversation history |
| `/mode [ask\|auto\|strict]` | Show or change the permission mode |
| `/model` | Show the current loaded model |
| `/verbose` | Toggle tool call visibility |
| `/tips` | Toggle rotating tips during thinking |
| `/stats` | Toggle per-response token stats |
| `/tokens` | Show session-wide token usage totals |
| `/hide-model` | Toggle model name in the prompt |
| `/tools` | List available tools with their signatures |
| `/status` | Show current session state |
| `/version` | Show the running lmcode version |
| `/exit` | Exit lmcode |

### LMCODE.md

Place a `LMCODE.md` file in your project root (or any parent directory) to inject project-specific context into the agent's system prompt:

```markdown
# LMCODE.md

This project uses Python 3.12+ and uv.
Never use `pip install` directly — always use `uv add`.
Run tests with `uv run pytest`.
```

---

## Configuration

lmcode reads `lmcode.toml` from the platform config directory:

- Linux: `~/.config/lmcode/lmcode.toml`
- macOS: `~/Library/Application Support/lmcode/lmcode.toml`
- Windows: `%APPDATA%\lmcode\lmcode.toml`

```toml
[lmstudio]
host = "localhost"
port = 1234
model = "auto"

[agent]
max_rounds = 50
permission_mode = "ask"
timeout_seconds = 30

[ui]
spinner = "dots"
show_tips = true
show_stats = true
```

---

## Project structure

```
src/lmcode/
├── cli/          # Typer commands (app.py, chat.py, ...)
├── agent/        # agent loop and core logic
├── tools/        # built-in coding tools
├── config/       # settings, paths, LMCODE.md handling
└── ui/           # colors, banner, status rendering
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

**v0.2 — current**
- [x] `lmcode` command with auto-detected model
- [x] Tools: read_file, write_file, list_files, run_shell, search_code
- [x] Permission modes: ask / auto / strict
- [x] Slash commands, Tab mode cycling
- [x] Context window usage tracking
- [x] Token stats, UISettings

**v0.3 — Session recorder**
- [ ] JSONL event stream per session
- [ ] `lmcode session list / view`

**v0.4 — MCP + plugins**
- [ ] MCP client
- [ ] OpenAPI → MCP dynamic servers
- [ ] Plugin system (pluggy)

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
