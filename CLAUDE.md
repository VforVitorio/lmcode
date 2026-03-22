# CLAUDE.md — lmcode

This file gives Claude Code full context about the lmcode project: architecture, development workflow, code standards, and custom agent skills (slash commands).

---

## 1. Project Overview

**lmcode** is a local coding agent CLI that runs entirely on the user's machine using [LM Studio](https://lmstudio.ai) as the inference backend. It is the open-source, local-first alternative to Claude Code or Aider — no cloud, no API keys, no telemetry. The user starts `lmcode chat` in a repo, types a request, and the agent calls tools (read/write files, run shell commands, search code, git operations) in an iterative loop until the task is done.

The agent loop is built on top of the official LM Studio Python SDK's `model.act()` method, which handles the full tool-calling cycle internally. lmcode adds the UI layer (animated spinner, syntax-highlighted tool output, diff blocks, slash commands), the tool registry, permission modes, session recording infrastructure, and the plugin system on top of that primitive. The key design constraint is that the LM Studio SDK's `AsyncTaskManager` is bound to the main event loop — everything async must stay on it.

The project is in active development (current version: 0.1.0, targeting v0.5.0 features). The main branch is protected; all work goes through `feat/*` → `dev` → `main` via PRs. The recommended model for testing is **Qwen2.5-Coder-7B-Instruct Q4_K_M**.

---

## 2. Architecture

### Module Map

```
src/lmcode/
├── __init__.py          # __version__ = "0.1.0"
├── __main__.py          # python -m lmcode entry point
│
├── agent/
│   ├── core.py          # THE main file — Agent class, _run_turn, slash commands,
│   │                    # spinner, diff rendering, tool wrapping, run_chat()
│   ├── context.py       # (stub) future context management
│   └── memory.py        # (stub) future cross-session memory
│
├── cli/
│   ├── app.py           # Root Typer app; registers all sub-commands
│   ├── chat.py          # `lmcode chat` — probes LM Studio, calls run_chat()
│   ├── run.py           # `lmcode run "<task>"` — one-shot (not yet implemented)
│   ├── config_cmd.py    # `lmcode config list/get/set` — TOML settings CLI
│   ├── session.py       # `lmcode session list/view` — stub, not yet implemented
│   └── mcp.py           # `lmcode mcp add/list/remove` — stub, not yet implemented
│
├── tools/
│   ├── registry.py      # @register decorator + get_all() / get(name)
│   ├── base.py          # ToolResult dataclass and Tool type alias
│   ├── filesystem.py    # read_file, write_file, list_files — all @register'd
│   ├── shell.py         # run_shell — @register'd
│   ├── search.py        # search_code (ripgrep + Python fallback) — @register'd
│   └── git.py           # (stub) future git tools
│
├── config/
│   ├── settings.py      # Pydantic-settings: LMStudioSettings, AgentSettings,
│   │                    # SessionSettings, UISettings; config.toml + LMCODE_ env vars
│   ├── paths.py         # platformdirs: config_dir(), data_dir(), sessions_dir()
│   └── lmcode_md.py     # find_lmcode_md() + read_lmcode_md() — walks up tree
│
├── ui/
│   ├── colors.py        # All color constants (ACCENT, SUCCESS, ERROR, etc.)
│   ├── banner.py        # ASCII art startup banner (full + compact)
│   ├── status.py        # build_prompt(), build_status_line(), next_mode()
│   ├── chat_ui.py       # (stub) future Textual TUI chat UI
│   ├── viewer.py        # (stub) future Textual session viewer
│   └── components/
│       ├── diff_view.py      # (stub)
│       ├── tool_call_view.py # (stub)
│       └── timeline.py       # (stub)
│
├── session/
│   ├── models.py        # Pydantic event models: SessionStartEvent, ToolCallEvent, etc.
│   ├── recorder.py      # (stub) future JSONL session recorder
│   ├── storage.py       # (stub) future session storage/retrieval
│   └── reader.py        # (stub) future session reader
│
├── mcp/
│   ├── bridge.py        # (stub) future MCP bridge
│   ├── client.py        # (stub) future MCP client
│   ├── openapi.py       # (stub) future OpenAPI → MCP adapter
│   └── registry.py      # (stub) future MCP tool registry
│
└── plugins/
    ├── hookspecs.py     # pluggy hookspecs: on_session_start/end, on_tool_call/result
    ├── manager.py       # get_plugin_manager() — discovers plugins via entry_points
    └── builtin/
        └── core_plugin.py  # (stub) built-in plugin
```

