"""Shared types, constants, and filesystem primitives for built-in tools."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

from baldric.protocol.tools import (
    AgentTool,
    AgentToolResult,
    ToolArgumentPreparer,
    ToolCancellationToken,
    ToolUpdateCallback,
)
from baldric.protocol.types import JSONValue

DEFAULT_MAX_OUTPUT_BYTES = 50 * 1024
DEFAULT_MAX_OUTPUT_LINES = 2_000
IMAGE_SNIFF_BYTES = 64 * 1024
UTF8_BOM = "\ufeff"


class ToolInputError(ValueError):
    """Raised when a tool receives invalid structured arguments."""


def _cut_off_arguments_error(name: str, text: str) -> str:
    """Error for a call whose arguments arrived as unparsed `_raw_arguments`."""
    try:
        json.loads(text)
    except ValueError as exc:
        error = str(exc)
    else:
        error = "not an object of named arguments"
    outcome = f"the {name} tool did not run"
    if name == "write":
        outcome += " and nothing was written"
    return (
        f"The {name} call's arguments are not valid JSON after {len(text)} characters "
        f"({error}), so {outcome}. The reply was probably cut off at the output limit. "
        "Send less per call: write a long file in parts (write the first part, then "
        "append with edit or bash; a second write replaces the file), or generate "
        "repetitive data with a script through bash."
    )


@dataclass(slots=True)
class ImageSupportState:
    """Mutable active-model image capability shared with built-in tools."""

    supported: bool | None = None


@dataclass(frozen=True, slots=True)
class ReadOperations:
    """Pluggable filesystem operations used by the read tool."""

    validate_path: Callable[[Path], None]
    read_bytes: Callable[[Path], bytes]
    size_bytes: Callable[[Path], int] | None = None
    read_prefix: Callable[[Path, int], bytes] | None = None


@dataclass(frozen=True, slots=True)
class TruncationResult:
    """Metadata describing how a tool output was shortened.

    `content` contains the returned slice. The remaining fields record whether
    truncation happened, whether the line or byte limit was responsible, the
    total size of the original output, the size of the returned output, and
    edge cases such as partial-line output or a first line that is too large to
    display safely.
    """

    content: str
    truncated: bool
    truncated_by: str | None
    total_lines: int
    total_bytes: int
    output_lines: int
    output_bytes: int
    last_line_partial: bool
    first_line_exceeds_limit: bool
    max_lines: int
    max_bytes: int

    def to_json(self) -> dict[str, JSONValue]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Complete definition for a coding tool before provider conversion.

    A definition contains the tool name, user-facing description, prompt
    metadata, JSON input schema, and async executor. `to_agent_tool()` converts
    it into the smaller `AgentTool` type consumed by the provider-neutral agent
    loop while preserving prompt metadata for clients that render tool guidance.
    """

    name: str
    description: str
    prompt_snippet: str
    prompt_guidelines: tuple[str, ...]
    input_schema: Mapping[str, JSONValue]
    executor: Callable[[Mapping[str, JSONValue], ToolCancellationToken | None], Awaitable[AgentToolResult]]
    prepare_arguments: ToolArgumentPreparer | None = None

    def to_agent_tool(self) -> AgentTool:
        """Convert the coding definition to the Pi-compatible core tool."""

        async def execute(
            tool_call_id: str,
            arguments: Mapping[str, JSONValue],
            signal: ToolCancellationToken | None = None,
            on_update: ToolUpdateCallback | None = None,
        ) -> AgentToolResult:
            del tool_call_id, on_update
            if set(arguments) == {"_raw_arguments"}:
                raise ToolInputError(_cut_off_arguments_error(self.name, str(arguments["_raw_arguments"])))
            return await self.executor(arguments, signal)

        return AgentTool(
            name=self.name,
            label=self.name,
            description=self.description,
            parameters=self.input_schema,
            execute_fn=execute,
            prompt_snippet=self.prompt_snippet,
            prompt_guidelines=self.prompt_guidelines,
            prepare_arguments=self.prepare_arguments,
        )


_file_locks: dict[Path, asyncio.Lock] = {}


def _str_arg(arguments: Mapping[str, JSONValue], name: str) -> str:
    if name not in arguments:
        sent = ", ".join(f"`{key}`" for key in arguments) or "no arguments"
        raise ToolInputError(
            f"`{name}` is missing (the call sent {sent}); nothing was run. Send the call again with `{name}`."
        )
    value = arguments[name]
    if not isinstance(value, str):
        raise ToolInputError(f"{name} must be a string")
    return value


def _path_arg(arguments: Mapping[str, JSONValue], name: str, *, cwd: Path) -> Path:
    value = _str_arg(arguments, name)
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = cwd / path
    return path


def _optional_int_arg(arguments: Mapping[str, JSONValue], name: str) -> int | None:
    value = arguments.get(name)
    if value is None:
        return None
    if not isinstance(value, int):
        raise ToolInputError(f"{name} must be an integer")
    return value


def _optional_float_arg(arguments: Mapping[str, JSONValue], name: str) -> float | None:
    value = arguments.get(name)
    if value is None:
        return None
    if not isinstance(value, int | float):
        raise ToolInputError(f"{name} must be a number")
    return float(value)


class _FileLockContext:
    def __init__(self, path: Path) -> None:
        self._path = path.resolve()
        self._lock: asyncio.Lock | None = None

    async def __aenter__(self) -> None:
        lock = _file_locks.setdefault(self._path, asyncio.Lock())
        self._lock = lock
        await lock.acquire()

    async def __aexit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        if self._lock is not None:
            self._lock.release()


def _file_lock(path: Path) -> _FileLockContext:
    return _FileLockContext(path)
