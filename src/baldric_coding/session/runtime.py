"""Persistent coding-session wrapper built on AgentHarness."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator, Sequence
from contextlib import suppress
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal

from baldric_agent.events import AgentEndEvent, AgentEvent, MessageEndEvent, ToolExecutionEndEvent
from baldric_agent.messages import (
    AgentMessage,
    AssistantMessage,
    CustomMessage,
    Usage,
    UserMessage,
    sum_usage,
)
from baldric_agent.provider import ModelProvider
from baldric_agent.provider_events import AssistantDoneEvent, AssistantErrorEvent, TextDeltaEvent
from baldric_agent.session import (
    CompactionEntry,
    CustomEntry,
    CustomMessageEntry,
    MessageEntry,
    ModelChangeEntry,
    SessionState,
    ThinkingLevelChangeEntry,
)
from baldric_agent.session.entries import SessionEntry
from baldric_agent.tool_history import ToolHistoryRepair
from baldric_agent.types import JSONValue
from baldric_coding.context.resources import (
    ResourceDiagnostic,
    ResourceError,
)
from baldric_coding.events import (
    AgentSettledEvent,
    AutoRetryEndEvent,
    AutoRetryStartEvent,
    CodingSessionEvent,
    CompactionEndEvent,
    CompactionStartEvent,
    SessionAgentEndEvent,
    SessionInfoChangedEvent,
)
from baldric_coding.observability.diagnostics import (
    AgentCallDiagnosticContext,
    new_agent_call_run_id,
)
from baldric_coding.providers.config import (
    ProviderConfig,
    provider_has_usable_credentials,
)
from baldric_coding.session.branch_summary import summarize_branch_messages_with_model
from baldric_coding.session.compaction.context_window import (
    SUMMARIZATION_SYSTEM_PROMPT,
    build_compaction_summary_prompt,
    summarize_messages_for_compaction,
)
from baldric_coding.session.provider_helpers import (  # noqa: F401
    _coerced_thinking_level as _coerced_thinking_level,
)
from baldric_coding.session.provider_helpers import (
    _configured_inference_provider as _configured_inference_provider,
)
from baldric_coding.session.provider_helpers import (
    _configured_inference_provider_mode as _configured_inference_provider_mode,
)
from baldric_coding.session.provider_helpers import (
    _configured_model_supports_images as _configured_model_supports_images,
)
from baldric_coding.session.provider_helpers import (
    _create_runtime_provider as _create_runtime_provider,
)
from baldric_coding.session.provider_helpers import (
    _default_thinking_level_for_active_model as _default_thinking_level_for_active_model,
)
from baldric_coding.session.provider_helpers import (
    _fallback_session_name as _fallback_session_name,
)
from baldric_coding.session.provider_helpers import (
    _filter_tools as _filter_tools,
)
from baldric_coding.session.provider_helpers import (
    _initial_model_for_config as _initial_model_for_config,
)
from baldric_coding.session.provider_helpers import (
    _initial_thinking_level_for_config as _initial_thinking_level_for_config,
)
from baldric_coding.session.provider_helpers import (
    _preferred_thinking_level_for_model as _preferred_thinking_level_for_model,
)
from baldric_coding.session.provider_helpers import (
    _prepare_provider_selection as _prepare_provider_selection,
)
from baldric_coding.session.provider_helpers import (
    _provider_config_for_name as _provider_config_for_name,
)
from baldric_coding.session.provider_helpers import (
    _runtime_model_for_state as _runtime_model_for_state,
)
from baldric_coding.session.provider_helpers import (
    _sanitize_session_name as _sanitize_session_name,
)
from baldric_coding.session.provider_helpers import (
    _session_inference_provider as _session_inference_provider,
)
from baldric_coding.session.provider_helpers import (
    _session_inference_provider_mode as _session_inference_provider_mode,
)
from baldric_coding.session.provider_helpers import (
    _state_thinking_level as _state_thinking_level,
)
from baldric_coding.session.provider_helpers import (
    _terminal_command_context_message as _terminal_command_context_message,
)
from baldric_coding.session.provider_helpers import (
    _unavailable_thinking_message as _unavailable_thinking_message,
)
from baldric_coding.session.resource_helpers import (  # noqa: F401
    SessionResources as SessionResources,
)
from baldric_coding.session.resource_helpers import (
    TerminalCommandRequest as TerminalCommandRequest,
)
from baldric_coding.session.resource_helpers import (
    _append_prompt_sections as _append_prompt_sections,
)
from baldric_coding.session.resource_helpers import (
    _append_session_entry_sync as _append_session_entry_sync,
)
from baldric_coding.session.resource_helpers import (
    _category_summary as _category_summary,
)
from baldric_coding.session.resource_helpers import (
    _codex_account_id as _codex_account_id,
)
from baldric_coding.session.resource_helpers import (
    _context_file_signatures as _context_file_signatures,
)
from baldric_coding.session.resource_helpers import (
    _custom_prompt_source as _custom_prompt_source,
)
from baldric_coding.session.resource_helpers import (
    _diagnostic_signatures as _diagnostic_signatures,
)
from baldric_coding.session.resource_helpers import (
    _extension_signatures as _extension_signatures,
)
from baldric_coding.session.resource_helpers import (
    _load_session_resources as _load_session_resources,
)
from baldric_coding.session.resource_helpers import (
    _merge_context_files as _merge_context_files,
)
from baldric_coding.session.resource_helpers import (
    _prompt_template_signatures as _prompt_template_signatures,
)
from baldric_coding.session.resource_helpers import (
    _provider_config_or_none as _provider_config_or_none,
)
from baldric_coding.session.resource_helpers import (
    _provider_settings_with_runtime_catalogs as _provider_settings_with_runtime_catalogs,
)
from baldric_coding.session.resource_helpers import (
    _provider_with_runtime_model_catalog as _provider_with_runtime_model_catalog,
)
from baldric_coding.session.resource_helpers import (
    _runtime_model_thinking_defaults as _runtime_model_thinking_defaults,
)
from baldric_coding.session.resource_helpers import (
    _runtime_provider_model_metadata as _runtime_provider_model_metadata,
)
from baldric_coding.session.resource_helpers import (
    _skill_signatures as _skill_signatures,
)
from baldric_coding.session.resource_helpers import (
    _system_prompt_resource_signatures as _system_prompt_resource_signatures,
)
from baldric_coding.session.resource_helpers import (
    _tool_history_repair_plan as _tool_history_repair_plan,
)
from baldric_coding.session.resource_helpers import (
    default_session_path as default_session_path,
)
from baldric_coding.session.resource_helpers import (
    jsonl_session_storage as jsonl_session_storage,
)
from baldric_coding.session.resource_helpers import (
    parse_terminal_command as parse_terminal_command,
)
from baldric_coding.session.tree_helpers import (  # noqa: F401
    _active_branchable_entry_id as _active_branchable_entry_id,
)
from baldric_coding.session.tree_helpers import (
    _custom_message_from_entry as _custom_message_from_entry,
)
from baldric_coding.session.tree_helpers import (
    _detach_missing_parents as _detach_missing_parents,
)
from baldric_coding.session.tree_helpers import (
    _first_recent_context_index as _first_recent_context_index,
)
from baldric_coding.session.tree_helpers import (
    _is_branchable_tree_entry as _is_branchable_tree_entry,
)
from baldric_coding.session.tree_helpers import (
    _is_tool_call_tree_entry as _is_tool_call_tree_entry,
)
from baldric_coding.session.tree_helpers import (
    _last_parent_id_from_state as _last_parent_id_from_state,
)
from baldric_coding.session.tree_helpers import (
    _last_user_message_index as _last_user_message_index,
)
from baldric_coding.session.tree_helpers import (
    _message_text_preview as _message_text_preview,
)
from baldric_coding.session.tree_helpers import (
    _messages_after_entry_on_active_path as _messages_after_entry_on_active_path,
)
from baldric_coding.session.tree_helpers import (
    _next_user_message_index as _next_user_message_index,
)
from baldric_coding.session.tree_helpers import (
    _ordered_tree_entries as _ordered_tree_entries,
)
from baldric_coding.session.tree_helpers import (
    _resolve_export_destination as _resolve_export_destination,
)
from baldric_coding.session.tree_helpers import (
    _resolved_labels as _resolved_labels,
)
from baldric_coding.session.tree_helpers import (
    _session_entry_for_message as _session_entry_for_message,
)
from baldric_coding.session.tree_helpers import (
    _session_export_title as _session_export_title,
)
from baldric_coding.session.tree_helpers import (
    _short_preview as _short_preview,
)
from baldric_coding.session.tree_helpers import (
    _storage_path as _storage_path,
)
from baldric_coding.session.tree_helpers import (
    _tree_branch_indents as _tree_branch_indents,
)
from baldric_coding.session.tree_helpers import (
    _tree_choice_label as _tree_choice_label,
)
from baldric_coding.session.tree_helpers import (
    _tree_entry_title as _tree_entry_title,
)
from baldric_coding.session.tree_helpers import (
    _tree_layout as _tree_layout,
)
from baldric_coding.session.tree_helpers import (
    is_context_overflow_error as is_context_overflow_error,
)
from baldric_coding.session.tree_helpers import (
    is_retryable_huggingface_route_error as is_retryable_huggingface_route_error,
)

if TYPE_CHECKING:
    from baldric_coding.session.session import CodingSession


def _session_module() -> Any:
    import baldric_coding.session.session as session_module

    return session_module


StreamingBehavior = Literal["steer", "follow_up"]
SESSION_NAME_SYSTEM_PROMPT = (
    "You write concise coding-agent session names. Reply with only a short title, "
    "maximum four words, no quotes, no punctuation-only output."
)
TREE_RUNNING_MESSAGE = "Baldric is still working. Press Escape to interrupt before using /tree."


@dataclass(frozen=True, slots=True)
class _PendingMessageWrite:
    """Stable entry retained while a message persistence attempt is retried."""

    message: AgentMessage
    entry: MessageEntry | CustomMessageEntry


@dataclass(frozen=True, slots=True)
class CompactionPlan:
    """Prepared active-context entries for a compaction run."""

    first_kept_entry_id: str
    replaced_entry_count: int
    messages_to_summarize: tuple[AgentMessage, ...]


@dataclass(frozen=True, slots=True)
class _GeneratedSummary:
    """Summary text paired with the provider usage spent producing it."""

    text: str
    usage: Usage | None
    provider: str | None = None
    model: str | None = None
    response_provider: str | None = None


async def prompt(
    session: CodingSession,
    content: str,
    *,
    streaming_behavior: StreamingBehavior | None = None,
    source: Literal["interactive", "extension"] = "interactive",
    custom_type: str | None = None,
    details: dict[str, JSONValue] | None = None,
) -> AsyncGenerator[CodingSessionEvent, None]:
    """Append a user prompt, run the agent, and persist new messages.

    ``custom_type``/``details`` attach custom-message render metadata to the
    appended ``UserMessage`` (used when an extension delivers a custom
    message that starts an idle session's turn). ``source`` marks who
    initiated the turn for the `input` hook (``"extension"`` when an
    extension started it, ``"interactive"`` otherwise).
    """
    context = session._diagnostic_context()
    input_outcome = await session._extension_runtime.run_input_hooks(
        content, source=source, streaming_behavior=streaming_behavior
    )
    if input_outcome.handled:
        if input_outcome.message:
            session._extension_runtime.ui.notify(input_outcome.message)
        return
    content = input_outcome.text
    try:
        expanded_content = session.expand_prompt_text(content)
    except ResourceError:
        raise
    except Exception as exc:
        session._last_diagnostic_log_path = session._diagnostic_logger.log_exception(
            context=context,
            phase="expand_prompt",
            exc=exc,
        )
        raise

    if session._harness.is_running:
        if streaming_behavior == "steer":
            session._harness.steer(expanded_content)
            session_event_0 = session.queue_update_event()
            await session._extension_runtime.emit_event(session_event_0)
            yield session_event_0
            return
        if streaming_behavior == "follow_up":
            session._harness.follow_up(expanded_content)
            session_event_0 = session.queue_update_event()
            await session._extension_runtime.emit_event(session_event_0)
            yield session_event_0
            return
        raise RuntimeError("CodingSession is already running; pass streaming_behavior to queue a message.")

    await session._flush_pending_message_writes(context=context)
    await session._commit_preview()
    await session._refresh_runtime_model_limits()
    async for compaction_event in session._try_auto_compact(
        context=context, phase="auto_compact_before_prompt"
    ):
        yield compaction_event
    # id() values can be reused once earlier message objects are freed.
    session._ended_message_ids.clear()
    session._persisted_message_ids.clear()
    events: AsyncIterator[AgentEvent] | None = None
    settled_event: AgentSettledEvent | None = None
    auto_name_attempted = False
    auto_name_task: asyncio.Task[None] | None = None
    overflow_message: AssistantMessage | None = None
    route_failure_message: AssistantMessage | None = None
    try:
        prompt_message: AgentMessage
        if custom_type is not None:
            prompt_message = CustomMessage(
                custom_type=custom_type,
                content=expanded_content,
                display=True,
                details=details,
            )
        else:
            prompt_message = UserMessage(content=expanded_content)
        events = session._harness.prompt_message(prompt_message)
        session._invalidate_context_usage_cache()
        async for event in events:
            auto_name_message: str | None = None
            if (
                isinstance(event, MessageEndEvent)
                and not auto_name_attempted
                and isinstance(event.message, UserMessage)
            ):
                auto_name_attempted = True
                auto_name_message = event.message.text
            if isinstance(event, ToolExecutionEndEvent):
                session._invalidate_context_usage_cache()
            if (
                isinstance(event, MessageEndEvent)
                and isinstance(event.message, AssistantMessage)
                and event.message.stop_reason == "error"
                and not event.message.is_tool_result_recovery
            ):
                session._last_diagnostic_log_path = session._diagnostic_logger.log_assistant_error(
                    context=context,
                    phase="agent_loop",
                    message=event.message,
                )
                if is_context_overflow_error(event.message):
                    overflow_message = event.message
                elif session._should_auto_failover_huggingface_route(event.message):
                    route_failure_message = event.message
            if isinstance(event, AgentEndEvent):
                yield SessionAgentEndEvent(
                    messages=event.messages,
                    will_retry=(overflow_message is not None or route_failure_message is not None),
                )
            else:
                yield event
            # Frontends have rendered the confirmed, expanded prompt. Name
            # the session alongside the agent's reply instead of delaying
            # the reply's request behind the naming request.
            if auto_name_message is not None:
                auto_name_task = asyncio.create_task(
                    session._try_auto_name_session(auto_name_message, context=context),
                    name="baldric-auto-name-session",
                )
                # Let the naming request start first so provider calls keep
                # a deterministic order.
                await asyncio.sleep(0)
        if overflow_message is not None:
            session_event_1 = CompactionStartEvent(reason="overflow")
            await session._extension_runtime.emit_event(session_event_1)
            yield session_event_1
            compacted = await session._try_overflow_compact(context=context)
            compaction_end = CompactionEndEvent(
                reason="overflow",
                result=None,
                aborted=not compacted,
                will_retry=compacted,
                error_message=None if compacted else "Overflow compaction failed",
            )
            await session._extension_runtime.emit_event(compaction_end)
            yield compaction_end
            if compacted:
                retry_start = AutoRetryStartEvent(
                    attempt=1,
                    max_attempts=1,
                    delay_ms=0,
                    error_message=overflow_message.error_message or "Context overflow",
                )
                await session._extension_runtime.emit_event(retry_start)
                yield retry_start
                events = session._harness.continue_()
                session._invalidate_context_usage_cache()
                overflow_retry_error: str | None = None
                async for retry_event in events:
                    if isinstance(retry_event, ToolExecutionEndEvent):
                        session._invalidate_context_usage_cache()
                    if (
                        isinstance(retry_event, MessageEndEvent)
                        and isinstance(retry_event.message, AssistantMessage)
                        and retry_event.message.stop_reason in {"error", "aborted"}
                        and not retry_event.message.is_tool_result_recovery
                    ):
                        overflow_retry_error = retry_event.message.error_message or "Provider request aborted"
                        if retry_event.message.stop_reason == "error":
                            session._last_diagnostic_log_path = (
                                session._diagnostic_logger.log_assistant_error(
                                    context=context,
                                    phase="agent_loop_retry",
                                    message=retry_event.message,
                                )
                            )
                    if isinstance(retry_event, AgentEndEvent):
                        yield SessionAgentEndEvent(
                            messages=retry_event.messages,
                            will_retry=False,
                        )
                    else:
                        yield retry_event
                session_event_4 = AutoRetryEndEvent(
                    success=overflow_retry_error is None,
                    attempt=1,
                    final_error=overflow_retry_error,
                )
                await session._extension_runtime.emit_event(session_event_4)
                yield session_event_4
        elif route_failure_message is not None:
            async for failover_event in session._run_huggingface_route_failover(context=context):
                yield failover_event
        else:
            async for compaction_event in session._try_auto_compact(
                context=context, phase="auto_compact_after_prompt"
            ):
                yield compaction_event
        if auto_name_task is not None:
            await auto_name_task
    except Exception as exc:
        session._last_diagnostic_log_path = session._diagnostic_logger.log_exception(
            context=context,
            phase="agent_loop",
            exc=exc,
        )
        raise
    finally:
        if auto_name_task is not None and not auto_name_task.done():
            auto_name_task.cancel()
        try:
            await session._reconcile_run_persistence(events, context=context)
        finally:
            if events is not None:
                settled_event = await session._dispatch_agent_settled()
    if settled_event is not None:
        yield settled_event


async def continue_(session: CodingSession) -> AsyncGenerator[CodingSessionEvent, None]:
    """Continue the agent from restored state and persist new messages."""
    context = session._diagnostic_context()
    await session._flush_pending_message_writes(context=context)
    await session._refresh_runtime_model_limits()
    # id() values can be reused once earlier message objects are freed.
    session._ended_message_ids.clear()
    session._persisted_message_ids.clear()
    events: AsyncIterator[AgentEvent] | None = None
    settled_event: AgentSettledEvent | None = None
    route_failure_message: AssistantMessage | None = None
    try:
        events = session._harness.continue_()
        session._invalidate_context_usage_cache()
        async for event in events:
            if isinstance(event, ToolExecutionEndEvent):
                session._invalidate_context_usage_cache()
            if (
                isinstance(event, MessageEndEvent)
                and isinstance(event.message, AssistantMessage)
                and event.message.stop_reason == "error"
                and not event.message.is_tool_result_recovery
            ):
                session._last_diagnostic_log_path = session._diagnostic_logger.log_assistant_error(
                    context=context,
                    phase="agent_loop",
                    message=event.message,
                )
                if session._should_auto_failover_huggingface_route(event.message):
                    route_failure_message = event.message
            if isinstance(event, AgentEndEvent):
                yield SessionAgentEndEvent(
                    messages=event.messages,
                    will_retry=route_failure_message is not None,
                )
            else:
                yield event
        if route_failure_message is not None:
            async for failover_event in session._run_huggingface_route_failover(context=context):
                yield failover_event
        async for compaction_event in session._try_auto_compact(
            context=context, phase="auto_compact_after_continue"
        ):
            yield compaction_event
    except Exception as exc:
        session._last_diagnostic_log_path = session._diagnostic_logger.log_exception(
            context=context,
            phase="agent_loop",
            exc=exc,
        )
        raise
    finally:
        try:
            await session._reconcile_run_persistence(events, context=context)
        finally:
            if events is not None:
                settled_event = await session._dispatch_agent_settled()
    if settled_event is not None:
        yield settled_event


async def _dispatch_agent_settled(session: CodingSession) -> AgentSettledEvent:
    """Dispatch and return the final session event for one started run."""
    event = AgentSettledEvent()
    await session._extension_runtime.emit_event(event)
    return event


def _diagnostic_context(session: CodingSession) -> AgentCallDiagnosticContext:
    return AgentCallDiagnosticContext(
        provider_name=session._provider_name,
        model=session.model,
        cwd=session.cwd,
        session_id=session.session_id,
        run_id=new_agent_call_run_id(),
    )


async def _persist_active_tool_history_repairs(session: CodingSession) -> ToolHistoryRepair | None:
    """Stage or append one complete repair branch for malformed history."""
    plan = _tool_history_repair_plan(
        session._state.messages,
        context_entry_ids=session._state.context_entry_ids,
        entries=session._state.entries,
    )
    if plan is None:
        return None

    parent_id, suffix, repair = plan
    active_model = session._state.model
    active_thinking_level = session._state.thinking_level
    active_entries = session._state.entries
    parent_index = next(
        (index for index, entry in enumerate(active_entries) if entry.id == parent_id),
        -1,
    )
    custom_entries = [
        entry
        for entry in active_entries[parent_index + 1 :]
        if isinstance(entry, CustomEntry) and entry.namespace != "baldric.session-history-repair"
    ]
    staged: list[SessionEntry] = [
        CustomEntry(
            parent_id=parent_id,
            namespace="baldric.session-history-repair",
            data={"version": 1, **repair.diagnostic_data()},
        )
    ]
    parent_id = staged[-1].id
    for message in suffix:
        entry = _session_entry_for_message(parent_id=parent_id, message=message)
        staged.append(entry)
        parent_id = entry.id
    if active_model is not None:
        model_entry = ModelChangeEntry(
            parent_id=parent_id,
            model=active_model,
            provider=session.provider_name,
        )
        staged.append(model_entry)
        parent_id = model_entry.id
    thinking_entry = ThinkingLevelChangeEntry(
        parent_id=parent_id,
        thinking_level=active_thinking_level,
    )
    staged.append(thinking_entry)
    parent_id = thinking_entry.id
    for custom_entry in custom_entries:
        copied_entry = CustomEntry(
            parent_id=parent_id,
            namespace=custom_entry.namespace,
            data=custom_entry.data,
        )
        staged.append(copied_entry)
        parent_id = copied_entry.id
    if session._config.defer_authoritative_writes:
        session._prepared_entries.extend(staged)
        session._last_parent_id = parent_id
        replay_entries = [*session._state.entries, *staged]
        session._state = SessionState.from_entries(replay_entries, leaf_id=parent_id)
    else:
        await session._append_session_batch(staged)
        session._last_parent_id = parent_id
        await session._refresh_persisted_state(leaf_id=parent_id)
    session._harness.replace_messages(session._state.messages)
    session._invalidate_context_usage_cache()
    return repair


def _attach_persistence_listener(session: CodingSession) -> None:
    """(Re-)attach push persistence to the current harness.

    Persistence subscribes to harness events rather than running in the
    event consumer, which the TUI tears down on interrupt.
    """
    if session._persistence_unsubscribe is not None:
        session._persistence_unsubscribe()
        session._persistence_unsubscribe = None
    # Command-only tests construct sessions with stub harnesses.
    subscribe = getattr(session._harness, "subscribe", None)
    if subscribe is not None:
        session._persistence_unsubscribe = subscribe(session._persist_on_message_end)


async def _persist_on_message_end(session: CodingSession, event: AgentEvent) -> None:
    if isinstance(event, MessageEndEvent):
        session._ended_message_ids.add(id(event.message))
        await session._persist_message(event.message)


async def _persist_message(session: CodingSession, message: AgentMessage) -> None:
    """Persist one completed message at the active branch tip, idempotently.

    Message lifecycle events are the durable-message boundary. A stable entry
    id lets a retry recognize an append that reached disk before raising.
    Only retries pay for a full-file read.
    """
    message_id = id(message)
    pending = session._pending_message_writes.get(message_id)
    is_retry = pending is not None
    if pending is None:
        entry = _session_entry_for_message(parent_id=session._last_parent_id, message=message)
        pending = _PendingMessageWrite(message=message, entry=entry)
        session._pending_message_writes[message_id] = pending

    durable_ids = {entry.id for entry in await session._read_session_entries()} if is_retry else frozenset()
    if pending.entry.id not in durable_ids:
        await session._append_session_entry(pending.entry)
    session._last_parent_id = pending.entry.id

    await session._refresh_persisted_state(leaf_id=session._last_parent_id)
    session._persisted_message_ids.add(message_id)
    session._pending_message_writes.pop(message_id, None)
    session._invalidate_context_usage_cache()


async def _reconcile_run_persistence(
    session: CodingSession, events: AsyncIterator[AgentEvent] | None, *, context: AgentCallDiagnosticContext
) -> None:
    """Close a run and retry failed persists still present in the transcript.

    Keyed on message identity, not counts: the loop emits an assistant's
    ``message_end`` before appending it to the transcript. A message whose
    persist and append both failed cannot be retried here; the repair at
    the next run start re-synthesizes and persists its tool result.
    """
    if events is not None:
        aclose = getattr(events, "aclose", None)
        if aclose is not None:
            with suppress(Exception):
                await aclose()
    for message in session._harness.messages:
        message_id = id(message)
        if message_id in session._ended_message_ids and message_id not in session._persisted_message_ids:
            # Runs in a finally: a repeat failure must not mask cancellation.
            try:
                await session._persist_message(message)
            except Exception as exc:  # noqa: BLE001 - preserve cancellation
                session._log_persistence_failure(context=context, exc=exc)
    session._ended_message_ids.clear()
    session._persisted_message_ids.clear()


async def _flush_pending_message_writes(
    session: CodingSession, *, context: AgentCallDiagnosticContext
) -> None:
    """Finish earlier partial writes before another storage-dependent action."""
    harness_message_ids = {id(message) for message in session._harness.messages}
    for pending in tuple(session._pending_message_writes.values()):
        if id(pending.message) not in harness_message_ids:
            session._harness.append_message(pending.message)
            harness_message_ids.add(id(pending.message))
        try:
            await session._persist_message(pending.message)
        except Exception as exc:
            session._log_persistence_failure(context=context, exc=exc)
            raise


def _log_persistence_failure(
    session: CodingSession, *, context: AgentCallDiagnosticContext, exc: BaseException
) -> None:
    with suppress(Exception):
        session._last_diagnostic_log_path = session._diagnostic_logger.log_exception(
            context=context,
            phase="session_persistence_reconcile",
            exc=exc,
        )


def _invalidate_context_usage_cache(session: CodingSession) -> None:
    """Mark context accounting dirty after transcript/system/tool changes."""
    session._context_usage_cache = None


async def _refresh_persisted_state(session: CodingSession, *, leaf_id: str | None) -> None:
    entries = await session._read_session_entries()
    session._state = SessionState.from_entries(entries, leaf_id=leaf_id)
    if session._config.session_id is not None and session._config.session_manager is not None:
        session._config.session_manager.touch_session(
            session._config.session_id,
            model=session.model,
            provider_name=session.provider_name,
            inference_provider=session._inference_provider,
            inference_provider_mode=session._inference_provider_mode,
            preserve_inference_provider=False,
            cwd=session.cwd,
        )


async def _read_session_entries(session: CodingSession) -> list[SessionEntry]:
    """Read stored entries, detaching roots imported from external history."""
    return _detach_missing_parents(await session._config.storage.read_all())


async def _commit_prepared_entries(session: CodingSession) -> None:
    """Durably commit the staged startup/repair batch exactly once."""
    if not session._config.defer_authoritative_writes:
        return
    durable_ids = {entry.id for entry in await session._config.storage.read_all()}
    missing = tuple(entry for entry in session._prepared_entries if entry.id not in durable_ids)
    if missing:
        append_batch = getattr(session._config.storage, "append_batch", None)
        if append_batch is None:
            # Compatibility storage implementations predate the atomic
            # batch contract.  Production storage always takes this path.
            for entry in missing:
                await session._config.storage.append(entry)
        else:
            await append_batch(missing)
    session._pending_initial_entries = ()
    session._prepared_entries.clear()
    session._config = replace(session._config, defer_authoritative_writes=False)
    try:
        if session._config.index_on_first_persist:
            session._index_current_session()
    except Exception as exc:  # index is a rebuildable cache, not authority
        session._record_session_index_diagnostic(exc)


async def _append_session_entry(session: CodingSession, entry: SessionEntry) -> None:
    """Append one durable entry after flushing deferred session metadata."""
    await session._ensure_session_initialized()
    await session._config.storage.append(entry)


async def _append_session_batch(session: CodingSession, entries: Sequence[SessionEntry]) -> None:
    """Append entries as one storage transaction, with legacy fallback."""
    await session._ensure_session_initialized()
    append_batch = getattr(session._config.storage, "append_batch", None)
    if append_batch is None:
        for entry in entries:
            await session._config.storage.append(entry)
        return
    await append_batch(tuple(entries))


async def _ensure_session_initialized(session: CodingSession) -> None:
    if session._config.defer_authoritative_writes and session._prepared_entries:
        await session._commit_prepared_entries()
        return
    if not session._pending_initial_entries:
        return
    await session._write_pending_initial_entries()
    if session._config.index_on_first_persist:
        try:
            session._index_current_session()
        except Exception as exc:
            session._record_session_index_diagnostic(exc)


async def _write_pending_initial_entries(session: CodingSession) -> None:
    durable_ids = {entry.id for entry in await session._config.storage.read_all()}
    missing = tuple(entry for entry in session._pending_initial_entries if entry.id not in durable_ids)
    if missing:
        append_batch = getattr(session._config.storage, "append_batch", None)
        if append_batch is not None:
            await append_batch(missing)
        else:
            for entry in missing:
                await session._config.storage.append(entry)
    session._pending_initial_entries = ()


def _ensure_session_file_initialized(session: CodingSession) -> None:
    if not session._pending_initial_entries:
        return
    for entry in session._pending_initial_entries:
        _append_session_entry_sync(session._config.storage, entry)
    session._pending_initial_entries = ()


def _record_session_index_diagnostic(session: CodingSession, exc: BaseException) -> None:
    session._resource_diagnostics = (
        *session._resource_diagnostics,
        ResourceDiagnostic(
            kind="session-index",
            message=f"Session index needs repair: {type(exc).__name__}",
            severity="warning",
        ),
    )


def _index_current_session(session: CodingSession) -> None:
    if session._config.session_id is None or session._config.session_manager is None:
        return
    existing = session._config.session_manager.get_session(session._config.session_id)
    if existing is not None:
        return
    session._config.session_manager.create_session(
        cwd=session.cwd,
        model=session.model,
        provider_name=session.provider_name,
        inference_provider=session._inference_provider,
        session_id=session._config.session_id,
    )


async def _try_auto_compact(
    session: CodingSession, *, context: AgentCallDiagnosticContext, phase: str
) -> AsyncGenerator[CodingSessionEvent, None]:
    try:
        plan = session._auto_compaction_plan()
    except Exception as exc:  # noqa: BLE001 - automatic compaction must not lose a turn
        session._last_diagnostic_log_path = session._diagnostic_logger.log_exception(
            context=context,
            phase=phase,
            exc=exc,
        )
        return
    if plan is None:
        return
    start_event = CompactionStartEvent(reason="threshold")
    await session._extension_runtime.emit_event(start_event)
    yield start_event
    try:
        await session._run_compaction_plan(plan)
    except Exception as exc:  # noqa: BLE001 - automatic compaction must not lose a turn
        session._last_diagnostic_log_path = session._diagnostic_logger.log_exception(
            context=context,
            phase=phase,
            exc=exc,
        )
        end_event = CompactionEndEvent(
            reason="threshold",
            result=None,
            aborted=True,
            will_retry=False,
            error_message=str(exc) or type(exc).__name__,
        )
    else:
        end_event = CompactionEndEvent(
            reason="threshold",
            result=None,
            aborted=False,
            will_retry=False,
            error_message=None,
        )
    await session._extension_runtime.emit_event(end_event)
    yield end_event


async def _try_overflow_compact(session: CodingSession, *, context: AgentCallDiagnosticContext) -> bool:
    try:
        plan = session._recent_preserving_compaction_plan()
        if plan is None:
            return False
        await session._run_compaction_plan(plan)
        return True
    except Exception as exc:  # noqa: BLE001 - the original overflow remains visible
        session._last_diagnostic_log_path = session._diagnostic_logger.log_exception(
            context=context,
            phase="overflow_compact",
            exc=exc,
        )
        return False


async def _try_auto_name_session(
    session: CodingSession, first_message: str, *, context: AgentCallDiagnosticContext
) -> None:
    bound_session_id = session._config.session_id
    bound_manager = session._config.session_manager
    bound_provider = session._harness.config.provider
    bound_model = session.model
    if not session._should_auto_name_session():
        return
    try:
        title = await session._generate_session_name(
            first_message, provider=bound_provider, model=bound_model
        )
    except Exception as exc:  # noqa: BLE001 - naming must not interrupt the agent turn
        session._last_diagnostic_log_path = session._diagnostic_logger.log_exception(
            context=context,
            phase="auto_name_session",
            exc=exc,
        )
        title = _fallback_session_name(first_message)
    if title is None:
        title = _fallback_session_name(first_message)
    if title is None:
        return
    if session._config.session_id != bound_session_id or session._config.session_manager is not bound_manager:
        # The session was replaced while naming ran; drop the stale result
        # instead of retitling the adopted session.
        return
    persisted = session._persist_session_name(
        title,
        only_if_unnamed=True,
        index_if_missing=False,
    )
    if persisted is not None:
        await session._extension_runtime.emit_event(SessionInfoChangedEvent(name=persisted))


def _should_auto_name_session(session: CodingSession) -> bool:
    if session._config.session_id is None or session._config.session_manager is None:
        return False
    record = session._config.session_manager.get_session(session._config.session_id, cwd=session.cwd)
    if record is not None and record.title:
        return False
    return sum(isinstance(message, UserMessage) for message in session._harness.messages) == 1


async def _generate_session_name(
    session: CodingSession, first_message: str, *, provider: ModelProvider, model: str
) -> str | None:
    prompt = (
        "Create a concise session name for this first user message. "
        "Use at most four words.\n\n"
        f"User message:\n{first_message}"
    )
    text_parts: list[str] = []
    final_text: str | None = None
    async for event in provider.stream_response(
        model=model,
        system=SESSION_NAME_SYSTEM_PROMPT,
        messages=[UserMessage(content=prompt)],
        tools=[],
    ):
        if isinstance(event, TextDeltaEvent):
            text_parts.append(event.delta)
        elif isinstance(event, AssistantDoneEvent):
            final_text = event.message.text
        elif isinstance(event, AssistantErrorEvent):
            raise RuntimeError(f"Session naming failed: {event.error.error_message or event.reason}")
    return _sanitize_session_name(final_text if final_text is not None else "".join(text_parts))


def _provider_is_usable(session: CodingSession, provider: ProviderConfig) -> bool:
    return provider_has_usable_credentials(
        provider,
        credential_reader=session._credential_store,
    )


def _usable_provider_configs(session: CodingSession) -> tuple[ProviderConfig, ...]:
    if session._provider_settings is None:
        return ()
    return tuple(
        provider for provider in session._provider_settings.providers if session._provider_is_usable(provider)
    )


def _auto_compaction_plan(session: CodingSession) -> CompactionPlan | None:
    threshold = session.auto_compact_token_threshold
    if threshold is None or threshold <= 0:
        return None
    if len(session._state.context_entry_ids) < 2:
        return None
    if session.context_token_estimate <= threshold:
        return None
    return session._recent_preserving_compaction_plan()


async def _run_compaction_plan(session: CodingSession, plan: CompactionPlan) -> None:
    tokens_before = session.context_token_estimate
    generated = await session._generate_compaction_summary(plan.messages_to_summarize)
    await session._append_compaction(
        generated.text,
        first_kept_entry_id=plan.first_kept_entry_id,
        tokens_before=tokens_before,
        usage=generated.usage,
        provider=generated.provider,
        model=generated.model,
        response_provider=generated.response_provider,
    )


async def _generate_compaction_summary(
    session: CodingSession, messages: tuple[AgentMessage, ...], *, custom_instructions: str | None = None
) -> _GeneratedSummary:
    prompt = build_compaction_summary_prompt(
        messages,
        custom_instructions=custom_instructions,
    )
    text_parts: list[str] = []
    final_text: str | None = None
    response_usages: list[Usage] = []
    response_provider: str | None = None
    summary_messages: list[AgentMessage] = [UserMessage(content=prompt)]
    async for event in session._harness.config.provider.stream_response(
        model=session.model,
        system=SUMMARIZATION_SYSTEM_PROMPT,
        messages=summary_messages,
        tools=[],
    ):
        if isinstance(event, TextDeltaEvent):
            text_parts.append(event.delta)
        elif isinstance(event, AssistantDoneEvent):
            final_text = event.message.text
            response_usages.append(event.message.usage)
            response_provider = event.message.response_provider
        elif isinstance(event, AssistantErrorEvent):
            raise RuntimeError(
                f"Compaction summarization failed: {event.error.error_message or event.reason}"
            )

    summary = (final_text if final_text is not None else "".join(text_parts)).strip()
    if not summary:
        raise RuntimeError("Compaction summarization returned an empty summary")
    return _GeneratedSummary(
        text=summary,
        usage=sum_usage(response_usages) if response_usages else None,
        provider=session.provider_name,
        model=session.model,
        response_provider=response_provider,
    )


async def _summarize_branch_messages(
    session: CodingSession,
    messages: tuple[AgentMessage, ...],
    *,
    custom_instructions: str | None = None,
    replace_instructions: bool = False,
) -> _GeneratedSummary:
    try:
        result = await summarize_branch_messages_with_model(
            provider=session._harness.config.provider,
            model=session.model,
            messages=messages,
            custom_instructions=custom_instructions,
            replace_instructions=replace_instructions,
        )
    except Exception:
        result = None
    if result is not None:
        summary, usage, response_provider = result
        return _GeneratedSummary(
            text=summary,
            usage=usage,
            provider=session.provider_name,
            model=session.model,
            response_provider=response_provider,
        )
    return _GeneratedSummary(
        text=summarize_messages_for_compaction(messages),
        usage=None,
    )


def _recent_preserving_compaction_plan(session: CodingSession) -> CompactionPlan | None:
    rows = session._active_context_rows()
    if len(rows) < 2:
        return None

    first_kept_index = _first_recent_context_index(
        rows,
        keep_recent_tokens=_session_module().DEFAULT_COMPACTION_KEEP_RECENT_TOKENS,
    )
    if first_kept_index <= 0:
        return None

    if first_kept_index >= len(rows):
        return None

    replaced = rows[:first_kept_index]
    return CompactionPlan(
        first_kept_entry_id=rows[first_kept_index][0],
        replaced_entry_count=len(replaced),
        messages_to_summarize=tuple(message for _entry_id, message in replaced),
    )


def _active_context_rows(session: CodingSession) -> tuple[tuple[str, AgentMessage], ...]:
    return tuple(zip(session._state.context_entry_ids, session._state.messages, strict=True))


async def _append_compaction(
    session: CodingSession,
    summary: str,
    *,
    first_kept_entry_id: str,
    tokens_before: int | None = None,
    usage: Usage | None = None,
    provider: str | None = None,
    model: str | None = None,
    response_provider: str | None = None,
) -> CompactionEntry:
    if first_kept_entry_id not in session._state.context_entry_ids:
        raise ValueError("First kept entry is not in the active context")

    compaction = CompactionEntry(
        parent_id=session._last_parent_id,
        summary=summary,
        first_kept_entry_id=first_kept_entry_id,
        tokens_before=tokens_before,
        usage=usage,
        provider=provider,
        model=model,
        response_provider=response_provider,
    )
    await session._append_session_entry(compaction)
    session._last_parent_id = compaction.id

    await session._refresh_persisted_state(leaf_id=compaction.id)
    session._harness.replace_messages(session._state.messages)
    session._invalidate_context_usage_cache()
    return compaction