### Key Files and Their Roles

| File | Role |
|------|------|
| `agent/core.py` | The heart of lmcode. Contains: `Agent` class, `_BASE_SYSTEM_PROMPT`, `_SLASH_COMMANDS` list, spinner logic, diff rendering, tool output panels, `run_chat()` entry point. ~1200 lines. |
| `tools/registry.py` | 24-line module. `@register` decorator stores tools in `_registry` dict. `get_all()` returns list for `model.act(tools=...)`. |
| `tools/filesystem.py` | `read_file`, `write_file`, `list_files`. Must be imported in `core.py` (even if unused) to trigger the `@register` decorators. |
| `config/settings.py` | Pydantic-settings singleton. `get_settings()` returns cached `Settings`. Reads `~/.config/lmcode/config.toml` and `LMCODE_*` env vars. |
| `config/lmcode_md.py` | Walks directory tree upward looking for `LMCODE.md` files. Combines them root-to-leaf and injects into system prompt. |
| `ui/colors.py` | Single source of truth for all colors. Import constants from here; never hardcode hex strings elsewhere. |
| `ui/status.py` | `build_prompt()` returns prompt-toolkit HTML for the live input prompt. `build_status_line()` for the post-connect status. |

### Data Flow

```
User types a message
        │
        ▼
cli/chat.py: chat()
  → probes LM Studio (_probe_lmstudio)
  → prints banner
  → calls run_chat(model_id)
        │
        ▼
agent/core.py: run_chat()
  → asyncio.run(Agent(model_id).run())
        │
        ▼
Agent.run()
  → connects to LM Studio via lms.AsyncClient()
  → resolves model via _get_model()
  → computes token-aware file byte limit via _compute_max_file_bytes()
  → enters prompt loop (prompt_toolkit PromptSession)
        │
        ▼ (user enters a message)
Agent._run_turn(model, user_input)
  → chat.add_user_message(user_input)
  → wraps tools with _wrap_tool_verbose() if verbose mode
  → starts asyncio keepalive task for spinner animation
  → awaits model.act(chat, tools=tools, on_message=_on_message, ...)
        │
        ▼ (LM Studio SDK handles the tool loop internally)
model.act() loop:
  prompt → LLM → tool_call? → execute tool → append result → repeat → done
        │
        ▼
  _on_message callback fires for each message:
    - tool_calls present → update spinner label to "working" or "tool /path"
    - role == "tool" → update spinner to "finishing"
    - assistant content → captured[] list for display
        │
        ▼
  _wrap_tool_verbose wrapper (when verbose=True):
    → _print_tool_call() — one-line tool invocation display
    → calls actual tool function (filesystem/shell/search)
    → _print_tool_result() — syntax panel / diff block / IN/OUT panel
        │
        ▼
Agent.run() receives response_text
  → prints "lmcode  › {response}" in ACCENT_BRIGHT
  → prints stats line (↑ prompt ↓ generated, tok/s, elapsed)
  → checks context window usage (warns at 80%)
  → prints Rule separator
  → loops back to prompt
```

---

## 3. Development Commands

```bash
# Install dependencies (first time or after pyproject.toml changes)
uv sync --all-extras

# Run lmcode locally
uv run lmcode chat
uv run lmcode --help

# Run tests
uv run pytest
uv run pytest tests/test_tools/          # specific module
uv run pytest --cov=src/lmcode           # with coverage

# Lint
uv run ruff check .

# Format
uv run ruff format .

# Type check
uv run mypy src/

# Full CI check (run this before every commit)
uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run pytest

# Fix all auto-fixable lint issues
uv run ruff check . --fix

# Config commands
uv run lmcode config list
uv run lmcode config get agent.max_file_bytes
uv run lmcode config set agent.permission_mode auto
```

