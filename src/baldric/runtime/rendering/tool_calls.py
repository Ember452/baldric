"""Terse tool-call formatting shared by the TUI and the print/JSON renderers."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from baldric.protocol.messages import ToolCall
from baldric.protocol.types import JSONValue


def format_tool_call_block(tool_call: ToolCall, *, compact: bool = True, cwd: Path | None = None) -> str:
    """Format a tool call, optionally compacting long bash invocations."""
    invocation = format_tool_call_invocation(tool_call, expanded=not compact, cwd=cwd)
    if tool_call.name == "bash":
        return invocation
    return f"→ {invocation}"


def format_tool_call_invocation(
    tool_call: ToolCall, *, expanded: bool = False, cwd: Path | None = None
) -> str:
    """Format a tool call as a terse human-readable invocation."""
    arguments = tool_call.arguments
    if tool_call.name == "read":
        path = _string_argument(arguments, "path")
        if path is None:
            return _fallback_tool_call_invocation(tool_call)
        return f"read {_display_tool_path(path, cwd)}{_read_line_suffix(arguments)}"
    if tool_call.name == "edit":
        path = _string_argument(arguments, "path")
        if path is None:
            return _fallback_tool_call_invocation(tool_call)
        return f"edit {_display_tool_path(path, cwd)}"
    if tool_call.name == "write":
        path = _string_argument(arguments, "path")
        if path is None:
            return _fallback_tool_call_invocation(tool_call)
        return f"write {path}"
    if tool_call.name == "bash":
        invocation = _format_bash_tool_call_invocation(arguments, compact=not expanded)
        return invocation if invocation is not None else _fallback_tool_call_invocation(tool_call)
    return _fallback_tool_call_invocation(tool_call)


def _format_bash_tool_call_invocation(arguments: dict[str, JSONValue], *, compact: bool) -> str | None:
    command = _string_argument(arguments, "command")
    if command is None:
        return None
    timeout = _number_argument(arguments, "timeout")
    suffix = f" (timeout {timeout:g}s)" if timeout is not None else ""
    if compact:
        description = _string_argument(arguments, "description")
        if description is not None:
            displayed_description = _normalize_bash_description(description)
            if displayed_description:
                return f"→ {displayed_description}{suffix}"
        return f"→ Running shell command{suffix}"
    return f"$ {command}{suffix}"


def _normalize_bash_description(description: str) -> str:
    return " ".join(description.split())


def _read_line_suffix(arguments: dict[str, JSONValue]) -> str:
    offset = _int_argument(arguments, "offset")
    limit = _int_argument(arguments, "limit")
    if offset is None and limit is None:
        return ""
    start = 1 if offset is None else max(1, offset)
    if limit is None:
        return f":{start}-"
    return f":{start}-{start + max(1, limit) - 1}"


FALLBACK_INVOCATION_ARGS_CHARS = 160


def _fallback_tool_call_invocation(tool_call: ToolCall) -> str:
    if tool_call.arguments:
        rendered = str(tool_call.arguments)
        if len(rendered) > FALLBACK_INVOCATION_ARGS_CHARS:
            rendered = rendered[:FALLBACK_INVOCATION_ARGS_CHARS].rstrip() + "…"
        return f"{tool_call.name} {rendered}"
    return tool_call.name


def _string_argument(arguments: dict[str, JSONValue], key: str) -> str | None:
    value = arguments.get(key)
    return value if isinstance(value, str) else None


def _display_tool_path(path: str, cwd: Path | None) -> str:
    """Shorten an absolute file path to a cwd-relative one when it is inside cwd.

    Relative paths and paths outside ``cwd`` are returned unchanged so the
    transcript never renders a misleading ``../..`` chain.
    """
    if cwd is None:
        return path
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        return path
    try:
        return str(candidate.resolve().relative_to(_resolved_cwd(cwd)))
    except (OSError, ValueError):
        return path


@lru_cache(maxsize=8)
def _resolved_cwd(cwd: Path) -> Path:
    """Resolve a working directory once per distinct value (restores call hot)."""
    return cwd.expanduser().resolve()


def _int_argument(arguments: dict[str, JSONValue], key: str) -> int | None:
    value = arguments.get(key)
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _number_argument(arguments: dict[str, JSONValue], key: str) -> int | float | None:
    value = arguments.get(key)
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int | float) else None
