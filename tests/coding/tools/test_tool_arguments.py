"""baldric_agent checks tool-call arguments against the tool's declared schema."""

from collections.abc import Mapping
from typing import Any

import pytest

from baldric_agent.events import MessageEndEvent
from baldric_agent.tool_arguments import argument_problems, invalid_arguments_message
from baldric_agent.tool_calls import execute_tool_call
from baldric_protocol.messages import TextContent, ToolCall, ToolResultMessage
from baldric_protocol.tools import AgentTool, AgentToolResult
from baldric_protocol.types import JSONValue

READ_SCHEMA: dict[str, JSONValue] = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "limit": {"type": "integer"},
        "mode": {"type": "string", "enum": ["text", "bytes"]},
        "ranges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"start": {"type": "integer"}},
                "required": ["start"],
            },
        },
    },
    "required": ["path"],
    "additionalProperties": False,
}


async def _run(
    schema: Mapping[str, JSONValue],
    arguments: dict[str, JSONValue],
    prepare: Any = None,
) -> tuple[bool, str, list[Mapping[str, JSONValue]]]:
    """Run one `read` call with `arguments`; return (is_error, text, what the tool got)."""
    seen: list[Mapping[str, JSONValue]] = []

    async def execute(
        tool_call_id: str,
        args: Mapping[str, JSONValue],
        signal: Any = None,
        on_update: Any = None,
    ) -> AgentToolResult:
        del tool_call_id, signal, on_update
        seen.append(args)
        return AgentToolResult(content=[TextContent(text="ran")], details={})

    tool = AgentTool(
        name="read",
        label="Read",
        description="Read a file.",
        parameters=schema,
        execute_fn=execute,
        prepare_arguments=prepare,
    )
    call = ToolCall(id="call-1", name="read", arguments=arguments)

    result_message: ToolResultMessage | None = None
    events = execute_tool_call(call, {"read": tool}, None, None, None)
    async for event in events:
        if isinstance(event, MessageEndEvent) and isinstance(event.message, ToolResultMessage):
            result_message = event.message
    assert result_message is not None
    text = "".join(block.text for block in result_message.content if isinstance(block, TextContent))
    return result_message.is_error, text, seen


@pytest.mark.anyio
async def test_missing_required_argument_is_refused_before_the_tool_runs() -> None:
    is_error, text, seen = await _run(READ_SCHEMA, {"limit": 5})

    assert seen == []
    assert is_error is True
    assert text == (
        'Invalid arguments for read: missing required "path". Send the call again with these fixed.'
    )


@pytest.mark.anyio
async def test_one_error_lists_every_problem() -> None:
    is_error, text, seen = await _run(
        READ_SCHEMA,
        {"limit": "10", "mode": "lines", "colour": "red", "ranges": [{"start": 1}, {}]},
    )

    assert seen == []
    assert is_error is True
    assert text == (
        "Invalid arguments for read: "
        'missing required "path"; '
        '"limit" must be integer, got string; '
        '"mode" must be one of "text", "bytes", got "lines"; '
        'unknown argument "colour"; '
        'missing required "ranges[1].start". '
        "Send the call again with these fixed."
    )


@pytest.mark.anyio
async def test_valid_arguments_reach_the_tool_unchanged() -> None:
    arguments: dict[str, JSONValue] = {"path": "a.py", "limit": 10.0, "mode": "bytes"}

    is_error, text, seen = await _run(READ_SCHEMA, arguments)

    assert is_error is False
    assert text == "ran"
    assert seen == [arguments]
    assert isinstance(seen[0]["limit"], float)


@pytest.mark.anyio
async def test_a_tool_with_no_schema_is_not_checked() -> None:
    is_error, _, seen = await _run({}, {"anything": [1, "two"], "path": 3})

    assert is_error is False
    assert seen == [{"anything": [1, "two"], "path": 3}]


@pytest.mark.anyio
async def test_unparsed_arguments_are_left_to_the_tool() -> None:
    is_error, _, seen = await _run(READ_SCHEMA, {"_raw_arguments": '{"path": "a.py'})

    assert is_error is False
    assert seen == [{"_raw_arguments": '{"path": "a.py'}]


@pytest.mark.anyio
async def test_prepared_arguments_are_checked_and_reach_the_tool() -> None:
    def prepare(arguments: object) -> Mapping[str, JSONValue]:
        assert isinstance(arguments, Mapping)
        return {"path": arguments["file"]}

    is_error, _, seen = await _run(READ_SCHEMA, {"file": "a.py"}, prepare)

    assert is_error is False
    assert seen == [{"path": "a.py"}]


@pytest.mark.anyio
async def test_a_failing_preparer_refuses_the_call() -> None:
    def prepare(arguments: object) -> Mapping[str, JSONValue]:
        raise ValueError("cannot read these arguments")

    is_error, text, seen = await _run(READ_SCHEMA, {"path": "a.py"}, prepare)

    assert seen == []
    assert is_error is True
    assert "cannot read these arguments" in text


def test_missing_required_and_wrong_type_are_reported() -> None:
    assert argument_problems(READ_SCHEMA, {"limit": 5}) == ['missing required "path"']
    assert argument_problems(READ_SCHEMA, {"path": None}) == ['"path" must be string, got null']
    assert argument_problems(READ_SCHEMA, {"path": "a.py", "limit": True}) == [
        '"limit" must be integer, got boolean'
    ]
    assert argument_problems(READ_SCHEMA, {"path": "a.py", "mode": "pages"}) == [
        '"mode" must be one of "text", "bytes", got "pages"'
    ]


def test_optional_argument_sent_as_null_counts_as_not_sent() -> None:
    assert argument_problems(READ_SCHEMA, {"path": "a.py", "limit": None, "mode": None}) == []


def test_additional_properties_schema_and_type_lists_are_checked() -> None:
    schema: dict[str, JSONValue] = {
        "type": "object",
        "properties": {"limit": {"type": ["integer", "string"]}},
        "additionalProperties": {"type": "integer"},
    }

    assert argument_problems(schema, {"limit": "all", "extra": 1}) == []
    assert argument_problems(schema, {"limit": 1.5, "extra": "x"}) == [
        '"limit" must be integer or string, got number',
        '"extra" must be integer, got string',
    ]


def test_invalid_arguments_message_shape() -> None:
    assert invalid_arguments_message("read", ['missing required "path"']) == (
        'Invalid arguments for read: missing required "path". Send the call again with these fixed.'
    )