---

## 4. Git Workflow

- **Branch naming**: `feat/<description>`, `fix/<description>`, `docs/<description>`
- **PR flow**: `feat/*` or `fix/*` → `dev` → `main`
- **`main` is protected** — never push directly to main; always PR
- **`dev` is the integration branch** — PRs from feature branches target `dev`
- After a PR is merged, delete the source branch
- The user runs all git commands themselves; Claude provides the exact commands as text, never executes them

### Typical feature workflow (provide these commands as text to the user):

```bash
# 1. Create branch from dev
git checkout dev && git pull origin dev
git checkout -b feat/your-feature-name

# 2. Implement, then run CI checks
uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run pytest

# 3. Commit (conventional commits style)
git add <specific files>
git commit -m "feat: description of what was added"

# 4. Push and open PR
git push -u origin feat/your-feature-name
gh pr create --base dev --title "feat: ..." --body "..."
```

### Commit message style (Conventional Commits):
```
feat: add search_code tool using ripgrep
fix: handle empty file in read_file tool
docs: add plugin development guide
refactor: extract tool registry into its own module
test: add integration tests for shell tool
```

---

## 5. Code Standards

### Core principles
- **Single responsibility** — each file, class, and function does one thing
- **Small helpers** — extract named helper functions instead of inline logic blocks
- **Docstrings on every file and public function** — the module docstring goes at the top of every `.py` file; every public function gets a one-line or multi-line docstring
- **Full type hints** — `from __future__ import annotations` at the top of every file; no untyped `Any` unless truly unavoidable (comment why if used)
- **No unnecessary abstractions** — don't create a class where a function will do; don't create a module where a function in an existing module will do

### Patterns
- Tools return `str` (never raise exceptions — return `"error: ..."` strings)
- Tools are plain functions; the LM Studio SDK converts type hints + docstring → JSON schema
- `@register` from `tools/registry.py` is the only registration mechanism
- Settings are always accessed via `get_settings()` (lazy singleton)
- Colors are always imported from `lmcode.ui.colors` — never hardcode hex strings
- `from __future__ import annotations` is the first non-comment line in every source file

### Style (enforced by ruff + mypy)
- Line length: 100 characters
- Python target: 3.12
- Ruff rules: E, W, F, I, B, C4, UP
- mypy: strict mode
- `tomllib` (stdlib) for TOML reading; `tomli_w` for writing

---

## 6. Agent Skills

These are custom slash commands for use inside Claude Code. Each is a self-contained workflow.

---

### /feature [description]

Implement a new lmcode feature end-to-end.

**Steps:**

1. **Understand the request.** Ask clarifying questions if the scope is unclear. Check the ROADMAP.md and open issues to see if this is already planned.

2. **Read relevant existing code.** Before writing anything, read the files you'll need to modify. At minimum:
   - `src/lmcode/agent/core.py` if adding a slash command or changing agent behavior
   - `src/lmcode/tools/registry.py` + the relevant tool file if adding a tool
   - `src/lmcode/config/settings.py` if adding a config option

3. **Plan the implementation.** State which files you will touch and what each change is, before writing any code.

4. **Implement the feature.** Follow all code standards:
   - `from __future__ import annotations` at top of every file
   - Docstring on the file module and every public function
   - Full type hints everywhere
   - Tools return `str` and never raise
   - Import colors from `lmcode.ui.colors`
   - Register new tools with `@register`

5. **Write tests.** Every new tool needs tests in `tests/test_tools/test_<toolname>.py`. Agent behavior changes go in `tests/test_agent/test_core.py`. Use `tmp_path` for filesystem tests. Mock LM Studio for unit tests (see `tests/conftest.py`).

