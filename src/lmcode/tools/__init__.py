"""Tool registry — importing this package registers all built-in tools.

Each submodule that defines tools must be imported here so that the
@register decorators run at package load time.
"""

from lmcode.tools import filesystem, search, shell  # noqa: F401
from lmcode.tools.registry import get_all  # noqa: F401 — re-exported for convenience

__all__ = ["get_all"]
