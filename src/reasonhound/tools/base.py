"""The tool abstraction agents act through.

A :class:`Tool` has a wire name, a description for the model, a strict Pydantic
argument model, and a :meth:`Tool.run` that returns text for the model. Tools
see the project only through a :class:`ToolContext`, which pins them to the
scan root and the exclude list.

Wire names use underscores (``fs_read``, not ``fs.read``): OpenAI and Anthropic
only accept ``[a-zA-Z0-9_-]`` in tool names.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from reasonhound.config import DEFAULT_EXCLUDE, REPORT_DIRNAME
from reasonhound.providers.base import ToolSpec
from reasonhound.tools.schema import portable_schema

__all__ = ["TOOL_NAME_PATTERN", "Tool", "ToolArgs", "ToolContext", "ToolError"]

#: The strictest tool-name grammar across the supported providers.
TOOL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class ToolError(Exception):
    """A recoverable tool failure; its message is returned to the model as an error."""


class ToolArgs(BaseModel):
    """Base for tool argument models: unknown arguments are rejected."""

    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class ToolContext:
    """What a tool may touch: one project root, minus the excluded names.

    The report folder is always excluded, so agents never read their own output
    (or a previous run's findings) back as if it were project code.
    """

    root: Path
    exclude: tuple[str, ...] = DEFAULT_EXCLUDE

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", self.root.resolve())
        if REPORT_DIRNAME not in self.exclude:
            object.__setattr__(self, "exclude", (*self.exclude, REPORT_DIRNAME))


class Tool(ABC):
    """One capability an agent can be granted."""

    name: ClassVar[str]
    description: ClassVar[str]
    args_model: ClassVar[type[ToolArgs]]

    def spec(self) -> ToolSpec:
        """The provider-neutral definition offered to the model."""
        return ToolSpec(
            name=self.name,
            description=self.description,
            input_schema=portable_schema(self.args_model),
        )

    @abstractmethod
    def run(self, args: ToolArgs, ctx: ToolContext) -> str:
        """Execute with validated *args*; raise :class:`ToolError` on a bad request."""
