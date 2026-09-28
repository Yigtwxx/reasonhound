"""Tools agents act through, each granted per agent via an allowlist.

See :mod:`reasonhound.tools.registry` for the allowlist enforcement (layer 2 of
the prompt-injection defense) and :mod:`reasonhound.tools.fs` for the sandbox.
"""

from __future__ import annotations

from reasonhound.tools.base import TOOL_NAME_PATTERN, Tool, ToolArgs, ToolContext, ToolError
from reasonhound.tools.fs import FsGlob, FsGrep, FsRead
from reasonhound.tools.registry import (
    MAX_TOOL_OUTPUT_CHARS,
    Toolbox,
    ToolRegistry,
    default_registry,
)
from reasonhound.tools.schema import portable_schema
from reasonhound.tools.syntax import AstParse

__all__ = [
    "MAX_TOOL_OUTPUT_CHARS",
    "TOOL_NAME_PATTERN",
    "AstParse",
    "FsGlob",
    "FsGrep",
    "FsRead",
    "Tool",
    "ToolArgs",
    "ToolContext",
    "ToolError",
    "ToolRegistry",
    "Toolbox",
    "default_registry",
    "portable_schema",
]
