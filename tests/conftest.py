"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """A temporary directory that mimics a project repo."""
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "README.md").write_text("# Test repo")
    return tmp_path


@pytest.fixture
def mock_lmstudio():
    """Mock LM Studio model — skips real inference in unit tests."""
    model = MagicMock()
    model.act = MagicMock(return_value=MagicMock(content="done"))
    return model
