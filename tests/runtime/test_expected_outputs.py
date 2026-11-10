"""Golden-file locks on user-visible and wire-visible output.

These files under ``tests/expected/`` are the contract. They only change when
someone deliberately reruns with ``UPDATE_EXPECTED=1`` and reviews the diff.
"""

from __future__ import annotations

from baldric.protocol.messages import AssistantMessage, TextContent, ToolCall, Usage
from tests.helpers.golden import assert_matches_expected

# Only wire-format output is locked here. Rendered terminal output (``--help``,
# rich panels) is intentionally excluded: its wrapping and Unicode width differ
# between platforms, so a committed golden file would fail on the other OS
# without any behavior having changed.


def test_assistant_message_wire_format_is_stable() -> None:
    message = AssistantMessage(
        content=[
            TextContent(text="hello"),
            ToolCall(id="call-1", name="read", arguments={"path": "README.md"}),
        ],
        model="golden-model",
        provider="golden-provider",
        stop_reason="toolUse",
        thinking_level="high",
        usage=Usage(input=10, output=5),
        timestamp=1_700_000_000_000,
    )

    wire = message.model_dump_json(exclude_none=True)
    assert_matches_expected("assistant_message.json", wire + "\n")


def test_tool_result_message_wire_format_is_stable() -> None:
    from baldric.protocol.messages import ToolResultMessage

    message = ToolResultMessage(
        tool_call_id="call-1",
        tool_name="read",
        content=[TextContent(text="file contents")],
        is_error=False,
        duration_ms=180,
        timestamp=1_700_000_000_000,
    )

    wire = message.model_dump_json(exclude_none=True)
    assert_matches_expected("tool_result_message.json", wire + "\n")
