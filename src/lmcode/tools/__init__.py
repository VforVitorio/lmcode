"""Tool registry — importing this package registers all built-in tools.

Each submodule that defines tools must be imported here so that the
@register decorators run at package load time.
"""

from lmcode.tools import filesystem  # noqa: F401
