"""Read-only filesystem tools: ``fs_read``, ``fs_grep``, ``fs_glob``.

All three are sandboxed to the scan root. A path is resolved (following
symlinks) and must land inside the root and outside every excluded name, so
neither ``../`` nor a symlink planted in the scanned repo can reach the rest of
the disk. Everything returned is file content or file names from the scanned
project -- attacker-controlled -- so it is always data-fenced (``injection-warden``).

Exclusion is case-insensitive: macOS and Windows filesystems are, so
``.GIT/config`` would otherwise reach the excluded ``.git``. Globs are matched one
path segment at a time with ``fnmatchcase`` (linear, no backtracking blow-up).
``fs_grep`` matches literally by default. A regex runs on Python's ``re``, which
has no timeout; the pattern-length and line-length caps bound the cost of a
pathological pattern but do not eliminate it.

Each tool keeps its own output within :data:`OUTPUT_BUDGET_CHARS`, so the fence
always closes and paging hints stay accurate; the toolbox's hard cut is only a
backstop.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from fnmatch import fnmatchcase
from functools import cache
from pathlib import Path, PurePosixPath, PureWindowsPath

from pydantic import Field

from reasonhound.security.fencing import fence
from reasonhound.tools.base import Tool, ToolArgs, ToolContext, ToolError

__all__ = [
    "MAX_FILE_BYTES",
    "OUTPUT_BUDGET_CHARS",
    "FsGlob",
    "FsGrep",
    "FsRead",
    "glob_match",
    "iter_files",
    "resolve_path",
]

MAX_FILE_BYTES = 2_000_000
MAX_READ_LINES = 400
MAX_LINE_CHARS = 2_000
_GREP_SNIPPET_CHARS = 300
_BINARY_SNIFF_BYTES = 8_192
#: Characters of fenced content one tool call may return (below the toolbox cap).
OUTPUT_BUDGET_CHARS = 16_000


# --- sandbox helpers -----------------------------------------------------------


def _is_excluded(parts: tuple[str, ...], exclude: tuple[str, ...]) -> bool:
    return any(
        fnmatchcase(part.casefold(), pattern.casefold()) for part in parts for pattern in exclude
    )


def _resolve(path: Path) -> Path | None:
    """``path.resolve()``, or ``None`` for a symlink loop or unreadable link."""
    try:
        return path.resolve()
    except (OSError, RuntimeError):  # 3.11 raises RuntimeError on a loop
        return None


def _inside(ctx: ToolContext, resolved: Path) -> bool:
    """Within the root and not under an excluded name, judged on the real path."""
    if not resolved.is_relative_to(ctx.root):
        return False
    return not _is_excluded(resolved.relative_to(ctx.root).parts, ctx.exclude)


def resolve_path(ctx: ToolContext, raw: str) -> Path:
    """Resolve a model-supplied relative path inside the sandbox, or raise."""
    if not raw.strip() or "\x00" in raw:
        raise ToolError("path must be a non-empty relative path")
    if Path(raw).is_absolute() or PureWindowsPath(raw).is_absolute() or PureWindowsPath(raw).drive:
        raise ToolError("paths must be relative to the project root")
    resolved = _resolve(ctx.root / raw)
    if resolved is None:
        raise ToolError(f"{raw!r} cannot be resolved (symlink loop?)")
    if not resolved.is_relative_to(ctx.root):
        raise ToolError(f"{raw!r} is outside the project root")
    if _is_excluded(resolved.relative_to(ctx.root).parts, ctx.exclude):
        raise ToolError(f"{raw!r} is excluded from the scan")
    return resolved


def _rel(ctx: ToolContext, path: Path) -> str:
    return path.relative_to(ctx.root).as_posix()


def glob_match(rel_path: str, pattern: str) -> bool:
    """Whether a POSIX relative path matches a ``**``-aware glob.

    ``**`` as a whole segment spans zero or more directories; every other segment
    is matched against exactly one path segment with ``fnmatchcase``, whose
    translation has no catastrophic backtracking. Memoized over segment indexes,
    the match is linear in ``len(pattern_segments) * len(path_segments)``.
    """
    pat = tuple(pattern.replace("\\", "/").strip("/").split("/"))
    parts = tuple(rel_path.split("/"))

    @cache
    def match(i: int, j: int) -> bool:
        if i == len(pat):
            return j == len(parts)
        if pat[i] == "**":
            return match(i + 1, j) or (j < len(parts) and match(i, j + 1))
        return j < len(parts) and fnmatchcase(parts[j], pat[i]) and match(i + 1, j + 1)

    return match(0, 0)


def _check_pattern(pattern: str) -> None:
    if PurePosixPath(pattern).is_absolute() or PureWindowsPath(pattern).drive:
        raise ToolError("glob patterns must be relative to the project root")
    if ".." in PurePosixPath(pattern.replace("\\", "/")).parts:
        raise ToolError("glob patterns may not contain '..'")


def iter_files(ctx: ToolContext, pattern: str = "**/*") -> Iterator[Path]:
    """Yield files under the root matching *pattern*, in a stable order.

    Excluded directories are pruned before descent, and a symlinked file is
    yielded only when its target is inside the root and not excluded (the same
    rule :func:`resolve_path` applies). Symlinked directories are not followed.
    """
    for dirpath, dirnames, filenames in os.walk(ctx.root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not _is_excluded((d,), ctx.exclude))
        for name in sorted(filenames):
            if _is_excluded((name,), ctx.exclude):
                continue
            path = Path(dirpath) / name
            if path.is_symlink():
                target = _resolve(path)
                if target is None or not _inside(ctx, target):
                    continue
            if glob_match(_rel(ctx, path), pattern):
                yield path


def _read_text(path: Path) -> str:
    """Read a text file within the size cap; refuse binaries."""
    if not path.is_file():
        raise ToolError("not a file")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ToolError(f"file is larger than {MAX_FILE_BYTES} bytes")
    data = path.read_bytes()
    if b"\x00" in data[:_BINARY_SNIFF_BYTES]:
        raise ToolError("binary file")
    return data.decode("utf-8", errors="replace")


# --- fs_read -------------------------------------------------------------------


class FsReadArgs(ToolArgs):
    path: str = Field(description="File path relative to the project root.")
    start_line: int = Field(default=1, ge=1, description="First line to return (1-based).")
    max_lines: int = Field(
        default=200, ge=1, le=MAX_READ_LINES, description="How many lines to return."
    )


class FsRead(Tool):
    name = "fs_read"
    description = (
        "Read a text file from the project, with line numbers. Long files are "
        "returned in windows; use start_line to page through them."
    )
    args_model = FsReadArgs

    def run(self, args: ToolArgs, ctx: ToolContext) -> str:
        assert isinstance(args, FsReadArgs)
        path = resolve_path(ctx, args.path)
        lines = _read_text(path).splitlines()
        total = len(lines)
        if total and args.start_line > total:
            raise ToolError(f"start_line {args.start_line} is past the end ({total} lines)")
        start = args.start_line - 1
        rendered: list[str] = []
        used = 0
        for number, line in enumerate(lines[start : start + args.max_lines], start=start + 1):
            entry = f"{number:>6}| {line[:MAX_LINE_CHARS]}"
            if rendered and used + len(entry) + 1 > OUTPUT_BUDGET_CHARS:
                break  # stop on a line boundary so the header and hint stay true
            rendered.append(entry)
            used += len(entry) + 1
        numbered = "\n".join(rendered)
        end = start + len(rendered)
        header = f"lines {start + 1}-{end} of {total}" if total else "empty file"
        more = f"\n(more: call again with start_line={end + 1})" if end < total else ""
        return f"{header}\n{fence(numbered, source=_rel(ctx, path))}{more}"


# --- fs_glob -------------------------------------------------------------------


class FsGlobArgs(ToolArgs):
    pattern: str = Field(
        default="**/*",
        max_length=200,
        description="Glob relative to the project root; '**' spans directories.",
    )
    limit: int = Field(default=200, ge=1, le=500, description="Maximum paths to return.")


class FsGlob(Tool):
    name = "fs_glob"
    description = "List project files matching a glob such as 'src/**/*.py'."
    args_model = FsGlobArgs

    def run(self, args: ToolArgs, ctx: ToolContext) -> str:
        assert isinstance(args, FsGlobArgs)
        _check_pattern(args.pattern)
        paths: list[str] = []
        used = 0
        truncated = False
        for path in iter_files(ctx, args.pattern):
            rel = _rel(ctx, path)
            if len(paths) == args.limit or used + len(rel) + 1 > OUTPUT_BUDGET_CHARS:
                truncated = True
                break
            paths.append(rel)
            used += len(rel) + 1
        if not paths:
            return "no files matched"
        note = f" (first {len(paths)}; narrow the pattern)" if truncated else ""
        return f"{len(paths)} file(s){note}\n{fence(chr(10).join(paths), source='fs_glob')}"


# --- fs_grep -------------------------------------------------------------------


class FsGrepArgs(ToolArgs):
    pattern: str = Field(min_length=1, max_length=200, description="Text (or regex) to find.")
    regex: bool = Field(default=False, description="Treat pattern as a Python regex.")
    ignore_case: bool = False
    glob: str = Field(default="**/*", max_length=200, description="Limit the search to files.")
    max_results: int = Field(default=100, ge=1, le=500)


class FsGrep(Tool):
    name = "fs_grep"
    description = (
        "Search project files for text and return 'path:line: snippet' matches. "
        "Literal by default; set regex=true for a regular expression."
    )
    args_model = FsGrepArgs

    def run(self, args: ToolArgs, ctx: ToolContext) -> str:
        assert isinstance(args, FsGrepArgs)
        _check_pattern(args.glob)
        flags = re.IGNORECASE if args.ignore_case else 0
        source = args.pattern if args.regex else re.escape(args.pattern)
        try:
            matcher = re.compile(source, flags)
        except re.error as exc:
            raise ToolError(f"invalid regex: {exc}") from exc

        hits: list[str] = []
        used = 0
        skipped_lines = 0
        for path in iter_files(ctx, args.glob):
            try:
                text = _read_text(path)
            except ToolError:
                continue  # binary or oversized: not searchable
            for number, line in enumerate(text.splitlines(), start=1):
                if len(line) > MAX_LINE_CHARS:
                    skipped_lines += 1  # minified bundles; bounds regex cost
                    continue
                if matcher.search(line):
                    snippet = line.strip()[:_GREP_SNIPPET_CHARS]
                    hit = f"{_rel(ctx, path)}:{number}: {snippet}"
                    if used + len(hit) + 1 > OUTPUT_BUDGET_CHARS:
                        return self._render(hits, skipped_lines, truncated=True)
                    hits.append(hit)
                    used += len(hit) + 1
                    if len(hits) == args.max_results:
                        return self._render(hits, skipped_lines, truncated=True)
        return self._render(hits, skipped_lines, truncated=False)

    @staticmethod
    def _render(hits: list[str], skipped_lines: int, *, truncated: bool) -> str:
        notes: list[str] = []
        if truncated:
            notes.append("result limit reached; narrow the pattern or glob")
        if skipped_lines:
            notes.append(f"{skipped_lines} over-long line(s) not searched")
        suffix = f"\n({'; '.join(notes)})" if notes else ""
        if not hits:
            return f"no matches{suffix}"
        return f"{len(hits)} match(es)\n{fence(chr(10).join(hits), source='fs_grep')}{suffix}"
