"""``ast_parse``: a tree-sitter structural outline of one source file.

Gives an agent the shape of a file -- classes, functions, methods, with line
ranges -- so it can target ``fs_read`` windows instead of reading whole files.
This is the structure half of the hybrid static engine; source -> sink tracing
(``dataflow_trace``) builds on it in the static phase.

Named ``syntax`` rather than ``ast`` so it cannot be confused with the stdlib
module.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from reasonhound.security.fencing import fence
from reasonhound.tools.base import Tool, ToolArgs, ToolContext, ToolError
from reasonhound.tools.fs import MAX_FILE_BYTES, resolve_path

__all__ = ["LANGUAGES", "AstParse", "language_for"]

#: File suffix -> tree-sitter-language-pack grammar name.
LANGUAGES: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".java": "java",
    ".php": "php",
    ".rb": "ruby",
}

# Node types that make up an outline, across the supported grammars.
_OUTLINE_KINDS: dict[str, str] = {
    "class_definition": "class",
    "class_declaration": "class",
    "class": "class",
    "interface_declaration": "interface",
    "function_definition": "function",
    "function_declaration": "function",
    "generator_function_declaration": "function",
    "method_definition": "method",
    "method_declaration": "method",
    "method": "method",
    "singleton_method": "method",
    "type_declaration": "type",
}

_MAX_OUTLINE_ENTRIES = 500


def language_for(suffix: str) -> str | None:
    """Grammar name for a file suffix, or ``None`` when unsupported."""
    return LANGUAGES.get(suffix.lower())


def _node_name(node: Any) -> str:
    name = node.child_by_field_name("name")
    if name is None or name.text is None:
        return "<anonymous>"
    return str(name.text.decode("utf-8", errors="replace"))


class AstParseArgs(ToolArgs):
    path: str = Field(description="Source file path relative to the project root.")


class AstParse(Tool):
    name = "ast_parse"
    description = (
        "Outline a source file's structure (classes, functions, methods with line "
        "ranges) using tree-sitter. Supports Python, JS/TS, Go, Java, PHP, Ruby."
    )
    args_model = AstParseArgs

    def run(self, args: ToolArgs, ctx: ToolContext) -> str:
        assert isinstance(args, AstParseArgs)
        path = resolve_path(ctx, args.path)
        language = language_for(path.suffix)
        if language is None:
            raise ToolError(f"no grammar for {args.path!r}")
        if not path.is_file():
            raise ToolError("not a file")
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ToolError(f"file is larger than {MAX_FILE_BYTES} bytes")

        from tree_sitter_language_pack import get_parser  # heavy import, paid on first use

        tree = get_parser(language).parse(path.read_bytes())  # type: ignore[arg-type]
        entries: list[str] = []
        self._walk(tree.root_node, 0, entries)
        rel = path.relative_to(ctx.root).as_posix()
        if not entries:
            return f"{language}: no classes or functions found"
        note = ""
        if len(entries) >= _MAX_OUTLINE_ENTRIES:
            note = f"\n(outline truncated at {_MAX_OUTLINE_ENTRIES} entries)"
        return f"{language} outline\n{fence(chr(10).join(entries), source=rel)}{note}"

    def _walk(self, node: Any, depth: int, entries: list[str]) -> None:
        if len(entries) >= _MAX_OUTLINE_ENTRIES:
            return
        kind = _OUTLINE_KINDS.get(node.type)
        child_depth = depth
        if kind is not None:
            start, end = node.start_point[0] + 1, node.end_point[0] + 1
            entries.append(f"{'  ' * depth}L{start}-{end} {kind} {_node_name(node)}")
            child_depth = depth + 1
        for child in node.children:
            self._walk(child, child_depth, entries)
