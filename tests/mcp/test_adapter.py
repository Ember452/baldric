"""Tests for ``baldric_mcp.adapter``: naming, schema, result conversion."""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Callable
from typing import Any

import pytest

from baldric_mcp.adapter import (
    TEXT_LIMIT,
    TOOL_NAME_MAX,
    convert_result,
    create_mcp_tool_name,
    mcp_tool_to_agent_tool,
    normalize_input_schema,
)
from baldric_mcp.client import McpContentBlock, McpToolInfo, McpToolResultData

pytestmark = pytest.mark.anyio


def _info(name: str = "search", description: str | None = None, title: str | None = None) -> McpToolInfo:
    return McpToolInfo(
        name=name,
        description=description if description is not None else "Search documents",
        title=title,
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
    )


async def _call(data: McpToolResultData, seen_progress: list[str] | None = None) -> Callable[..., Any]:
    async def call(
        arguments: dict[str, Any], on_progress: Callable[[str], None] | None = None
    ) -> McpToolResultData:
        if seen_progress is not None and on_progress is not None:
            seen_progress.append("hooked")
            on_progress("Progress 1/2 half")
        return data

    return call


def test_tool_name_plain() -> None:
    assert create_mcp_tool_name("docs", "search") == "mcp__docs__search"


def test_tool_name_sanitizes() -> None:
    assert create_mcp_tool_name("my-server", "do.thing") == "mcp__my_server__do_thing"


def test_tool_name_caps_at_64_with_hash_suffix() -> None:
    long_tool = "t" * 80

    name = create_mcp_tool_name("s", long_tool)

    digest = hashlib.sha256(f"s\0{long_tool}".encode()).hexdigest()[:8]
    assert len(name) == TOOL_NAME_MAX
    # pi: name.slice(0, 64 - 8 - 1) + "_" + digest8 — the slice keeps the first 55 bytes.
    assert name == f"mcp__s__{'t' * 47}_{digest}"


def test_tool_name_colliding_sanitizations_get_distinct_names() -> None:
    base = create_mcp_tool_name("srv", "a-b")
    digest = hashlib.sha256(b"srv\0a_b").hexdigest()[:8]
    clash = create_mcp_tool_name("srv", "a_b", is_taken=lambda candidate: candidate == base)

    assert base == "mcp__srv__a_b"
    assert clash == f"mcp__srv__a_b_{digest}"


def test_normalize_input_schema_falls_back_to_empty_object() -> None:
    empty = {"type": "object", "properties": {}}

    assert normalize_input_schema(None) == empty
    assert normalize_input_schema({}) == empty
    assert normalize_input_schema(["not", "an", "object"]) == empty  # type: ignore[list-item]


def test_normalize_input_schema_keeps_objects() -> None:
    schema = {"type": "object", "properties": {"query": {"type": "string"}}}

    assert normalize_input_schema(schema) == schema


async def test_convert_result_joins_text_blocks() -> None:
    data = McpToolResultData(
        blocks=(McpContentBlock(text="a"), McpContentBlock(text="b")),
        is_error=False,
    )

    result = convert_result("docs", "search", data)

    assert result.content[0].text == "a\nb"
    assert result.is_error is not True


async def test_convert_result_replaces_image_with_placeholder() -> None:
    data = McpToolResultData(
        blocks=(McpContentBlock(image_data=base64.b64encode(b"hello").decode(), image_mime="image/png"),),
        is_error=False,
    )

    result = convert_result("docs", "search", data)

    assert result.content[0].text == "[image: image/png, 5 bytes]"


async def test_convert_result_marks_errors_and_backfills_content() -> None:
    empty_error = McpToolResultData(blocks=(), is_error=True)

    result = convert_result("docs", "search", empty_error)

    assert result.is_error is True
    assert result.content[0].text == "MCP tool docs/search returned an error"


def _long_text() -> str:
    return "x" * (TEXT_LIMIT * 2)


async def test_convert_result_truncates_long_text_with_saver() -> None:
    saved: list[tuple[str, str]] = []

    def saver(full_text: str, suffix: str) -> str:
        saved.append((full_text, suffix))
        return "/tmp/full.txt"

    data = McpToolResultData(blocks=(McpContentBlock(text=_long_text()),), is_error=False)

    result = convert_result("docs", "search", data, output_saver=saver)

    text = result.content[0].text
    assert saved == [(_long_text(), ".txt")]
    assert text.startswith("Warning: truncated output (original token count: ")
    assert "chars truncated…" in text
    assert "[Full output: /tmp/full.txt (read it with offset/limit)]" in text
    assert len(text.encode()) < TEXT_LIMIT * 2


async def test_convert_result_truncates_long_text_without_saver() -> None:
    data = McpToolResultData(blocks=(McpContentBlock(text=_long_text()),), is_error=False)

    result = convert_result("docs", "search", data)

    text = result.content[0].text
    assert "chars truncated…" in text
    assert "Full output" not in text


async def test_mcp_tool_to_agent_tool_shape() -> None:
    tool = mcp_tool_to_agent_tool("docs", _info(), await _call(McpToolResultData(blocks=(), is_error=False)))

    assert tool.name == "mcp__docs__search"
    assert tool.label == "docs/search"
    assert tool.description == "Search documents"
    assert tool.parameters == {"type": "object", "properties": {"query": {"type": "string"}}}


async def test_mcp_tool_to_agent_tool_accepts_an_explicit_name() -> None:
    tool = mcp_tool_to_agent_tool(
        "docs",
        _info(),
        await _call(McpToolResultData(blocks=(), is_error=False)),
        name="mcp__docs__search_0123abcd",
    )

    assert tool.name == "mcp__docs__search_0123abcd"
    assert tool.label == "docs/search"


async def test_description_fallback_chain() -> None:
    call = await _call(McpToolResultData(blocks=(), is_error=False))

    blank = mcp_tool_to_agent_tool("srv", _info(description="   "), call)
    titled = mcp_tool_to_agent_tool("srv", _info(description="", title="Title"), call)
    neither = mcp_tool_to_agent_tool("srv", _info(description="", title=None), call)

    # "   ".strip() is falsy, so the chain continues to title, then the default.
    assert blank.description == "MCP tool search from server srv"
    assert titled.description == "Title"
    assert neither.description == "MCP tool search from server srv"


async def test_executor_maps_progress_and_result() -> None:
    updates: list[object] = []
    seen_progress: list[str] = []
    data = McpToolResultData(blocks=(McpContentBlock(text="done"),), is_error=False)
    tool = mcp_tool_to_agent_tool("docs", _info(), await _call(data, seen_progress))

    result = await tool.execute(
        "call-1",
        {"query": "x"},
        signal=None,
        on_update=updates.append,
    )

    assert seen_progress == ["hooked"]
    assert updates[0].content[0].text == "Progress 1/2 half"  # type: ignore[union-attr]
    assert result.content[0].text == "done"
    assert result.is_error is not True  # success reports nothing (pi: optional isError)
