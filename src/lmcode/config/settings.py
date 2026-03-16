"""Application settings via pydantic-settings (loaded from config.toml)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from lmcode.config.paths import config_file, sessions_dir


class LMStudioSettings(BaseSettings):
    host: str = "localhost"
    port: int = 1234
    model: str = "auto"  # "auto" = use whatever is loaded in LM Studio

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}/v1"


class AgentSettings(BaseSettings):
    max_rounds: int = 50
    permission_mode: Literal["ask", "auto", "strict"] = "ask"
    timeout_seconds: int = 30


class SessionSettings(BaseSettings):
    save_sessions: bool = True
    sessions_dir: Path = Field(default_factory=sessions_dir)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        toml_file=str(config_file()),
        env_prefix="LMCODE_",
        env_nested_delimiter="__",
    )

    lmstudio: LMStudioSettings = Field(default_factory=LMStudioSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    session: SessionSettings = Field(default_factory=SessionSettings)


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the global settings instance (lazy singleton)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
