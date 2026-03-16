"""Cross-platform path resolution using platformdirs."""

from __future__ import annotations

from pathlib import Path

from platformdirs import user_config_dir, user_data_dir

APP_NAME = "lmcode"
APP_AUTHOR = "lmcode"


def config_dir() -> Path:
    """~/.config/lmcode/ (Linux/macOS) or %APPDATA%/lmcode/ (Windows)."""
    return Path(user_config_dir(APP_NAME, APP_AUTHOR))


def data_dir() -> Path:
    """~/.local/share/lmcode/ (Linux/macOS) or %LOCALAPPDATA%/lmcode/ (Windows)."""
    return Path(user_data_dir(APP_NAME, APP_AUTHOR))


def sessions_dir() -> Path:
    """Directory where session JSONL files are stored."""
    return data_dir() / "sessions"


def config_file() -> Path:
    """Path to the main config TOML file."""
    return config_dir() / "config.toml"


def ensure_dirs() -> None:
    """Create all required directories if they don't exist."""
    config_dir().mkdir(parents=True, exist_ok=True)
    data_dir().mkdir(parents=True, exist_ok=True)
    sessions_dir().mkdir(parents=True, exist_ok=True)