6. **Run CI checks and report results:**
   ```bash
   uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run pytest
   ```
   Fix any failures before proceeding.

7. **Provide the git commands as text** (do not run them):
   ```bash
   git checkout dev && git pull origin dev
   git checkout -b feat/<feature-name>
   git add <specific files, not -A>
   git commit -m "feat: <description>"
   git push -u origin feat/<feature-name>
   gh pr create --base dev --title "feat: <description>" --body "..."
   ```

8. **Tell the user:** "Push the branch and open the PR when you're ready. The CI will run automatically."

---

### /fix [description]

Fix a bug in lmcode.

**Steps:**

1. **Investigate the bug.** Search the codebase for the relevant code:
   - Use `search_code` to find the function or module involved
   - Read the relevant file(s) to understand the current behavior
   - Reproduce the issue mentally: trace the execution path

2. **Identify the root cause.** State clearly what is wrong and why before making any changes.

3. **Fix the bug.** Make the minimal change that fixes the issue. Do not refactor unrelated code in the same commit.

4. **Add a regression test** that would have caught this bug. Place it in the appropriate test file.

5. **Run CI checks:**
   ```bash
   uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run pytest
   ```

6. **Provide the git commands as text:**
   ```bash
   git checkout dev && git pull origin dev
   git checkout -b fix/<bug-name>
   git add <specific files>
   git commit -m "fix: <description of what was wrong and how it was fixed>"
   git push -u origin fix/<bug-name>
   gh pr create --base dev --title "fix: <description>" --body "Fixes #<issue-number> if applicable"
   ```

---

### /close-issue [number]

Close a GitHub issue with proper resolution documentation.

**Steps:**

1. **Read the issue:**
   ```bash
   gh issue view <number>
   ```

2. **Understand what's needed.** Is it a bug, feature request, or question?

3. **If it requires code changes:** Use `/feature` or `/fix` skill to implement the fix, referencing the issue number in the commit message (`fixes #<number>`).

4. **If it's already resolved or won't be fixed:** Comment explaining the decision:
   ```bash
   gh issue comment <number> --body "..."
   gh issue close <number>
   ```

5. **If resolved by recent code:** Comment pointing to the PR or commit:
   ```bash
   gh issue comment <number> --body "Resolved in #<PR-number> / <commit-hash>. <brief explanation of what was done>."
   gh issue close <number>
   ```

---

### /release [version]

Complete release workflow for a new lmcode version.

**Steps:**

1. **Verify readiness:**
   - Run full CI check: `uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run pytest`
   - Check that `dev` is up to date: `gh pr list --base dev` (should be empty or only things going in this release)

2. **Update version strings.** The version appears in two places:
   - `src/lmcode/__init__.py`: `__version__ = "X.Y.Z"`
   - `pyproject.toml`: `version = "X.Y.Z"`
   - Also update `tests/test_smoke.py` which asserts the specific version string

3. **Update CHANGELOG.md.** Move items from `[Unreleased]` to a new `[X.Y.Z] - YYYY-MM-DD` section.

4. **Provide git commands for the release commit:**
   ```bash
   git checkout dev && git pull origin dev
   git add src/lmcode/__init__.py pyproject.toml CHANGELOG.md tests/test_smoke.py
   git commit -m "chore: release vX.Y.Z"
   git push origin dev
   ```

5. **Create the PR dev → main** (provide as text):
   ```bash
   gh pr create --base main --head dev --title "release: vX.Y.Z" --body "$(cat CHANGELOG.md | ...)"
   ```

6. **After the PR is merged**, provide the tag and GitHub release commands:
   ```bash
   git checkout main && git pull origin main
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   gh release create vX.Y.Z --title "vX.Y.Z" --notes "..."
   ```

7. **Tell the user:** "Once the release is published, announce in the repo discussions if relevant."

---

### /test-playground

Run a manual end-to-end test of lmcode features using the `playground/` sandbox directory.

**Instructions for the user:**

