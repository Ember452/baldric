"""Translate Baldric's transitional provider parser output into Pi stream events."""

from __future__ import annotations

from collections.abc import AsyncIterator

from baldric.ai._provider_events import (
    ProviderErrorEvent,
    ProviderEvent,
    ProviderResponseEndEvent,
    ProviderResponseStartEvent,
    ProviderRetryEvent,
    ProviderTextDeltaEvent,
    ProviderThinkingDeltaEvent,
    ProviderToolCallDeltaEvent,
    ProviderToolCallEvent,
    ProviderToolCallStartEvent,
)
from baldric.ai.events import (
    AssistantDoneEvent,
    AssistantErrorEvent,
    AssistantMessageEvent,
    AssistantRetryEvent,
    AssistantStartEvent,
    TextDeltaEvent,
    TextEndEvent,
    TextStartEvent,
    ThinkingDeltaEvent,
    ThinkingEndEvent,
    ThinkingStartEvent,
    ToolCallDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
)
from baldric.protocol.messages import (
    AssistantMessage,
    AssistantMessageDiagnostic,
    TextContent,
    ThinkingContent,
    ToolCall,
    Usage,
)
from baldric.protocol.types import JSONValue


def _snapshot(message: AssistantMessage) -> AssistantMessage:
    return message.model_copy(deep=True)


# Retry diagnostics are persisted with the assistant message, so an HTTP error
# body must be bounded before it reaches durable history.
_PROVIDER_DIAGNOSTIC_MAX_TEXT_LENGTH = 500


def _truncate_diagnostic_data(data: dict[str, JSONValue]) -> dict[str, JSONValue]:
    """Bound the text fields of provider retry details for durable diagnostics."""
    return {
        key: (
            value[:_PROVIDER_DIAGNOSTIC_MAX_TEXT_LENGTH]
            if isinstance(value, str) and len(value) > _PROVIDER_DIAGNOSTIC_MAX_TEXT_LENGTH
            else value
        )
        for key, value in data.items()
    }


def _retry_diagnostic(event: ProviderRetryEvent) -> AssistantMessageDiagnostic | None:
    """Turn a retry event's provider details into a message diagnostic."""
    if event.data is None:
        return None
    return AssistantMessageDiagnostic(
        type="provider_retry",
        details=_truncate_diagnostic_data(event.data),
    )


def _partial_tool_call(index: int) -> ToolCall:
    """A placeholder block while a tool call's arguments are still streaming."""
    return ToolCall(id=f"tool-call-{index}", name="", arguments={})


async def _end_active_block(
    partial: AssistantMessage,
    index: int | None,
) -> AsyncIterator[AssistantMessageEvent]:
    """End the active text/thinking block before the provider changes channels."""
    if index is None:
        return
    block = partial.content[index]
    if isinstance(block, TextContent):
        yield TextEndEvent(
            content_index=index,
            content=block.text,
            partial=_snapshot(partial),
        )
    elif isinstance(block, ThinkingContent):
        yield ThinkingEndEvent(
            content_index=index,
            content=block.thinking,
            partial=_snapshot(partial),
        )


def _copy_replay_metadata(target: AssistantMessage, source: AssistantMessage) -> None:
    """Copy provider metadata onto streamed blocks without changing their order."""
    source_thinking = [block for block in source.content if isinstance(block, ThinkingContent)]
    target_thinking = [block for block in target.content if isinstance(block, ThinkingContent)]
    for target_block, source_block in zip(target_thinking, source_thinking, strict=False):
        target_block.thinking_signature = source_block.thinking_signature
        target_block.redacted = source_block.redacted

    source_text = [block for block in source.content if isinstance(block, TextContent)]
    target_text = [block for block in target.content if isinstance(block, TextContent)]
    for target_text_block, source_text_block in zip(target_text, source_text, strict=False):
        target_text_block.text_signature = source_text_block.text_signature


def _finish_reason(value: str | None, *, has_tools: bool) -> str:
    if has_tools or value in {"tool_calls", "tool_use", "toolUse"}:
        return "toolUse"
    if value in {"length", "max_tokens", "MAX_TOKENS", "incomplete"}:
        return "length"
    return "stop"


