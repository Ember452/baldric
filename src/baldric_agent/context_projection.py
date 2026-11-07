"""Derived model context and the image-recovery probe."""

from __future__ import annotations

from baldric_agent.messages import (
    AgentMessage,
    AssistantMessage,
    BashExecutionMessage,
    ImageContent,
    TextContent,
    ToolResultMessage,
    UserMessage,
    bash_execution_text,
)
from baldric_agent.tool_history import repair_tool_history


def provider_context(messages: list[AgentMessage]) -> list[AgentMessage]:
    """Return replayable messages while retaining failures in durable history.

    Providers cannot consistently accept an assistant turn with no content. Baldric
    persists terminal failures for diagnostics, but an empty failed or aborted
    turn is not model context and must not poison the next request. After an
    image-bearing tool batch fails, replay its results as text-only API errors.
    Deriving this projection from history keeps JSONL replay safe without
    modifying the original attachments or emitting duplicate tool responses.
    """
    replayable: list[AgentMessage] = []
    image_results: list[tuple[int, ToolResultMessage]] = []
    for message in messages:
        if isinstance(message, AssistantMessage):
            if not message.content and message.stop_reason in {"error", "aborted"}:
                if message.stop_reason == "error":
                    for index, original in image_results:
                        replayable[index] = original.model_copy(
                            update={
                                "content": [
                                    block for block in original.content if not isinstance(block, ImageContent)
                                ]
                                + [
                                    TextContent(
                                        text=(
                                            "Image omitted because the provider rejected the "
                                            "request. API error: "
                                            f"{message.error_message or 'Unknown provider error'}"
                                            "\nTry a smaller image or another approach."
                                        )
                                    )
                                ],
                                "is_error": True,
                            }
                        )
                else:
                    image_results = []
                continue
            image_results = []
        elif isinstance(message, BashExecutionMessage):
            # A bash execution is its own durable message (pi parity) but the
            # provider sees plain text, and `exclude_from_context` keeps it out of
            # the request entirely while staying in the transcript.
            if not message.exclude_from_context:
                replayable.append(
                    UserMessage(
                        content=bash_execution_text(message),
                        timestamp=message.timestamp,
                    )
                )
            image_results = []
            continue
        elif isinstance(message, ToolResultMessage):
            if any(isinstance(block, ImageContent) for block in message.content):
                image_results.append((len(replayable), message))
        else:
            image_results = []
        replayable.append(message)
    return list(repair_tool_history(tuple(replayable)).messages)


def has_image_tool_results(messages: list[AgentMessage]) -> bool:
    """Check the latest tool batch, including its empty failed requests."""
    for message in reversed(messages):
        if isinstance(message, ToolResultMessage):
            if any(isinstance(block, ImageContent) for block in message.content):
                return True
        elif not (
            isinstance(message, AssistantMessage) and message.stop_reason == "error" and not message.content
        ):
            break
    return False