Start `uv run lmcode chat` in the lmcode repo directory, then run these prompts in sequence to test each UI feature. The playground directory is safe to modify — it's designed for this.

**Test sequence:**

1. **read_file panel** (should show syntax-highlighted panel with line numbers):
   ```
   read the file playground/calculator.py
   ```

2. **write_file diff block — modification** (should show side-by-side diff with +/- counts):
   ```
   add a multiply(a, b) function to playground/calculator.py
   ```

3. **write_file new file** (should show new-file panel, not a diff):
   ```
   create playground/greet.py with a greet(name) function
   ```

4. **run_shell IN/OUT panel** (should show the IN/OUT panel with separator):
   ```
   run python playground/calculator.py
   ```

5. **search_code** (should show inline results):
   ```
   search for "def " in playground/
   ```

6. **multi-step flow** (tests multiple tool calls):
   ```
   read playground/data.json, add a "version": "1.0" field, and save it
   ```

7. **slash commands:**
   - `/tokens` — should show prompt/generated counts and context arc
   - `/status` — should show mode, verbose, tips, stats, context
   - `/history 3` — should show last 3 turns as panels
   - `/compact` — should summarise and reset history
   - `/verbose` — toggle off, make a request, check tool calls are hidden
   - `/help` — should show full command table

8. **Tab mode cycling** — press Tab to cycle ask → auto → strict → ask

**What to look for:**
- Spinner animates with state labels (thinking. / working. / finishing.)
- Diff blocks show Catppuccin colors (rose on maroon / green on dark green)
- File panels have violet border, one-dark theme, line numbers
- Shell panels show IN/OUT with separator Rule
- Stats line appears after each response (↑ prompt ↓ generated, tok/s, time)

---

### /check

Run all CI checks and report the status.

**Execute each check and report results:**

```bash
uv run ruff check .
```
Report: how many errors, which files, what rules.

```bash
uv run ruff format --check .
```
Report: which files would be reformatted.

```bash
uv run mypy src/
```
Report: how many errors, which files.

```bash
uv run pytest -v
```
Report: how many passed/failed/skipped.

**Summary format:**
```
ruff check:   PASS / FAIL (N errors in X files)
ruff format:  PASS / FAIL (N files need formatting)
mypy:         PASS / FAIL (N errors)
pytest:       PASS / FAIL (N passed, N failed, N skipped)

Overall: READY TO COMMIT / NEEDS FIXES
```

If anything fails, diagnose and fix the issues, then re-run to confirm all green.

---

### /issues

List all open GitHub issues with priorities and status.

**Steps:**

1. Fetch all open issues:
   ```bash
   gh issue list --limit 100 --state open
   ```

2. Group and display them by type (bug / feature / question) and estimate priority based on:
   - Labels
   - References in ROADMAP.md
   - References in comments in the codebase
   - Whether they block other work

3. Format the output as a prioritized table:
   ```
   HIGH PRIORITY (blocking current milestone)
   #XX  [bug]     title
   #XX  [feat]    title

   MEDIUM PRIORITY (v0.5 scope)
   #XX  [feat]    title

   LOW / ICEBOX
   #XX  [feat]    title
   ```

4. If the user asks to work on a specific issue, invoke the appropriate skill (`/feature` or `/fix`).

---

### /explain [file or concept]

Explain a file, module, or concept in the lmcode codebase.

**Steps:**

1. **Identify what to explain.** If the user passed a file path, read it. If they passed a concept (e.g. "the tool registry" or "how slash commands work"), identify the relevant file(s) first.

2. **Read the relevant code** using `read_file`.

3. **Explain clearly:**
   - What this file/concept does and why it exists
   - How it fits into the overall architecture
   - Key design decisions and trade-offs
   - Any gotchas or non-obvious behaviors
   - Related files / call sites

4. **Show code snippets** only for the most important parts — the function signature, the key pattern, the non-obvious line. Don't paste entire files.

