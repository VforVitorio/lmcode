# lmcode project context

This is the **lmcode** source repository — the local coding agent CLI powered by LM Studio.

## What this project is

lmcode is a terminal coding agent that uses LM Studio for local inference. It is the open-source alternative to Claude Code for local models. The codebase you are working inside is lmcode itself.

## Key facts

- **Language**: Python 3.12
- **Package manager**: uv (`uv sync --all-extras` to install, `uv run <cmd>` to run)
- **Entry point**: `uv run lmcode chat`
- **Version**: 0.1.0 (in `src/lmcode/__init__.py` and `pyproject.toml`)
- **Main branch**: `main` (protected, PR only); development branch: `dev`
- **CI**: `.github/workflows/ci.yml` — pytest + ruff + mypy on push/PR

## Source layout

```
src/lmcode/
├── agent/core.py        # The agent loop, slash commands, spinner, diff UI
├── tools/               # read_file, write_file, list_files, run_shell, search_code
│   ├── registry.py      # @register decorator
│   └── filesystem.py    # Must be imported in core.py to trigger @register
├── config/
│   ├── settings.py      # Pydantic-settings; get_settings() singleton
│   ├── paths.py         # platformdirs: config_dir(), sessions_dir()
│   └── lmcode_md.py     # Walks up tree for LMCODE.md files
├── ui/
│   ├── colors.py        # All color constants — always import from here
│   ├── banner.py        # Startup ASCII art banner
│   └── status.py        # build_prompt(), build_status_line(), mode cycling
├── plugins/             # pluggy hookspecs + manager (on_tool_call, etc.)
├── session/models.py    # Pydantic event models for session recording
└── mcp/                 # MCP client stubs (not yet implemented)
```

## Development commands

```bash
uv run pytest                          # run tests
uv run ruff check .                    # lint
uv run ruff format .                   # format
uv run mypy src/                       # type check
uv run lmcode chat                     # run lmcode
```

Full CI check (run before commits):
```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run pytest
```

## Code standards

- `from __future__ import annotations` at the top of every source file
- Docstring on every module file and every public function
- Full type hints everywhere; mypy strict must pass
- Colors always imported from `lmcode.ui.colors` — never hardcode hex strings
- Tools return `str` and never raise exceptions (return `"error: ..."` on failure)
- New tools need `@register` decorator and must be imported in `agent/core.py`

## Git workflow

- Feature branches: `feat/<name>` → PR to `dev`
- Bug fix branches: `fix/<name>` → PR to `dev`
- `dev` → `main` is done via release PRs
- Never push directly to `main`
- The user runs all git commands; provide them as text

## Playground

The `playground/` directory is a safe sandbox. Use it to test features:
- `playground/calculator.py` — good for testing write_file diff blocks
- `playground/data.json` — JSON read/edit testing
- `playground/notes.txt` — plain text read/write
- `playground/script.sh` — triggers run_shell IN/OUT panel

## Known gotchas

- The LM Studio SDK `AsyncTaskManager` is bound to the main event loop — keep all async on it
- `from lmcode.tools import filesystem  # noqa: F401` in `core.py` is intentional — it triggers `@register`
- `tests/test_smoke.py` hardcodes the version string; update it when bumping versions
- `write_file` does full overwrites — agent must call `read_file` first for existing files
- Many `ui/components/`, `mcp/`, `session/` files are single-line stubs
