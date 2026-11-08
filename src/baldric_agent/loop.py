"""Pure Pi-compatible provider/tool agent loop."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from baldric_agent.assistant_stream import assistant_events
from baldric_agent.context_projection import has_image_tool_results, provider_context
from baldric_agent.events import (
    AgentEndEvent,
    AgentEvent,
    AgentStartEvent,
    MessageEndEvent,
    MessageStartEvent,
    ToolExecutionEndEvent,
    TurnEndEvent,
    TurnStartEvent,
)
from baldric_agent.tool_calls import (
    AfterToolCall,
    BeforeToolCall,
    execute_tool_call,
    fail_truncated_tool_calls,
)
from baldric_protocol.messages import (
    AgentMessage,
    AssistantMessage,
    AssistantMessageDiagnostic,
    ToolResultMessage,
)
from baldric_protocol.provider import CancellationToken, ModelProvider
from baldric_protocol.tools import AgentTool, AgentToolResult

# A model that keeps hitting the output limit on tool calls would otherwise loop
# forever: a truncated turn executes nothing, so the provider-failure counter
# never advances.
MAX_TRUNCATED_TURNS = 3

# Injectable context seams (pi agent-loop.ts:501-510): the transform runs on the
# raw agent messages, then the convert output is what the provider sees. Both
# are synchronous; an awaitable seam waits for a real async need.
ConvertToLlm = Callable[[list[AgentMessage]], list[AgentMessage]]
TransformContext = Callable[[list[AgentMessage]], list[AgentMessage]]


@dataclass(frozen=True, slots=True)
class TurnContext:
    """One completed turn, handed to the turn-boundary hooks (pi AgentTurnContext)."""

    message: AgentMessage
    tool_results: list[ToolResultMessage]
    # The live loop context; hooks may read it freely. Replacement goes through
    # the hook's update value, not by mutating this list mid-turn.
    context: list[AgentMessage]
    new_messages: list[AgentMessage]


@dataclass(frozen=True, slots=True)
class TurnUpdate:
    """Hook-provided replacement state before the next turn (pi AgentLoopTurnUpdate)."""

    # Appended to the context with full message lifecycle events.
    messages: Sequence[AgentMessage] = ()
    # Replaces the model string for this and later requests in the run.
    model: str | None = None


@dataclass(frozen=True, slots=True)
class RequestState:
    """Runtime state right before a provider request (pi PrepareRequestContext)."""

    # The raw loop context (pending messages already appended); the transform
    # and convert seams run after this hook.
    messages: list[AgentMessage]
    model: str


@dataclass(frozen=True, slots=True)
class RequestUpdate:
    """Hook-provided replacement state for the upcoming request (pi AgentRequestUpdate)."""

    # Replaces the raw loop context in place; the request is built from it.
    messages: list[AgentMessage] | None = None
    model: str | None = None


FinishTurn = Callable[[TurnContext], Literal["continue", "end"] | None]
PrepareNextTurn = Callable[[TurnContext], TurnUpdate | None]
PrepareRequest = Callable[[RequestState], RequestUpdate | None]


async def run_agent_loop(
    *,
    provider: ModelProvider,
    model: str,
    system: str,
    messages: list[AgentMessage],
    tools: list[AgentTool],
    prompts: Sequence[AgentMessage] = (),
    prelude_messages: Sequence[AgentMessage] = (),
    max_turns: int | None = None,
    signal: CancellationToken | None = None,
    session_id: str | None = None,
    get_steering_messages: Callable[[], Sequence[AgentMessage]] | None = None,
    get_follow_up_messages: Callable[[], Sequence[AgentMessage]] | None = None,
    before_tool_call: BeforeToolCall | None = None,
    after_tool_call: AfterToolCall | None = None,
    convert_to_llm: ConvertToLlm | None = None,
    transform_context: TransformContext | None = None,
    finish_turn: FinishTurn | None = None,
    prepare_next_turn: PrepareNextTurn | None = None,
    prepare_request: PrepareRequest | None = None,
) -> AsyncIterator[AgentEvent]:
    """Run the provider/tool loop and emit Pi-compatible agent events."""
    new_messages = list(prompts)
    if prompts:
        messages.extend(prompts)

    yield AgentStartEvent()
    yield TurnStartEvent()
    for message in prelude_messages:
        yield MessageStartEvent(message=message)
        yield MessageEndEvent(message=message)
    for prompt in prompts:
        yield MessageStartEvent(message=prompt)
        yield MessageEndEvent(message=prompt)

    if max_turns is not None and max_turns < 1:
        error = error_message(model, "max_turns must be at least 1")
        messages.append(error)
        new_messages.append(error)
        yield MessageStartEvent(message=error)
        yield MessageEndEvent(message=error)
        yield TurnEndEvent(message=error)
        yield AgentEndEvent(messages=new_messages)
        return

    tool_by_name = {tool.name: tool for tool in tools}
    turn = 1
    first_turn = True
    consecutive_errors = 0
    truncated_turns = 0
    pending = tuple(get_steering_messages() if get_steering_messages else ())
    # Error text of the tool call that cancelled the run, e.g. a hook's reason.
    stop_note: str | None = None
    explicit_continuation = False
    last_completed_turn: TurnContext | None = None

    while True:
        has_more_tools = True
        while has_more_tools or pending:
            # Pi agent-loop.ts:250-280: prepare the next turn from the last
            # completed one (never before the first); its messages are held
            # for emission after turn_start. Preparation can run long, so
            # steering queued while it ran is picked up here - but only when
            # the earlier poll came back empty, or one-at-a-time mode would
            # deliver two messages in this turn.
            prepared: list[AgentMessage] = []
            if last_completed_turn is not None and prepare_next_turn is not None:
                update = prepare_next_turn(last_completed_turn)
                if update is not None:
                    prepared = list(update.messages)
                    if update.model is not None:
                        model = update.model
            if last_completed_turn is not None and not pending and get_steering_messages is not None:
                pending = tuple(get_steering_messages())
            if not first_turn:
                yield TurnStartEvent()
            first_turn = False

            for message in (*prepared, *pending):
                messages.append(message)
                new_messages.append(message)
                yield MessageStartEvent(message=message)
                yield MessageEndEvent(message=message)
            pending = ()

            if max_turns is not None and turn > max_turns:
                error = error_message(model, f"Agent stopped after max_turns={max_turns}")
                messages.append(error)
                new_messages.append(error)
                yield MessageStartEvent(message=error)
                yield MessageEndEvent(message=error)
                yield TurnEndEvent(message=error)
                yield AgentEndEvent(messages=new_messages)
                return

            if signal is not None and signal.is_cancelled():
                # A request started after a cancel would fail as a provider error.
                aborted = aborted_message(model, stop_note)
                messages.append(aborted)
                new_messages.append(aborted)
                yield MessageStartEvent(message=aborted)
                yield MessageEndEvent(message=aborted)
                yield TurnEndEvent(message=aborted)
                yield AgentEndEvent(messages=new_messages)
                return

            # Pi agent-loop.ts:295-316: every provider request, including the
            # first, passes prepare_request after the pending messages are on
            # record. A returned context is adopted in place - the loop shares
            # this list object with the harness, so replacing it wholesale
            # would fork durable history.
            if prepare_request is not None:
                request_update = prepare_request(RequestState(messages=messages, model=model))
                if request_update is not None:
                    if request_update.messages is not None:
                        messages[:] = request_update.messages
                    if request_update.model is not None:
                        model = request_update.model

            # Python async generators cannot pass a yielding callback through a
            # normal await cleanly, so consume the assistant sub-generator and
            # retain its final message through the terminal event.
            assistant = None
            # Pi agent-loop.ts:501-510: transform the raw context first, then
            # convert. The default convert is the derived provider projection;
            # an injected convert replaces it wholesale.
            context_messages = list(messages)
            if transform_context is not None:
                context_messages = transform_context(context_messages)
            if convert_to_llm is None:
                context_messages = provider_context(context_messages)
            else:
                context_messages = convert_to_llm(context_messages)
            async for event in assistant_events(
                provider=provider,
                model=model,
                system=system,
                messages=context_messages,
                tools=tools,
                signal=signal,
                session_id=session_id,
            ):
                if (
                    isinstance(event, MessageEndEvent)
                    and isinstance(event.message, AssistantMessage)
                    and event.message.stop_reason == "error"
                    and not event.message.content
                    and consecutive_errors + 1 < 3
                    and (max_turns is None or turn < max_turns)
                    and has_image_tool_results(messages)
                    and not (signal is not None and signal.is_cancelled())
                ):
                    # Mark before message_end: subscribers persist this diagnostic
                    # and frontends must not report a final failure.
                    event.message.diagnostics = [
                        *(event.message.diagnostics or ()),
                        AssistantMessageDiagnostic(type="tool_result_recovery"),
                    ]
                yield event
                if isinstance(event, MessageEndEvent) and isinstance(event.message, AssistantMessage):
                    assistant = event.message

            if assistant is None:  # defensive: assistant_events always terminates
                assistant = error_message(model, "Provider produced no assistant message")
                yield MessageStartEvent(message=assistant)
                yield MessageEndEvent(message=assistant)

            messages.append(assistant)
            new_messages.append(assistant)
            if assistant.stop_reason in {"error", "aborted"}:
                consecutive_errors += 1
                # Pi agent-loop.ts:326-337: error and aborted turns still see
                # finish_turn, but the decision is ignored - they remain hard
                # exits.
                last_completed_turn = TurnContext(
                    message=assistant,
                    tool_results=[],
                    context=messages,
                    new_messages=new_messages,
                )
                if finish_turn is not None:
                    finish_turn(last_completed_turn)
                yield TurnEndEvent(message=assistant)
                if assistant.is_tool_result_recovery:
                    # Replay replaces rejected images with the API error in the
                    # existing tool responses; never rerun side-effecting tools.
                    turn += 1
                    continue
                yield AgentEndEvent(messages=new_messages)
                return

            consecutive_errors = 0

            tool_results: list[ToolResultMessage] = []
            final_tool_results: list[AgentToolResult] = []
            calls = list(assistant.tool_calls)
            if assistant.stop_reason == "length" and calls:
                # A response cut off by the output limit can carry arguments that
                # parse and validate but are silently incomplete, so none of them
                # may run. Report each call as a recoverable error and give the
                # model a bounded number of chances to re-issue complete ones.
                truncated_turns += 1
                async for event in fail_truncated_tool_calls(assistant, tool_results):
                    yield event
                messages.extend(tool_results)
                new_messages.extend(tool_results)
                yield TurnEndEvent(message=assistant, tool_results=tool_results)
                turn += 1
                if truncated_turns >= MAX_TRUNCATED_TURNS:
                    yield AgentEndEvent(messages=new_messages)
                    return
                has_more_tools = True
                pending = tuple(get_steering_messages() if get_steering_messages else ())
                continue

            truncated_turns = 0
            for call in calls:
                cancelled_before = signal is not None and signal.is_cancelled()
                async for event in execute_tool_call(
                    call,
                    tool_by_name,
                    signal,
                    before_tool_call,
                    after_tool_call,
                ):
                    yield event
                    if isinstance(event, ToolExecutionEndEvent):
                        final_tool_results.append(event.result)
                    elif isinstance(event, MessageEndEvent) and isinstance(event.message, ToolResultMessage):
                        tool_results.append(event.message)
                        messages.append(event.message)
                        new_messages.append(event.message)
                        if (
                            stop_note is None
                            and not cancelled_before
                            and signal is not None
                            and signal.is_cancelled()
                            and event.message.is_error
                        ):
                            stop_note = event.message.text or None

            # A tool signals it ended the run with AgentToolResult.terminate; stop
            # asking the model for more turns once every tool result this turn asks
            # to terminate. Keep looping when any tool left `terminate` unset/False.
            has_more_tools = bool(final_tool_results) and not all(
                result.terminate is True for result in final_tool_results
            )
            # Pi agent-loop.ts:366-388: snapshot the turn, let finish_turn
            # decide, then emit turn_end. "end" stops the run without polling
            # queues; "continue" is honored below only when no tool result,
            # steering, or follow-up satisfied the request naturally.
            last_completed_turn = TurnContext(
                message=assistant,
                tool_results=tool_results,
                context=messages,
                new_messages=new_messages,
            )
            decision = finish_turn(last_completed_turn) if finish_turn is not None else None
            yield TurnEndEvent(message=assistant, tool_results=tool_results)
            if decision == "end":
                yield AgentEndEvent(messages=new_messages)
                return
            explicit_continuation = decision == "continue"
            turn += 1
            pending = tuple(get_steering_messages() if get_steering_messages else ())
            if has_more_tools or pending:
                explicit_continuation = False

        follow_ups = tuple(get_follow_up_messages() if get_follow_up_messages else ())
        if follow_ups:
            explicit_continuation = False
            pending = follow_ups
            continue
        # Pi agent-loop.ts:403-408: no natural request is queued, so honor the
        # finish_turn "continue" decision with one context-only extra turn.
        if explicit_continuation:
            explicit_continuation = False
            continue
        break

    yield AgentEndEvent(messages=new_messages)


def error_message(model: str, message: str) -> AssistantMessage:
    return AssistantMessage(
        model=model,
        content=[],
        stop_reason="error",
        error_message=message,
    )


def aborted_message(model: str, reason: str | None) -> AssistantMessage:
    return AssistantMessage(
        model=model,
        content=[],
        stop_reason="aborted",
        error_message=reason or "Operation aborted",
    )
