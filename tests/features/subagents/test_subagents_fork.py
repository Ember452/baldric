"""Tests for fork capture: history fidelity, dangling calls, and seeded entries."""

from __future__ import annotations

from types import SimpleNamespace

from baldric.protocol.messages import (
    AssistantMessage,
    TextContent,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)
from baldric.runtime.features.subagents.fork import (
    FORK_FILLER_RESULT,
    capture_fork,
    wrap_fork_task,
)


def _context(messages: object) -> SimpleNamespace:
    return SimpleNamespace(
        system_prompt="You are Baldric.",
        model="some/model",
        provider_name="openai",
        thinking_level="high",
        transcript=tuple(messages or ()),
    )


def test_capture_records_the_parent_state_verbatim() -> None:
    messages = [UserMessage(content="hello"), AssistantMessage(content=[TextContent(text="hi")])]

    capture = capture_fork(_context(messages))

    assert capture.system_prompt == "You are Baldric."
    assert capture.model == "some/model"
    assert capture.provider_name == "openai"
    assert capture.thinking_level == "high"
    assert capture.messages == tuple(messages)


def test_an_unanswered_tool_call_is_closed_with_the_filler() -> None:
    """A dangling tool_use breaks provider requests, so the fork closes it."""
    call = ToolCall(id="call-9", name="agent", arguments={"prompt": "go"})
    capture = capture_fork(_context([UserMessage(content="go"), AssistantMessage(content=[call])]))

    assert [type(message) for message in capture.messages] == [
        UserMessage,
        AssistantMessage,
        ToolResultMessage,
    ]
    closer = capture.messages[-1]
    assert isinstance(closer, ToolResultMessage)
    assert closer.tool_call_id == "call-9"
    assert closer.tool_name == "agent"
    assert closer.text == FORK_FILLER_RESULT


def test_answered_calls_are_not_closed_twice() -> None:
    call = ToolCall(id="call-1", name="bash", arguments={"command": "pwd"})
    messages = [
        AssistantMessage(content=[call]),
        ToolResultMessage(tool_call_id="call-1", tool_name="bash", content="ok"),
    ]

    capture = capture_fork(_context(messages))

    assert len(capture.messages) == 2, "no filler for a call that already has a result"


def test_interleaved_calls_get_their_fillers_in_order() -> None:
    first = ToolCall(id="a", name="read", arguments={"path": "1"})
    second = ToolCall(id="b", name="read", arguments={"path": "2"})
    # `a` is answered, `b` is not. The filler rides immediately after the
    # assistant turn that owns it, so it lands before that turn's existing
    # result - the same interleaving order the host's own repair uses.
    messages = [
        AssistantMessage(content=[first, second]),
        ToolResultMessage(tool_call_id="a", tool_name="read", content="file"),
    ]

    capture = capture_fork(_context(messages))

    assert [type(message).__name__ for message in capture.messages] == [
        "AssistantMessage",
        "ToolResultMessage",
        "ToolResultMessage",
    ]
    assert [message.tool_call_id for message in capture.messages[1:]] == ["b", "a"]


def test_wrap_fork_task_frames_the_prompt_and_notes_isolation() -> None:
    plain = wrap_fork_task("fix the tests")

    assert plain.startswith("<fork_task>")
    assert plain.endswith("</fork_task>")
    assert "fix the tests" in plain
    assert "isolated git worktree" not in plain

    isolated = wrap_fork_task("fix the tests", worktree=True)

    assert "isolated git worktree" in isolated
    assert "absolute paths" in isolated