**Common explanation topics:**
- "the agent loop" → `agent/core.py`, `Agent._run_turn()`, `model.act()`
- "tool registration" → `tools/registry.py`, `@register`, import in `core.py`
- "LMCODE.md" → `config/lmcode_md.py`, `_build_system_prompt()`
- "slash commands" → `_SLASH_COMMANDS` list, `Agent._handle_slash()` in `core.py`
- "permission modes" → `MODES` in `ui/status.py`, `self._mode` in `Agent`
- "the diff block" → `_render_diff_sidebyside()` in `core.py`
- "settings" → `config/settings.py`, `get_settings()`, `config.toml`
- "colors" → `ui/colors.py`, all semantic aliases

---

## 7. Key Constants and Patterns

### Colors (`src/lmcode/ui/colors.py`)
```python
ACCENT = "#a78bfa"        # violet — main brand color, headings, highlights
ACCENT_BRIGHT = "#c4b5fd" # lighter violet — arrows, secondary accents
TEXT_PRIMARY = "#ffffff"
TEXT_SECONDARY = "#d1d5db"
TEXT_MUTED = "#9ca3af"
BG_PRIMARY = "#121127"
BORDER = "#2d2d3a"
SUCCESS = "#10b981"       # green
WARNING = "#f59e0b"       # amber
ERROR = "#ef4444"         # red
INFO = "#3b82f6"          # blue
```

### Tool Registration Pattern
```python
# In any tools/*.py file:
from lmcode.tools.registry import register

@register
def my_tool(param: str) -> str:
    """One-line description the model will read."""
    ...

# CRITICAL: The module must be imported in agent/core.py to trigger @register:
from lmcode.tools import filesystem  # noqa: F401 — ensures @register decorators run
```

### Slash Commands
```python
# In agent/core.py — two places to update when adding a slash command:

# 1. The list (drives /help output and ghost-text autocomplete):
_SLASH_COMMANDS: list[tuple[str, str]] = [
    ("/mycommand [arg]", "Description shown in /help"),
    ...
]

# 2. The handler (in Agent._handle_slash):
if cmd == "/mycommand":
    # handle it
    return True
```

### System Prompt
`_BASE_SYSTEM_PROMPT` in `agent/core.py` — injected with `{cwd}` and `{platform}`. `_build_system_prompt()` appends any `LMCODE.md` content found walking up the directory tree.

### Settings Access
```python
from lmcode.config.settings import get_settings
settings = get_settings()  # lazy singleton; reads config.toml + LMCODE_ env vars
```

### PR Branch Flow
```
feat/* or fix/*  →  dev  →  main
```

### Context Window Arc Characters
`_CTX_ARCS = ["○", "◔", "◑", "◕", "●"]` — shown in `/tokens` and `/status`. Warns at 80% usage (`_CTX_WARN_THRESHOLD = 0.80`).

### Spinner States
- `"thinking"` — model is processing, no tool call yet
- `"working"` — tool call in progress (no path known)
- `"tool /path/fragment"` — tool call with a file path (last 30 chars of path)
- `"finishing"` — tool result received, model writing final response

---

## 8. Known Issues / Gotchas

### LM Studio SDK event loop binding
The SDK's `AsyncTaskManager` is bound to the main event loop. Everything async — including `model.act()`, `model.respond()`, and `model.get_context_length()` — must run on the main loop. Do not offload to thread executors. The keepalive spinner task runs on the same loop and works because `model.act()` yields control during HTTP I/O.

### Spinner freeze during synchronous tool calls
The keepalive task updates the spinner every 100ms, but it only runs when `model.act()` yields to the event loop (during async HTTP prefill). During synchronous tool execution (file reads, shell commands), the event loop is blocked and the spinner freezes. This is a known limitation; see open issue tracking. Adding `await asyncio.sleep(0)` before tool execution did not help in practice.

### The `filesystem` import in `core.py`
```python
from lmcode.tools import filesystem  # noqa: F401 — ensures @register decorators run
```
This import looks unused (and ruff would flag it without the `noqa`). It is essential: importing the module runs the `@register` decorators that populate the tool registry. Without it, no tools are available. Every new tool module must be imported here.

