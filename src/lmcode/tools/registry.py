"""Global tool registry. Maps tool names to callables."""

from __future__ import annotations

from typing import Callable

_registry: dict[str, Callable[..., str]] = {}


def register(fn: Callable[..., str]) -> Callable[..., str]:
    """Decorator to register a function as an lmcode tool."""
    _registry[fn.__name__] = fn
    return fn


def get_all() -> list[Callable[..., str]]:
    """Return all registered tools as a list (for model.act())."""
    return list(_registry.values())


def get(name: str) -> Callable[..., str] | None:
    """Return a tool by name."""
    return _registry.get(name)
