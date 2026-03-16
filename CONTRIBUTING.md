# Contributing to lmcode

First off — thanks for taking the time to contribute. lmcode is an early-stage project and every contribution matters.

---

## Before you start

- **Open an issue before opening a PR** for anything non-trivial. This avoids duplicated work and ensures the direction fits the project.
- For bug fixes and small improvements, a PR directly is fine.
- Check the [ROADMAP](ROADMAP.md) to understand what's planned and what's in scope.

---

## Dev setup

lmcode uses [uv](https://docs.astral.sh/uv) for dependency management.

```bash
# clone
git clone https://github.com/yourusername/lmcode
cd lmcode

# install all deps including dev extras
uv sync --all-extras

# run tests
uv run pytest

# run lmcode locally
uv run lmcode --help
```

You'll also need:
- **LM Studio** running locally with a model loaded and the local server enabled (`localhost:1234`)
- Python 3.11+

---

## Project structure

See [SKELETON.md](SKELETON.md) for a full breakdown of every file and what it does.

The short version:

```
src/lmcode/
├── cli/        ← Typer commands
├── agent/      ← agent loop and context
├── tools/      ← built-in tools (filesystem, shell, git, search)
├── mcp/        ← MCP client + OpenAPI → MCP
├── plugins/    ← pluggy plugin system
├── session/    ← session recording and storage
├── ui/         ← Textual TUI
└── config/     ← settings and LMCODE.md handling
```

---

## Code style

All code is formatted and linted with [ruff](https://docs.astral.sh/ruff).

```bash
# format
uv run ruff format .

# lint
uv run ruff check .

# type check
uv run mypy src/
```

There's a pre-commit config if you want it:

```bash
uv run pre-commit install
```

Rules:
- Type annotations everywhere in `src/` — mypy must pass
- No `Any` unless truly unavoidable, and comment why
- Pydantic models for all data crossing module boundaries
- Public functions and classes get docstrings; internal helpers don't need them

---

## Tests

```bash
# all tests
uv run pytest

# specific module
uv run pytest tests/test_tools/

# with coverage
uv run pytest --cov=src/lmcode
```

Guidelines:
- Every new tool needs a test in `tests/test_tools/`
- Tests that need LM Studio are marked `@pytest.mark.integration` and skipped in CI unless `LMCODE_INTEGRATION=1` is set
- Use `tmp_path` fixture for any test that reads/writes files
- Mock the LM Studio SDK for unit tests — see `tests/conftest.py`

---

## Adding a built-in tool

1. Create `src/lmcode/tools/your_tool.py`
2. Define your tool as a plain Python function with type hints and a docstring (the docstring becomes the tool description the model sees)
3. Register it in `src/lmcode/tools/registry.py`
4. Add tests in `tests/test_tools/test_your_tool.py`

```python
# src/lmcode/tools/your_tool.py

def your_tool(param: str) -> str:
    """
    One-line description of what this tool does.
    The model will read this to decide when to use it.

    Args:
        param: what this parameter is

    Returns:
        what this returns
    """
    ...
```

---

## Adding a plugin hook

If you need a new lifecycle hook, add it to `src/lmcode/plugins/hookspecs.py` with a clear docstring explaining when it fires and what it receives.

---

## Pull request checklist

- [ ] Tests pass (`uv run pytest`)
- [ ] Ruff passes (`uv run ruff check .`)
- [ ] Mypy passes (`uv run mypy src/`)
- [ ] New behavior is tested
- [ ] CHANGELOG.md updated under `[Unreleased]`
- [ ] PR description explains the why, not just the what

---

## Commit style

Use [Conventional Commits](https://www.conventionalcommits.org):

```
feat: add search_code tool using ripgrep
fix: handle empty file in read_file tool
docs: add plugin development guide
refactor: extract tool registry into its own module
test: add integration tests for shell tool
```

---

## Issues

Use the issue templates. When reporting a bug, include:
- OS and Python version
- LM Studio version and model being used
- The command you ran
- Full error output

---

## License

By contributing you agree that your contributions will be licensed under the [MIT License](LICENSE).
