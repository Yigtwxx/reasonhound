"""Tool registry and per-agent toolboxes (prompt-injection defense, layer 2).

The :class:`ToolRegistry` holds every tool Reasonhound has. An agent never sees
the registry: it gets a :class:`Toolbox` built from its fixed allowlist, which
offers the model only those tools and refuses anything else. A request for a
tool outside the allowlist is answered with an error, never executed -- there is
no path from "file content convinced the model" to "a capability the agent was
not granted".
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import ValidationError

from reasonhound.providers.base import ToolCall, ToolResult, ToolSpec
from reasonhound.security.fencing import FENCE_BEGIN, FENCE_END
from reasonhound.tools.base import TOOL_NAME_PATTERN, Tool, ToolContext, ToolError
from reasonhound.tools.fs import FsGlob, FsGrep, FsRead
from reasonhound.tools.syntax import AstParse

__all__ = ["MAX_TOOL_OUTPUT_CHARS", "ToolRegistry", "Toolbox", "default_registry"]

#: Tool output beyond this is cut, so one call cannot flood the context window.
MAX_TOOL_OUTPUT_CHARS = 20_000

# A fence opens as "[BEGIN UNTRUSTED DATA" with an optional " source=..." label.
_FENCE_OPEN = FENCE_BEGIN[:-1]


class ToolRegistry:
    """Every tool available to the runtime, by wire name."""

    def __init__(self, tools: Iterable[Tool] = ()) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if not TOOL_NAME_PATTERN.fullmatch(tool.name):
            raise ValueError(f"invalid tool name {tool.name!r}: use [a-zA-Z0-9_-], max 64")
        if tool.name in self._tools:
            raise ValueError(f"tool {tool.name!r} is already registered")
        self._tools[tool.name] = tool

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._tools)

    def toolbox(self, allowed: Iterable[str]) -> Toolbox:
        """A view restricted to *allowed*; unknown names fail loudly at build time."""
        allowed = frozenset(allowed)
        unknown = allowed - self.names
        if unknown:
            raise ValueError(f"unknown tool(s) in allowlist: {', '.join(sorted(unknown))}")
        return Toolbox({name: self._tools[name] for name in sorted(allowed)})


class Toolbox:
    """The tools one agent may call, and the only way it can call them."""

    def __init__(self, tools: dict[str, Tool]) -> None:
        self._tools = tools

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._tools)

    def allows(self, name: str) -> bool:
        return name in self._tools

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(tool.spec() for tool in self._tools.values())

    def invoke(self, call: ToolCall, ctx: ToolContext) -> ToolResult:
        """Run *call* and return the result for the model; never raises.

        Every failure -- not permitted, bad arguments, a tool error, a bug --
        becomes an ``is_error`` result the model can react to, so one bad call
        cannot take the agent down.
        """
        tool = self._tools.get(call.name)
        if tool is None:
            return _error(call, f"tool {call.name!r} is not available to this agent")
        try:
            args = tool.args_model.model_validate(call.arguments)
        except ValidationError as exc:
            return _error(call, f"invalid arguments: {_brief(exc)}")
        try:
            output = tool.run(args, ctx)
        except ToolError as exc:
            return _error(call, str(exc))
        except OSError as exc:
            return _error(call, f"filesystem error: {exc.strerror or type(exc).__name__}")
        except Exception as exc:  # a tool bug must not kill the agent loop
            return _error(call, f"internal tool error ({type(exc).__name__})")
        if len(output) > MAX_TOOL_OUTPUT_CHARS:
            output = _truncate(output)
        return ToolResult(tool_call_id=call.id, content=output)


def _truncate(output: str) -> str:
    """Hard-cut *output*, re-closing a data fence the cut left open.

    Tools size their own output; this backstop only fires for a tool that does
    not. Embedded markers are neutralized by ``fence()``, so counting the real
    ones tells whether the cut landed inside a fenced block.
    """
    cut = output[:MAX_TOOL_OUTPUT_CHARS]
    if cut.count(_FENCE_OPEN) > cut.count(FENCE_END):
        cut += f"\n{FENCE_END}"
    return cut + "\n(output truncated)"


def _error(call: ToolCall, message: str) -> ToolResult:
    return ToolResult(tool_call_id=call.id, content=f"error: {message}", is_error=True)


def _brief(exc: ValidationError) -> str:
    """One line per validation problem, without echoing the (untrusted) input."""
    return "; ".join(
        f"{'.'.join(str(p) for p in err['loc']) or 'arguments'}: {err['msg']}"
        for err in exc.errors(include_input=False)
    )


def default_registry() -> ToolRegistry:
    """The static-phase toolset available in this release."""
    return ToolRegistry([FsRead(), FsGrep(), FsGlob(), AstParse()])
