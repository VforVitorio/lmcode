# Configuration

lmcode is configured via a TOML file. The file location is platform-dependent (via [platformdirs](https://platformdirs.readthedocs.io/)):

- Linux: `~/.config/lmcode/lmcode.toml`
- macOS: `~/Library/Application Support/lmcode/lmcode.toml`
- Windows: `%APPDATA%\lmcode\lmcode.toml`

## Full schema

```toml
[lmstudio]
# LM Studio server host and port
host = "localhost"
port = 1234

# Default model identifier — "auto" uses whatever is loaded in LM Studio
model = "auto"

[agent]
# Maximum number of agent loop iterations per run
max_rounds = 50

# Starting permission mode: ask | auto | strict
permission_mode = "ask"

# Seconds before a tool call times out
timeout_seconds = 30

[ui]
# Rich spinner name (see https://rich.readthedocs.io/en/stable/spinner.html)
spinner = "dots"

# Show rotating tips below the spinner during model inference
show_tips = true

# Show per-response token stats (↑ prompt  ↓ generated  tok/s  elapsed)
show_stats = true
```

## Settings classes

Defined in `src/lmcode/config/settings.py` using [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/):

```python
class LMStudioSettings(BaseSettings):
    host: str = "localhost"
    port: int = 1234
    model: str = "auto"

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}/v1"

class AgentSettings(BaseSettings):
    max_rounds: int = 50
    permission_mode: Literal["ask", "auto", "strict"] = "ask"
    timeout_seconds: int = 30
    max_file_bytes: int = 100_000  # overridden at startup based on context window

class UISettings(BaseSettings):
    spinner: str = "dots"
    show_tips: bool = True
    show_stats: bool = True
```

## Environment variable overrides

Any setting can be overridden with an environment variable using the `LMCODE_` prefix and double-underscore nesting:

```bash
LMCODE_LMSTUDIO__HOST=192.168.1.10
LMCODE_AGENT__PERMISSION_MODE=auto
LMCODE_UI__SHOW_TIPS=false
```

## Accessing settings in code

```python
from lmcode.config.settings import get_settings

settings = get_settings()
print(settings.lmstudio.base_url)
print(settings.agent.max_rounds)
print(settings.ui.show_tips)
```

`get_settings()` is a lazy singleton — the config file is read once on first call. Call `reset_settings()` to force a reload (useful in tests).

## Token-aware file read limit

`agent.max_file_bytes` is automatically overridden at session startup based on the model's actual context window. The formula is:

```
max_file_bytes = clamp(ctx_tokens * 4 * 0.20, 50_000, 500_000)
```

This ensures `read_file` doesn't consume more than ~20% of the context window with a single file. The value is retrieved via `model.get_context_length()`; if that fails, a heuristic based on size keywords in the model ID is used (e.g. `128k`, `32k`).

## Per-repo context: `LMCODE.md`

Place a `LMCODE.md` file in any directory (or any parent directory) to inject project-specific context into the agent's system prompt. Multiple files are discovered by walking up the directory tree and concatenated.

```markdown
# LMCODE.md

This project uses Python 3.12+ and uv for package management.
Never use `pip install` directly — always use `uv add`.
Run tests with `uv run pytest`.
```

Discovered by `src/lmcode/config/lmcode_md.py`.
