# Configuration

lmcode is configured via a TOML file at `~/.config/lmcode/config.toml` (or the platform equivalent via platformdirs).

## File location

```python
from lmcode.config.paths import config_file
print(config_file())
# Linux:   ~/.config/lmcode/config.toml
# macOS:   ~/Library/Application Support/lmcode/config.toml
# Windows: C:\Users\<user>\AppData\Roaming\lmcode\config.toml
```

## Full schema

```toml
[lmstudio]
# LM Studio server base URL
base_url = "http://localhost:1234"

# Default model identifier — "auto" lets LM Studio pick the loaded model
model = "auto"

[agent]
# Maximum number of agent loop iterations per run
max_rounds = 50

# Whether to confirm before writing files
confirm_writes = false

[session]
# Whether to record sessions to disk
enabled = true

# Where to store session files (defaults to platformdirs data dir)
# sessions_dir = "~/.local/share/lmcode/sessions"

# Maximum session file size in MB before rotation
max_size_mb = 50
```

## Settings classes

Defined in `src/lmcode/config/settings.py` with [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/):

```python
class LMStudioSettings(BaseSettings):
    base_url: str = "http://localhost:1234"
    model: str = "auto"

class AgentSettings(BaseSettings):
    max_rounds: int = 50
    confirm_writes: bool = False

class SessionSettings(BaseSettings):
    enabled: bool = True
    sessions_dir: Path | None = None
    max_size_mb: int = 50
```

## Accessing settings in code

```python
from lmcode.config.settings import get_settings

settings = get_settings()
print(settings.lmstudio.base_url)
print(settings.agent.max_rounds)
```

`get_settings()` is a lazy singleton — the config file is read once on first call.

## Per-repo context: `LMCODE.md`

Place a `LMCODE.md` file in any directory (or any parent directory) to inject project-specific context into the agent's system prompt. Multiple files are discovered by walking up the tree and concatenated.

```markdown
# LMCODE.md

This project uses Python 3.12+ and uv for package management.
Never use `pip install` directly — always use `uv add`.
Run tests with `uv run pytest`.
```
