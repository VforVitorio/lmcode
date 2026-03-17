# Development Setup

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (package manager)
- [LM Studio](https://lmstudio.ai/) (for running the agent locally)
- [GitHub CLI](https://cli.github.com/) (`gh`) — optional, for PR workflow

## Getting started

```bash
# Clone
git clone https://github.com/VforVitorio/lmcode.git
cd lmcode

# Install all dependencies (including dev)
uv sync --all-extras

# Verify
uv run lmcode --version
uv run pytest
```

## Running the CLI

```bash
uv run lmcode --help
uv run lmcode chat
uv run lmcode chat --model "llama-3.2-3b-instruct" --max-rounds 20
```

## Running tests

```bash
# All tests
uv run pytest

# With coverage
uv run pytest --cov=src/lmcode --cov-report=term-missing

# A specific file
uv run pytest tests/test_smoke.py -v
```

## Linting and formatting

```bash
# Check
uv run ruff check .
uv run ruff format --check .

# Auto-fix
uv run ruff check --fix .
uv run ruff format .

# Type check
uv run mypy src/lmcode
```

## Branch workflow

```
main  ←  dev  ←  feat/*
```

1. Branch from `dev`: `git checkout -b feat/my-feature dev`
2. Push and open a PR targeting `dev`
3. PRs to `main` are only for releases, created from `dev`

> When a PR is merged, the source branch is deleted automatically (configured at the repo level).

## Project structure

```
lmcode/
├── src/lmcode/
│   ├── cli/         # Typer app, subcommands
│   ├── config/      # Settings, paths, LMCODE.md discovery
│   ├── tools/       # Tool registry and built-in tools
│   ├── agent/       # Agent core (model.act wrapper)
│   ├── plugins/     # pluggy hookspecs and manager
│   ├── session/     # JSONL event models and recorder
│   ├── mcp/         # FastMCP / OpenAPI integration
│   └── ui/          # Colors, banner, Rich components
├── tests/
├── docs/            # This documentation
├── assets/          # Logo and other static assets
└── .github/         # CI workflow, issue templates
```

## CI

GitHub Actions runs on every push and PR to `main` or `dev`:

| Job | Command |
|-----|---------|
| `test` | `uv run pytest --cov=src/lmcode` |
| `lint` | `uv run ruff check .` + `uv run ruff format --check .` |
| `typecheck` | `uv run mypy src/lmcode` |

See [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml).