### `ruff format` must run before commits
The CI lint job runs `uv run ruff format --check .` (not `ruff format .`). It will fail if files are not formatted. Always run `uv run ruff format .` before staging, or use `uv run pre-commit install` to automate it.

### `tests/test_smoke.py` hardcodes the version string
`test_version_string()` asserts `lmcode.__version__ == "0.1.0"`. Update this test when bumping the version in `__init__.py` and `pyproject.toml`.

### `write_file` always does full overwrites
There is no surgical edit tool yet. The agent must call `read_file` first, modify the content in memory, then call `write_file` with the complete new content. The diff block in the UI is generated by comparing the pre-write content (captured before the write) with the new content.

### Config is a lazy singleton
`get_settings()` caches the `Settings` instance after the first call. If settings are changed at runtime (e.g., via `lmcode config set`), call `reset_settings()` to clear the cache so the next `get_settings()` reloads from disk.

### Many modules are stubs
`agent/context.py`, `agent/memory.py`, `mcp/bridge.py`, `mcp/client.py`, `mcp/openapi.py`, `session/recorder.py`, `session/storage.py`, `ui/chat_ui.py`, `ui/viewer.py`, and all `ui/components/` files are single-line stubs. Don't be surprised when they're empty.

---

## 9. Testing

### Test structure
```
tests/
├── conftest.py                     # tmp_repo fixture, mock_lmstudio fixture
├── test_smoke.py                   # Import and CLI smoke tests
├── test_agent/
│   └── test_core.py                # Agent class, _build_system_prompt, _run_turn
├── test_tools/
│   ├── test_filesystem.py          # read_file, write_file, list_files + helpers
│   ├── test_shell.py               # run_shell
│   └── test_search.py              # search_code
├── test_mcp/                       # (empty, MCP not implemented)
├── test_plugins/                   # (empty, plugins not fully implemented)
└── test_session/                   # (empty, session not implemented)
```

### Testing conventions
- Use `tmp_path` pytest fixture for any test that reads or writes files
- Mock LM Studio via `tests/conftest.py::mock_lmstudio` for unit tests
- Tests that require a running LM Studio instance are marked `@pytest.mark.integration` and skipped in CI unless `LMCODE_INTEGRATION=1` is set
- Every new tool module gets its own `tests/test_tools/test_<module>.py`
- Test helpers (private functions) directly — they're in scope if you import them
- `asyncio_mode = "auto"` is set in pyproject.toml, so async tests work without `@pytest.mark.asyncio` decoration (though it's harmless to include it)
- Avoid mocking the database or filesystem — use real `tmp_path` fixtures

### Running tests
```bash
uv run pytest                                    # all tests
uv run pytest tests/test_tools/                  # one directory
uv run pytest tests/test_smoke.py::test_cli_help # one test
uv run pytest --cov=src/lmcode --cov-report=term-missing  # with coverage
uv run pytest -k "filesystem"                    # filter by name
```

---

## 10. Project Files Reference

| File | Purpose |
|------|---------|
| `pyproject.toml` | Package metadata, dependencies, ruff/mypy/pytest config |
| `README.md` | Public documentation, feature list, install instructions |
| `DESIGN.md` | Architecture decisions, agent loop design, plugin/MCP/multi-agent design |
| `ROADMAP.md` | Planned versions and features |
| `CONTRIBUTING.md` | Contributor guide: setup, standards, PR checklist |
| `CHANGELOG.md` | Version history (Keep a Changelog format) |
| `SKELETON.md` | Full file tree breakdown |
| `playground/` | Safe sandbox for testing features; edit/break anything here |
| `.github/workflows/ci.yml` | CI: test (pytest + coverage), lint (ruff), typecheck (mypy) |
| `LMCODE.md` | (this repo) Project context injected into lmcode's own system prompt |
| `CLAUDE.md` | (this file) Claude Code instructions and skills |
