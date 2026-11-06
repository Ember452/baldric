"""Read tool implementation."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path

from baldric_agent.messages import ImageContent, TextContent
from baldric_agent.tools import AgentTool, AgentToolResult, ToolCancellationToken
from baldric_agent.types import JSONValue
from baldric_coding.tools.base import (
    DEFAULT_MAX_OUTPUT_BYTES,
    DEFAULT_MAX_OUTPUT_LINES,
    IMAGE_SNIFF_BYTES,
    ImageSupportState,
    ReadOperations,
    ToolDefinition,
    ToolInputError,
    _optional_int_arg,
    _path_arg,
    _str_arg,
)
from baldric_coding.tools.image_processing import (
    DEFAULT_MAX_SOURCE_IMAGE_BYTES,
    ImageProcessingFailure,
    detect_image_family_mime_type,
    detect_supported_image_mime_type,
    process_image,
    unsupported_image_reason,
)
from baldric_coding.tools.output_accumulator import format_size
from baldric_coding.tools.truncate import truncate_head


def _validate_local_read_path(path: Path) -> None:
    if not path.exists():
        raise ToolInputError(f"File not found: {path}")
    if path.is_dir():
        raise ToolInputError(f"Path is a directory: {path}")


def _local_file_size(path: Path) -> int:
    return path.stat().st_size


def _local_read_prefix(path: Path, limit: int) -> bytes:
    with path.open("rb") as file:
        return file.read(limit)


DEFAULT_READ_OPERATIONS = ReadOperations(
    validate_path=_validate_local_read_path,
    read_bytes=Path.read_bytes,
    size_bytes=_local_file_size,
    read_prefix=_local_read_prefix,
)


def create_read_tool_definition(
    *,
    cwd: str | Path | None = None,
    operations: ReadOperations | None = None,
    image_support: ImageSupportState | None = None,
) -> ToolDefinition:
    """Create a definition for the `read` tool.

    The tool reads a file resolved relative to `cwd` unless an absolute path is
    supplied. Text files are decoded as UTF-8 and may be sliced with optional
    1-indexed `offset` and positive integer `limit` arguments. Returned text is
    truncated to `DEFAULT_MAX_OUTPUT_LINES` lines or `DEFAULT_MAX_OUTPUT_BYTES`
    bytes, whichever comes first, and continuation hints are appended when more
    lines remain. Supported images (`jpg`, `png`, `gif`, `webp`, and `bmp`) are
    detected from file content and returned as provider-neutral image blocks.
    Images are validated and resized or converted when needed to fit inline limits.

    The executor raises `ToolInputError` for invalid arguments, missing files,
    directories, and offsets beyond the end of the file. Successful results
    include the resolved path and truncation metadata in `data`.
    """
    root = Path.cwd() if cwd is None else Path(cwd)
    read_operations = operations or DEFAULT_READ_OPERATIONS

    async def execute(
        arguments: Mapping[str, JSONValue],
        signal: ToolCancellationToken | None = None,
    ) -> AgentToolResult:
        del signal
        raw_path = _str_arg(arguments, "path")
        path = _path_arg(arguments, "path", cwd=root)
        offset = _optional_int_arg(arguments, "offset")
        limit = _optional_int_arg(arguments, "limit")

        if offset is not None and offset < 0:
            raise ToolInputError("offset must be at least 0")
        if limit is not None and limit < 1:
            raise ToolInputError("limit must be at least 1")
        read_operations.validate_path(path)
        if read_operations.size_bytes is not None and read_operations.read_prefix is not None:
            source_size = read_operations.size_bytes(path)
            if source_size > DEFAULT_MAX_SOURCE_IMAGE_BYTES:
                prefix = read_operations.read_prefix(path, IMAGE_SNIFF_BYTES)
                image_family = detect_image_family_mime_type(prefix)
                if image_family is not None:
                    reason = unsupported_image_reason(prefix) or (
                        f"source is {format_size(source_size)}, exceeding the "
                        f"{format_size(DEFAULT_MAX_SOURCE_IMAGE_BYTES)} processing limit"
                    )
                    return _omitted_image_result(
                        path=path,
                        source_mime_type=image_family,
                        source_bytes=source_size,
                        reason=reason,
                    )

        data = await asyncio.to_thread(read_operations.read_bytes, path)
        unsupported_reason = unsupported_image_reason(data)
        if unsupported_reason is not None:
            image_family = detect_image_family_mime_type(data)
            assert image_family is not None
            return _omitted_image_result(
                path=path,
                source_mime_type=image_family,
                source_bytes=len(data),
                reason=unsupported_reason,
            )

        source_mime_type = detect_supported_image_mime_type(data)
        if source_mime_type is not None:
            if image_support is not None and image_support.supported is False:
                return _omitted_image_result(
                    path=path,
                    source_mime_type=source_mime_type,
                    source_bytes=len(data),
                    reason=(
                        "current model does not support image input. Image contents are "
                        "unavailable; do not infer or describe them. Ask the user to switch "
                        "to a vision-capable model"
                    ),
                )
            processed = await asyncio.to_thread(process_image, data, source_mime_type)
            image_details: dict[str, JSONValue] = {
                "path": str(path),
                "source_mime_type": source_mime_type,
                "bytes": len(data),
            }
            if isinstance(processed, ImageProcessingFailure):
                return AgentToolResult(
                    content=[
                        TextContent(
                            text=(
                                f"Read image file [{source_mime_type}]\n[Image omitted: {processed.message}.]"
                            )
                        )
                    ],
                    details=image_details,
                )

            image_details.update(
                {
                    "mime_type": processed.mime_type,
                    "processed_bytes": len(processed.data),
                    "width": processed.width,
                    "height": processed.height,
                }
            )
            note_lines = "".join(f"\n[{note}]" for note in processed.notes)
            return AgentToolResult(
                content=[
                    TextContent(text=f"Read image file [{processed.mime_type}]{note_lines}"),
                    ImageContent(data=_base64_text(processed.data), mime_type=processed.mime_type),
                ],
                details=image_details,
            )

        text = data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        all_lines = text.split("\n")
        start_line = 0 if offset is None or offset == 0 else offset - 1
        if start_line >= len(all_lines):
            raise ToolInputError(f"Offset {offset} is beyond end of file ({len(all_lines)} lines total)")

        user_limited_lines: int | None = None
        if limit is not None:
            end_line = min(start_line + limit, len(all_lines))
            selected = "\n".join(all_lines[start_line:end_line])
            user_limited_lines = end_line - start_line
        else:
            selected = "\n".join(all_lines[start_line:])

        truncation = truncate_head(selected)
        start_display = start_line + 1
        details: dict[str, JSONValue] = {"path": str(path), "truncation": truncation.to_json()}

        if truncation.first_line_exceeds_limit:
            first_line_size = format_size(len(all_lines[start_line].encode()))
            output = (
                f"[Line {start_display} is {first_line_size}, exceeds "
                f"{format_size(DEFAULT_MAX_OUTPUT_BYTES)} limit. Use bash: sed -n "
                f"'{start_display}p' {raw_path} | head -c {DEFAULT_MAX_OUTPUT_BYTES}]"
            )
        elif truncation.truncated:
            end_display = start_display + truncation.output_lines - 1
            next_offset = end_display + 1
            output = truncation.content
            if truncation.truncated_by == "lines":
                output += (
                    f"\n\n[Showing lines {start_display}-{end_display} of {len(all_lines)}. "
                    f"Use offset={next_offset} to continue.]"
                )
            else:
                output += (
                    f"\n\n[Showing lines {start_display}-{end_display} of {len(all_lines)} "
                    f"({format_size(DEFAULT_MAX_OUTPUT_BYTES)} limit). "
                    f"Use offset={next_offset} to continue.]"
                )
        elif user_limited_lines is not None and start_line + user_limited_lines < len(all_lines):
            remaining = len(all_lines) - (start_line + user_limited_lines)
            next_offset = start_line + user_limited_lines + 1
            output = (
                f"{truncation.content}\n\n[{remaining} more lines in file. "
                f"Use offset={next_offset} to continue.]"
            )
        else:
            output = truncation.content

        return AgentToolResult(
            content=[TextContent(text=output)],
            details=details,
        )

    return ToolDefinition(
        name="read",
        description=(
            "Read the contents of a file. Supports text files and images "
            "(jpg, png, gif, webp, bmp). "
            "Images are sent to vision-capable models as attachments. For text files, output is "
            "truncated to "
            f"{DEFAULT_MAX_OUTPUT_LINES} lines or {DEFAULT_MAX_OUTPUT_BYTES // 1024}KB "
            "(whichever is hit first). Use offset/limit for large files. When you need the "
            "full file, continue with offset until complete."
        ),
        prompt_snippet="Read file contents",
        prompt_guidelines=("Use read to examine files instead of cat or sed.",),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to read"},
                "offset": {"type": "integer", "description": "Line number to start reading from"},
                "limit": {"type": "integer", "description": "Maximum number of lines to read"},
            },
            "required": ["path"],
        },
        executor=execute,
    )


def _omitted_image_result(
    *,
    path: Path,
    source_mime_type: str,
    source_bytes: int,
    reason: str,
) -> AgentToolResult:
    return AgentToolResult(
        content=[TextContent(text=f"Read image file [{source_mime_type}]\n[Image omitted: {reason}.]")],
        details={
            "path": str(path),
            "source_mime_type": source_mime_type,
            "bytes": source_bytes,
        },
    )


def create_read_tool(
    *,
    cwd: str | Path | None = None,
    operations: ReadOperations | None = None,
    image_support: ImageSupportState | None = None,
) -> AgentTool:
    """Create an `AgentTool` for reading UTF-8 text files and supported images."""
    return create_read_tool_definition(
        cwd=cwd,
        operations=operations,
        image_support=image_support,
    ).to_agent_tool()


def _base64_text(data: bytes) -> str:
    import base64

    return base64.b64encode(data).decode("ascii")
