# Changelog

All notable changes to lmcode will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
lmcode uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [0.7.0] - 2026-03-26

### Added
- **`/model` command** — switch models mid-session without restarting: `/model list`, `/model load <id>`, `/model unload` (#19)
- **Auto-start LM Studio at startup** — when the inference server is not running, lmcode automatically tries `lms server start` (if LM Studio GUI is open) and then `lms daemon up` (headless, no GUI), with animated dots throughout so the terminal never appears frozen (#34, #85)
- **Interactive arrow-key model picker** — when no model is loaded, a menu lets you pick from your downloaded models; animated dots while loading (#50)
- **ASCII art logo in startup menus** — the lmcode banner is shown above every startup menu (#86)
- **`daemon_up()` in `lms_bridge`** — wraps `lms daemon up` for headless LM Studio startup

### Fixed
- **Fast startup probe** — `_probe_lmstudio()` now does a 0.5 s socket pre-check before calling the SDK, eliminating the multi-second freeze when the server is simply not running (#85)
- **`lms load` arg format** — `--gpu=auto` changed to `--gpu auto` (two separate args); previous format caused silent load failure
- **Model identifier for `lms load`** — `DownloadedModel` now reads `modelKey` from `lms ls --json` as fallback identifier, matching what `lms load` actually accepts

### Changed
- Startup menus use pure ANSI rendering instead of prompt_toolkit `Application`, eliminating cursor highlight artifacts on the selected item
- `server_start()` and `daemon_up()` are launched in daemon threads during startup so the animation begins immediately

---

## [0.6.1] - 2026-03-23

### Changed
- **`agent/core.py` split into focused submodules** — the 1 259-line monolith is now four focused files: `_noise.py` (SDK noise suppression), `_display.py` (all print/render helpers, `SLASH_COMMANDS`, diff rendering), `_prompt.py` (prompt-toolkit session factory), and a slimmer `core.py` (~820 lines). No behaviour changes.

### Fixed
- **`write_file` mixed newline unescape** — the previous guard `"\n" not in content` silently skipped unescaping when a model emitted a mix of real and literal `\n` sequences (e.g. Qwen 7B), producing syntactically invalid Python files. Guard dropped; unescape always runs when `\n` literal is present.

### Tests
- Added `tests/test_agent/test_display.py` — full coverage of `_ctx_usage_line`, `_build_stats_line`, `_format_tool_signature`, `_render_diff_sidebyside`, `_print_history`, and `SLASH_COMMANDS` structure.
- Added `tests/test_agent/test_noise.py` — coverage of `_FilterSDKNoise` and `_FilteredLastResort` suppression logic.

---

## [0.6.0] - 2026-03-22

### Fixed
- **LM Studio disconnect** — closing LM Studio mid-session now shows a clean `LM Studio disconnected → restart LM Studio and run lmcode again` message instead of a raw traceback. Catches `LMStudioServerError` (the actual exception on disconnect) and `LMStudioWebsocketError` from the SDK (#70).
- **SDK WebSocket JSON noise suppression** — `{"event": "Websocket failed, terminating session."}` lines no longer appear on disconnect. Previous approach (`logging.getLogger().addFilter()`) was ineffective because records from unconfigured loggers reach `logging.lastResort` directly, bypassing root logger filters. Fix wraps `logging.lastResort` itself and keeps `sys.stderr` as belt-and-suspenders.

---

<!-- Add new versions below this line, newest first -->

## [0.5.0] - 2026-03-22

### Added
- **Ctrl+C interrupt mid-generation** — pressing Ctrl+C returns to the input prompt instead of exiting lmcode. Displays `^C` + italic `interrupted` with a Rule separator. Chat history is rolled back cleanly so the next turn has no dangling context.
- **Syntax-highlighted diff blocks for `write_file`** — when a file is overwritten the agent displays a side-by-side diff with `+`/`-` counts, Catppuccin colours, and line numbers. New files get a "new file" panel instead.
- **Playground folder** — `playground/` sandbox directory for manual end-to-end feature testing.
- **`/history [n]` slash command** — show last _n_ turns as Rich panels.
- **Ctrl+R history search** — prompt-toolkit reverse history search.
- **Tab mode cycling** — pressing Tab cycles through `ask → auto → strict → ask` permission modes.
- **Ghost-text autocomplete** — slash commands show inline ghost-text suggestions accepted with Tab.

### Changed
- **`run_shell` tool panel** — output is now wrapped in an IN/OUT panel with a separator Rule and uppercase labels.
- **File preview panel** — `read_file` results render in a one-dark themed panel with violet rounded border and line numbers.
- **System prompt rewrite** — tool-first framing with hard constraints, environment block, and anti-hallucination rules tuned for 7B models.
- **Tool docstrings** — rewritten with explicit use-case guidance to improve tool-calling reliability on small models.

### Fixed
- **Verbose panels always shown** — the LM Studio SDK calls tools with positional args; `kwargs` was empty causing panels to be skipped. Fixed with `inspect.signature` positional-arg merge in `_wrap_tool_verbose`.
- **`write_file` escape sequences** — models that emit literal `\n` / `\t` / `\"` (no real newlines in the string) now have those sequences unescaped before writing to disk.
- **SDK "already closed channel" noise** — the warning emitted by the LM Studio WebSocket layer after Ctrl+C is now suppressed via a root-logger `logging.Filter` and a `sys.stderr` wrapper.
- **Completion menu colours** — subtle dark indigo background, violet highlight, no harsh colour blocks.
- **CI lint and typecheck** — fixed ruff E402 and import-sort failures introduced during UX work.

---

## [0.1.0] - 2025-01-01

### Added
- Initial project structure with `agent/`, `cli/`, `tools/`, `config/`, `ui/`, `session/`, `mcp/`, `plugins/` packages.
- `lmcode chat` — interactive REPL powered by LM Studio `model.act()` tool loop.
- Core tools: `read_file`, `write_file`, `list_files`, `run_shell`, `search_code`.
- Tool registry (`@register` decorator).
- Pydantic-settings config (`~/.config/lmcode/config.toml` + `LMCODE_*` env vars).
- `LMCODE.md` context injection (walks directory tree upward).
- Animated dots spinner with state labels (`thinking` / `working` / `finishing`).
- Slash commands: `/help`, `/tokens`, `/status`, `/compact`, `/verbose`, `/clear`, `/history`.
- Slash command ghost-text autocomplete and borderless dropdown.
- Permission modes: `ask`, `auto`, `strict`.
- ASCII art startup banner.
- `lmcode config list/get/set` CLI.
- README, ROADMAP, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, DESIGN, SKELETON docs.
- CI workflow: test (pytest + coverage), lint (ruff), typecheck (mypy).
