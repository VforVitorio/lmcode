# Contributing Guide (Technical)

> For the short version, see [CONTRIBUTING.md](../../CONTRIBUTING.md) in the repo root.

## Adding a new built-in tool

1. Create or edit a file in `src/lmcode/tools/builtin/`
2. Decorate the function with `@register`
3. Add a test in `tests/tools/test_<name>.py`
4. Document it in [docs/features/tools.md](../features/tools.md)

Example:

```python
# src/lmcode/tools/builtin/files.py
from pathlib import Path
from lmcode.tools.registry import register
from lmcode.tools.base import ToolResult

@register
def read_file(path: str) -> str:
    """Read the contents of a file. Returns the file text or an error message."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as e:
        return f"error: {e}"
```

## Adding a new CLI subcommand

1. Create `src/lmcode/cli/<name>.py` with a Typer app
2. Register it in `src/lmcode/cli/app.py` with `app.add_typer()`
3. Add smoke tests in `tests/test_smoke.py`
4. Document it in [docs/features/cli.md](../features/cli.md)

## Adding a new config option

1. Add the field to the relevant settings class in `src/lmcode/config/settings.py`
2. Update [docs/features/config.md](../features/config.md) with the new field

## Release process

1. Bump version in `src/lmcode/__init__.py` and `pyproject.toml`
2. Update `CHANGELOG.md`
3. Merge `dev` → `main` via PR
4. Tag the release: `git tag v0.x.0 && git push origin v0.x.0`
5. GitHub Actions publishes to PyPI (when configured)
