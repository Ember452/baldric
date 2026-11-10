"""Tool-call execution for the agent loop."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from time import monotonic_ns

from baldric.agent.events import (
    AgentEvent,
    MessageEndEvent,
    MessageStartEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    ToolExecutionUpdateEvent,
)
from baldric.agent.tool_arguments import argument_problems, invalid_arguments_message
from baldric.protocol.messages import AssistantMessage, TextContent, ToolCall, ToolResultMessage
from baldric.protocol.provider import CancellationToken
from baldric.protocol.tools import AgentTool, AgentToolResult
from baldric.protocol.types import JSONValue

BeforeToolCall = Callable[[ToolCall], Awaitable[tuple[bool, str | None]]]
AfterToolCall = Callable[
    [ToolCall, AgentToolResult, bool],
    Awaitable[tuple[AgentToolResult, bool]],
]


async def execute_tool_call(
    call: ToolCall,
    tools: Mapping[str, AgentTool],
    signal: CancellationToken | None,
    before_tool_call: BeforeToolCall | None,
    after_tool_call: AfterToolCall | None,
) -> AsyncIterator[AgentEvent]:
    """Execute one validated tool call and emit its full lifecycle."""
    yield ToolExecutionStartEvent(
        tool_call_id=call.id,
        tool_name=call.name,
        args=call.arguments,
    )

    blocked = False
    block_reason: str | None = None
    duration_ms: int | None = None
    if before_tool_call is not None:
        try:
            blocked, block_reason = await before_tool_call(call)
        except Exception as exc:
            # The gate is a safety boundary, so a misbehaving gate (approval UI
            # or extension hook) must fail closed: the call does not run, and
            # the turn does not abort with a stack trace.
            blocked = True
            block_reason = f"Tool gate failed: {type(exc).__name__}: {exc}"

    if blocked:
        result = error_result(block_reason or "Tool execution was blocked")
        is_error = True
    elif signal is not None and signal.is_cancelled():
        result = error_result("Operation aborted")
        is_error = True
    else:
        tool = tools.get(call.name)
        if tool is None:
            result = error_result(f"Tool {call.name} not found")
            is_error = True
        else:
            arguments, problems = checked_arguments(tool, call)
            if problems:
                result = error_result(invalid_arguments_message(call.name, problems))
                is_error = True
            else:
                outcome: list[tuple[AgentToolResult, bool]] = []
                started_ns = monotonic_ns()
                async for update in run_tool(tool, call, arguments, signal, outcome):
                    yield ToolExecutionUpdateEvent(
                        tool_call_id=call.id,
                        tool_name=call.name,
                        args=call.arguments,
                        partial_result=update,
                    )
                # Same boundary Pi reports: the execute step only, not the hooks.
                duration_ms = (monotonic_ns() - started_ns) // 1_000_000
                result, is_error = outcome[0]
                # Pi agent-loop.ts:988: a tool that reports is_error without
                # raising failed on its own terms; keep its content/details.
                if result.is_error:
                    is_error = True

    if after_tool_call is not None:
        try:
            result, is_error = await after_tool_call(call, result, is_error)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - hooks are an isolation boundary
            # Pi agent-loop.ts:1043-1046: a failing after-hook replaces the
            # whole result with an error result; the run continues. Python's
            # CancelledError still propagates: cancellation is not a hook
            # failure.
            result = error_result(str(exc) or type(exc).__name__)
            is_error = True

    yield ToolExecutionEndEvent(
        tool_call_id=call.id,
        tool_name=call.name,
        result=result,
        is_error=is_error,
        duration_ms=duration_ms,
    )
    message = ToolResultMessage(
        tool_call_id=call.id,
        tool_name=call.name,
        content=result.content,
        details=result.details,
        added_tool_names=result.added_tool_names,
        is_error=is_error,
        duration_ms=duration_ms,
    )
    yield MessageStartEvent(message=message)
    yield MessageEndEvent(message=message)


async def fail_truncated_tool_calls(
    assistant: AssistantMessage,
    tool_results: list[ToolResultMessage],
) -> AsyncIterator[AgentEvent]:
    """Report every call of a length-truncated turn without executing it.

    Streamed tool arguments are finalized with a best-effort JSON salvage, so a
    response cut off by the output limit can carry arguments that parse and
    validate but are silently incomplete. None of them are safe to run, and a
    schema check cannot catch the difference, so each call becomes a recoverable
    error the model can re-issue.
    """
    for call in assistant.tool_calls:
        yield ToolExecutionStartEvent(
            tool_call_id=call.id,
            tool_name=call.name,
            args=call.arguments,
        )
        result = error_result(
            f'Tool call "{call.name}" was not executed: the response hit the output token '
            "limit, so its arguments may be truncated. Re-issue the tool call with complete "
            "arguments."
        )
        yield ToolExecutionEndEvent(
            tool_call_id=call.id,
            tool_name=call.name,
            result=result,
            is_error=True,
        )
        message = ToolResultMessage(
            tool_call_id=call.id,
            tool_name=call.name,
            content=result.content,
            details=result.details,
            is_error=True,
        )
        yield MessageStartEvent(message=message)
        yield MessageEndEvent(message=message)
        tool_results.append(message)


def checked_arguments(tool: AgentTool, call: ToolCall) -> tuple[Mapping[str, JSONValue], list[str]]:
    # Arguments that did not parse as JSON arrive as `_raw_arguments` alone,
    # and the tool reports those itself.
    if set(call.arguments) == {"_raw_arguments"}:
        return call.arguments, []
    arguments: Mapping[str, JSONValue] = call.arguments
    if tool.prepare_arguments is not None:
        try:
            arguments = tool.prepare_arguments(call.arguments)
        except Exception as exc:  # noqa: BLE001 - tools are an isolation boundary
            return call.arguments, [str(exc)]
    return arguments, argument_problems(tool.parameters, arguments)


async def run_tool(
    tool: AgentTool,
    call: ToolCall,
    arguments: Mapping[str, JSONValue],
    signal: CancellationToken | None,
    outcome: list[tuple[AgentToolResult, bool]],
) -> AsyncIterator[AgentToolResult]:
    """Run a tool, yielding progress partials as the tool reports them.

    `on_update` is synchronous while only this generator can emit events, so
    partials are handed over through a queue and raced against the tool itself.
    Buffering them until the tool returned made progress events useless to a
    consumer while a long-running tool was still working (issue #382).

    The final `(result, is_error)` pair is appended to `outcome`, since an async
    generator cannot return a value to its consumer.
    """
    queue: asyncio.Queue[AgentToolResult] = asyncio.Queue()
    accepting = True

    def on_update(partial: AgentToolResult) -> None:
        if accepting:
            queue.put_nowait(partial.model_copy(deep=True))

    task = asyncio.ensure_future(tool.execute(call.id, arguments, signal, on_update))
    try:
        while not task.done():
            pending_update = asyncio.ensure_future(queue.get())
            try:
                await asyncio.wait({pending_update, task}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                if not pending_update.done():
                    pending_update.cancel()
            if pending_update.done() and not pending_update.cancelled():
                yield pending_update.result()
    finally:
        # Stop accepting as soon as the tool is done, matching the previous
        # behaviour, and never leave the tool running if the consumer stops
        # early.
        accepting = False
        if not task.done():
            task.cancel()

    # Emit anything the tool reported just before it returned.
    while not queue.empty():
        yield queue.get_nowait()

    try:
        outcome.append((task.result(), False))
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - tools are an isolation boundary
        outcome.append((error_result(str(exc)), True))


def error_result(message: str) -> AgentToolResult:
    return AgentToolResult(content=[TextContent(text=message)], details={})