async def canonicalize_provider_stream(
    source: AsyncIterator[ProviderEvent],
    *,
    api: str,
    provider: str,
    model: str,
    thinking_level: str | None = None,
    independent_channels: bool = False,
) -> AsyncIterator[AssistantMessageEvent]:
    """Canonicalize one old internal parser stream.

    Provider parsers remain isolated behind this private bridge while they are
    migrated incrementally. The public provider protocol exposes only Pi events.
    Chat Completions uses independent channels: a channel switch does not end
    either block. Other transports preserve their sequential block ordering.
    """
    partial = AssistantMessage(api=api, provider=provider, model=model, thinking_level=thinking_level)
    active_index: int | None = None
    active_kind: str | None = None
    channel_indices: dict[str, int] = {}
    started = False
    terminal = False
    open_tool_blocks: dict[int, int] = {}
    open_tool_order: list[int] = []
    tool_arg_buffers: dict[int, str] = {}
    retry_diagnostics: list[AssistantMessageDiagnostic] = []

    async for event in source:
        if isinstance(event, ProviderRetryEvent):
            # Surface the retry so a frontend can show it instead of a hang; the
            # agent layer turns this into a provider_retry event. The public retry
            # events have no details slot, so attach the provider's status/body to
            # the diagnostics path instead (same mechanism as ProviderErrorEvent).
            diagnostic = _retry_diagnostic(event)
            if diagnostic is not None:
                retry_diagnostics.append(diagnostic)
                partial.diagnostics = list(retry_diagnostics)
            yield AssistantRetryEvent(
                attempt=event.attempt,
                max_attempts=event.max_attempts,
                delay_ms=int(round(event.delay_seconds * 1000)),
                message=event.message,
            )
            continue
        if isinstance(event, ProviderResponseStartEvent):
            if event.response_provider is not None:
                partial.response_provider = event.response_provider
            if not started:
                started = True
                yield AssistantStartEvent(partial=_snapshot(partial))
            continue
        if not started:
            started = True
            yield AssistantStartEvent(partial=_snapshot(partial))

        if isinstance(event, ProviderTextDeltaEvent):
            if independent_channels:
                active_index = channel_indices.get("text")
                active_kind = "text" if active_index is not None else None
            if active_kind != "text":
                if not independent_channels:
                    async for end_event in _end_active_block(partial, active_index):
                        yield end_event
                active_index = len(partial.content)
                active_kind = "text"
                partial.content.append(TextContent(text=""))
                channel_indices["text"] = active_index
                yield TextStartEvent(content_index=active_index, partial=_snapshot(partial))
            assert active_index is not None
            block = partial.content[active_index]
            assert isinstance(block, TextContent)
            block.text += event.delta
            yield TextDeltaEvent(
                content_index=active_index,
                delta=event.delta,
                partial=_snapshot(partial),
            )
        elif isinstance(event, ProviderThinkingDeltaEvent):
            if independent_channels:
                active_index = channel_indices.get("thinking")
                active_kind = "thinking" if active_index is not None else None
            if active_kind != "thinking":
                if not independent_channels:
                    async for end_event in _end_active_block(partial, active_index):
                        yield end_event
                active_index = len(partial.content)
                active_kind = "thinking"
                partial.content.append(ThinkingContent(thinking=""))
                channel_indices["thinking"] = active_index
                yield ThinkingStartEvent(
                    content_index=active_index,
                    partial=_snapshot(partial),
                )
            assert active_index is not None
            block = partial.content[active_index]
            assert isinstance(block, ThinkingContent)
            block.thinking += event.delta
            yield ThinkingDeltaEvent(
                content_index=active_index,
                delta=event.delta,
                partial=_snapshot(partial),
            )
        elif isinstance(event, ProviderToolCallStartEvent):
            indices = list(channel_indices.values()) if independent_channels else [active_index]
            for index in indices:
                async for end_event in _end_active_block(partial, index):
                    yield end_event
            channel_indices.clear()
            active_index = None
            active_kind = None
            if event.index not in open_tool_blocks:
                content_index = len(partial.content)
                partial.content.append(_partial_tool_call(event.index))
                open_tool_blocks[event.index] = content_index
                open_tool_order.append(event.index)
                yield ToolCallStartEvent(content_index=content_index, partial=_snapshot(partial))
        elif isinstance(event, ProviderToolCallDeltaEvent):
            if event.index not in open_tool_blocks:
                indices = list(channel_indices.values()) if independent_channels else [active_index]
                for index in indices:
                    async for end_event in _end_active_block(partial, index):
                        yield end_event
                channel_indices.clear()
                active_index = None
                active_kind = None
                content_index = len(partial.content)
                partial.content.append(_partial_tool_call(event.index))
                open_tool_blocks[event.index] = content_index
                open_tool_order.append(event.index)
                yield ToolCallStartEvent(content_index=content_index, partial=_snapshot(partial))
            tool_arg_buffers[event.index] = tool_arg_buffers.get(event.index, "") + event.delta
            yield ToolCallDeltaEvent(
                content_index=open_tool_blocks[event.index],
                delta=event.delta,
                partial=_snapshot(partial),
            )
        elif isinstance(event, ProviderToolCallEvent):
            indices = list(channel_indices.values()) if independent_channels else [active_index]
            for index in indices:
                async for end_event in _end_active_block(partial, index):
                    yield end_event
            channel_indices.clear()
            active_index = None
            active_kind = None
            # Pair the completion with the block opened for the same stream
            # index. Providers that stream arguments always carry the index, so
            # this is exact even when completions arrive out of start order or
            # when a sibling call never streamed (delta-less). A completion
            # without an index (complete-only providers) is self-contained and
            # must never displace an already-open placeholder.
            index = event.index
            paired_content_index = open_tool_blocks.pop(index, None) if index is not None else None
            if index is not None and paired_content_index is not None:
                open_tool_order.remove(index)
                tool_arg_buffers.pop(index, None)
                partial.content[paired_content_index] = event.tool_call.model_copy(deep=True)
                yield ToolCallEndEvent(
                    content_index=paired_content_index,
                    tool_call=event.tool_call,
                    partial=_snapshot(partial),
                )
            else:
                content_index = len(partial.content)
                partial.content.append(event.tool_call.model_copy(deep=True))
                yield ToolCallStartEvent(content_index=content_index, partial=_snapshot(partial))
                yield ToolCallEndEvent(
                    content_index=content_index,
                    tool_call=event.tool_call,
                    partial=_snapshot(partial),
                )
        elif isinstance(event, ProviderResponseEndEvent):
            indices = list(channel_indices.values()) if independent_channels else [active_index]
            for index in indices:
                async for end_event in _end_active_block(partial, index):
                    yield end_event
            channel_indices.clear()
            active_index = None
            active_kind = None

            # Preserve the exact streamed content order. The parser's final
            # message remains authoritative only for response metadata/usage.
            final = event.message.model_copy(deep=True)
            final.api = api
            final.provider = provider
            final.model = model
            final.thinking_level = thinking_level
            final.response_provider = event.message.response_provider or partial.response_provider
            final.content = [block.model_copy(deep=True) for block in partial.content]
            if not final.content and event.message.content:
                final.content = [block.model_copy(deep=True) for block in event.message.content]
            if retry_diagnostics:
                final.diagnostics = [*(final.diagnostics or []), *retry_diagnostics]
            _copy_replay_metadata(final, event.message)
            final.stop_reason = _finish_reason(
                event.finish_reason,
                has_tools=bool(final.tool_calls),
            )  # type: ignore[assignment]
            yield AssistantDoneEvent(reason=final.stop_reason, message=final)  # type: ignore[arg-type]
            terminal = True
        elif isinstance(event, ProviderErrorEvent):
            error = partial.model_copy(deep=True)
            error.response_provider = event.response_provider or partial.response_provider
            error.stop_reason = "error"
            error.error_message = event.message
            error.diagnostics = [
                AssistantMessageDiagnostic(type="provider_error", details=event.data),
                *retry_diagnostics,
            ]
            yield AssistantErrorEvent(reason="error", error=error)
            terminal = True

    if not started:
        yield AssistantStartEvent(partial=_snapshot(partial))
    if not terminal:
        error = partial.model_copy(deep=True)
        error.stop_reason = "error"
        error.error_message = "Provider stream ended without a terminal event"
        error.usage = Usage()
        error.diagnostics = list(retry_diagnostics) or None
        yield AssistantErrorEvent(reason="error", error=error)
