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
- **Coding tools** — read files, write files, list files, run shell commands, search code (ripgrep), git operations
- **LMCODE.md** — per-repo memory file, like CLAUDE.md; injected into the system prompt automatically
- **Animated spinner** — state labels (`thinking…` / `working…` / `finishing…`) with tool name + path during tool calls
- **Tool output panels** — syntax-highlighted file previews, side-by-side diff blocks for edits, IN/OUT panels for shell commands
- **Ghost-text autocomplete** — fish-shell style: type `/h` → dim `elp` appears, Tab accepts
- **Persistent history** — Ctrl+R and Up-arrow recall prompts across sessions (`~/.lmcode/history`)
- **Permission modes** — `ask` (confirm each tool), `auto` (run freely), `strict` (read-only); Tab cycles between them
- **LMCODE.md** — per-repo context file injected into the system prompt
- **/compact** — summarises conversation history via the model, resets the chat, and injects the summary as context
- **/tokens** — session-wide prompt (↑) and generated (↓) token totals with context arc (`◔ 38%  14.2k / 32k tok`)
- **/history [N]** — show last N conversation turns as bordered panels (default 5)
- **/hide-model** — toggle model name visibility in the live prompt
- **Cycling tips** — tips below the spinner rotate every 8 s through a shuffled list
- **Context arc indicator** — `○◔◑◕●` with percentage in `/status` and `/tokens`; warns at 80 % usage

## Slash commands

| Command | Description |
|---------|-------------|
| `/help` | Show all available slash commands |
| `/status` | Show session stats, model info, and context window usage |
| `/tokens` | Show session prompt (↑) and generated (↓) token totals with context arc |
| `/compact` | Summarise history, reset chat, inject summary as context |
| `/history [N]` | Show last N conversation turns as panels (default 5) |
| `/hide-model` | Toggle model name visibility in the live prompt |
| `/verbose` | Toggle verbose tool-call output |
| `/tips` | Toggle cycling tips below the thinking spinner |
| `/stats` | Toggle per-turn stats line after each response |
| `/tools` | List all registered tools |

---

## Status

| Component | Status |
|---|---|
| CLI skeleton (Typer + Rich) | ✅ done |
| LM Studio adapter (`model.act`) | ✅ done |
| Agent loop + basic tools | ✅ done |
| Slash commands + UX polish | ✅ done |
| Animated spinner + state labels | ✅ done |
| Tool output panels (file, diff, shell) | ✅ done |
| Ghost-text autocomplete + history | ✅ done |
| Ctrl+C interrupt mid-generation | ✅ done |
| Graceful LM Studio disconnect handling | ✅ done |
| Streaming Markdown output | 🔶 in progress |
| Interactive permission UI (ask mode) | 🔲 planned |
| Session recorder (JSONL) | 🔲 planned |
| Session viewer (Textual TUI) | 🔲 planned |
| MCP client | 🔲 planned |
| Plan mode / Agent mode | 🔲 planned |
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
```

The agent will connect to LM Studio automatically. Type your request and press Enter. Use `/help` to see all slash commands.

> **Recommended model:** Qwen2.5-Coder-7B-Instruct (Q4_K_M, ~4.5 GB VRAM) — best function calling for code tasks at 7B size.

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
     └── Tool Runner
            ├── read_file / write_file / list_files
            ├── run_shell
            ├── search_code (ripgrep)
            └── git (status, diff, commit)
```

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

**v0.1.0 — Basic chat** ✅
- [x] `lmcode chat` with LM Studio connection
- [x] Agent loop (`model.act`) + basic tools
- [x] Auto-connect to LM Studio

**v0.2.0 — Full tool suite** ✅
- [x] `write_file`, `list_files`, `run_shell`, `search_code` tools
- [x] Banner + status bar
- [x] Slash commands (`/help`, `/status`, `/verbose`, `/tools`, `/compact`)

**v0.3.0 — UX polish** ✅
- [x] `/compact` — summarise history and reset chat
- [x] `/tokens` — session token totals and context arc
- [x] `/hide-model` — toggle model name in prompt
- [x] Cycling tips — rotate every 8 s during thinking
- [x] Context window indicator — arc `○◔◑◕●` + % in `/status` and `/tokens`

**v0.4.0 — Input & display** ✅
- [x] Animated spinner with state labels (`thinking…` / `working…` / `finishing…`)
- [x] Ghost-text slash autocomplete (fish-shell style, Tab to accept)
- [x] Persistent history — Ctrl+R / Up-arrow across sessions
- [x] `read_file` syntax panel (one-dark, line numbers, violet border)
- [x] `write_file` side-by-side diff block (Codex/Catppuccin palette)
- [x] `run_shell` IN/OUT panel with separator
- [x] `/history [N]` — show last N conversation turns

**v0.5.0 — Agent modes** ✅ done
- [x] Ctrl+C interrupt mid-generation — returns to prompt, shows `^C` / `interrupted` (#60)
- [x] Verbose tool panels always shown — fixed positional-arg merge in `_wrap_tool_verbose`
- [x] `write_file` escape sequences — literal `\n`/`\t` unescaped before writing
- [x] SDK channel noise suppression after Ctrl+C
- [ ] Streaming Markdown output (#56)
- [ ] Interactive permission UI — diff view + arrow-key confirm in ask mode (#40)
- [ ] Plan mode — model proposes a plan before executing (#21)
- [ ] Agent mode — autonomous multi-step execution (#22)

**v0.6.0 — Stability** 🔶 in progress
- [x] Graceful LM Studio disconnect handling (#70)
- [ ] Git tools — `git_status`, `git_diff`, `git_commit`, `git_log`
- [ ] Streaming Markdown output (#56)

**v1.0**
- [ ] Session recorder + Textual TUI viewer
- [ ] MCP client
- [ ] Stable API + docs site
- [ ] VSCode extension

---

## Inspiration

- [Claude Code](https://claude.ai/claude-code) — the gold standard for coding agents
- [Aider](https://aider.chat) — great open source coding assistant
- [Open Interpreter](https://openinterpreter.com) — local code execution agent
- [LM Studio](https://lmstudio.ai) — local LLM inference

---

## License

MIT — see [LICENSE](LICENSE)
