# Roadmap

This document tracks the planned direction of lmcode. It is a living document — priorities may shift as the project evolves and community feedback comes in.

> Current status: **v0.7.0, active development** — core agent loop is production-quality; focus is now on UX polish, permission enforcement, and MCP/plugin ecosystem.

---

## v0.1 — MVP: it works ✅ (shipped)

**Agent core**
- [x] Connect to LM Studio local server via official Python SDK
- [x] Agent loop using `model.act()` with tool calling
- [x] Auto-detect running model (no manual config needed)
- [x] Streaming output (tokens printed progressively) — #56
- [ ] `max_rounds` safety limit

**Built-in tools**
- [x] `read_file` — read any file in the repo
- [x] `write_file` — write or overwrite a file (with diff UI)
- [x] `list_files` — list directory contents with glob support
- [x] `run_shell` — execute shell commands with timeout
- [x] `search_code` — grep/ripgrep search across the repo

**CLI**
- [x] `lmcode chat` — interactive chat session
- [x] `lmcode config list/get/set`
- [ ] `lmcode run "<task>"` — one-shot task execution
- [x] `/model load <id>` — switch model mid-session (#19)

**Config**
- [x] `~/.config/lmcode/config.toml` — global config
- [x] `LMCODE.md` — per-repo context injected into system prompt

**Packaging**
- [x] `pyproject.toml` with uv
- [x] CI: pytest + ruff + mypy on push

---

## v0.6.x — Stability & polish ✅ (shipped)

- [x] Ctrl+C interrupt mid-generation (#69)
- [x] Syntax-highlighted diff blocks for `write_file` (#68)
- [x] LM Studio disconnect handled gracefully (#70)
- [x] SDK WebSocket JSON noise suppressed
- [x] `agent/core.py` split into focused submodules (maintainability)
- [x] `write_file` mixed newline unescape fix (Qwen 7B compatibility)
- [x] Full test coverage for display and noise modules

---

## v0.7.x — UX polish (current)

- [x] **Model switching mid-session** — `/model list · load · unload` (#19)
- [x] **Auto-start LM Studio** — `lms server start` → `lms daemon up` with animated dots (#34, #85)
- [x] **Interactive model picker** — arrow-key menu on startup when no model loaded (#50)
- [x] **ASCII art in startup menus** — banner shown above every startup menu (#86)
- [x] **Streaming Markdown** — response tokens stream progressively; final output rendered as Markdown (#56)
- [x] **Inference parameter control** — `/temp` and `/params set` slash commands (#18)
- [x] **Friendly startup messages** — welcoming tone in startup menus (#87)
- [ ] **Interactive permission UI** — diff view + arrow-key confirmation for `ask` mode (#40)

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
