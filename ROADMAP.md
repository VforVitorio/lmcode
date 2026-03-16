# Roadmap

This document tracks the planned direction of lmcode. It is a living document — priorities may shift as the project evolves and community feedback comes in.

> Current status: **pre-MVP, active development**

---

## v0.1 — MVP: it works

The goal of v0.1 is a single working thing: `lmcode chat` in a repo, with a local model doing real coding tasks.

**Agent core**
- [ ] Connect to LM Studio local server via official Python SDK
- [ ] Agent loop using `model.act()` with tool calling
- [ ] Streaming output to terminal in real time
- [ ] Auto-detect running model (no manual config needed)
- [ ] `max_rounds` safety limit

**Built-in tools**
- [ ] `read_file` — read any file in the repo
- [ ] `write_file` — write or overwrite a file
- [ ] `list_files` — list directory contents with glob support
- [ ] `run_shell` — execute shell commands with timeout
- [ ] `search_code` — grep/ripgrep search across the repo

**CLI**
- [ ] `lmcode chat` — interactive chat session
- [ ] `lmcode run "<task>"` — one-shot task execution
- [ ] `lmcode --model <id>` — override which model to use
- [ ] `--verbose` flag for debug output

**Session recording**
- [ ] Every agent action saved as JSONL event stream
- [ ] Sessions stored in `~/.local/share/lmcode/sessions/`
- [ ] `lmcode session list` — list past sessions

**Config**
- [ ] `~/.config/lmcode/config.toml` — global config
- [ ] `LMCODE.md` — per-repo memory file (injected into system prompt)

**Packaging**
- [ ] `pyproject.toml` with uv
- [ ] `pipx install lmcode` works
- [ ] CI: pytest + ruff + mypy on push

---

## v0.2 — MCP + plugins

**MCP client**
- [ ] Connect to any running MCP server
- [ ] MCP tools available in the agent loop automatically
- [ ] `lmcode mcp add <server>` — register an MCP server
- [ ] `lmcode mcp list` — list connected servers

**OpenAPI → MCP (powered by FastMCP)**
- [ ] `lmcode mcp add --openapi <spec-url-or-file>` — load any REST API as tools
- [ ] Dynamic tool generation from OpenAPI spec at startup
- [ ] Named MCP connections persisted in config

**Plugin system**
- [ ] pluggy-based hookspecs
- [ ] Auto-discovery via Python entry points
- [ ] Hooks: `on_tool_call`, `on_tool_result`, `on_session_start`, `on_session_end`
- [ ] Example plugin repo as template

**More tools**
- [ ] `git_status`, `git_diff`, `git_commit`, `git_log`
- [ ] `run_tests` — auto-detect pytest / npm test / cargo test
- [ ] `edit_file` — surgical line-level edits (not full rewrites)

---

## v0.3 — Session viewer

**Textual TUI**
- [ ] `lmcode session view` — open session viewer
- [ ] Event timeline: user → model → tool call → result
- [ ] Diff viewer for file edits
- [ ] Session replay (step through events)
- [ ] Filter by session, date, tool type

**Chat UI improvements**
- [ ] Rich markdown rendering in terminal
- [ ] Syntax-highlighted code blocks
- [ ] Collapsible tool call sections

---

## v0.4 — Code intelligence

- [ ] Repo indexing (file tree + symbol index)
- [ ] Semantic code search via embeddings (LM Studio embedding models)
- [ ] `search_symbols` — find function/class definitions
- [ ] Auto-inject relevant context into system prompt based on task

---

## v1.0 — Stable release

- [ ] Stable public API (tools, plugins, MCP)
- [ ] Full documentation site
- [ ] VSCode extension (basic: run lmcode from editor)
- [ ] Multi-agent support (orchestrator + subagents)
- [ ] Performance: parallel tool execution
- [ ] Windows / macOS / Linux tested and supported

---

## Icebox (not planned yet, but interesting)

- Web UI alternative to TUI
- Remote LM Studio support (non-localhost)
- Agent memory across sessions (long-term project memory)
- Fine-tuned models optimized for lmcode tool format
- Collaborative sessions (multiple users)

---

## How priorities are set

1. Does it make `lmcode chat` more useful day-to-day? → high priority
2. Does it make the project more extensible for others? → medium priority
3. Is it a nice-to-have polish item? → low priority / icebox

If you want to advocate for a feature, open an issue with your use case.
