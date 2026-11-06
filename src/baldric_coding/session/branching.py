"""Session-tree branching logic for CodingSession (choices, labels, branch)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from baldric_agent.messages import (
    UserMessage,
)
from baldric_agent.session import (
    BranchSummaryEntry,
    LabelEntry,
)
from baldric_agent.session.entries import SessionEntry
from baldric_coding.session.provider_helpers import (
    _default_thinking_level_for_active_model as _default_thinking_level_for_active_model,
)
from baldric_coding.session.provider_helpers import (
    _state_thinking_level as _state_thinking_level,
)
from baldric_coding.session.tree_helpers import (
    _active_branchable_entry_id as _active_branchable_entry_id,
)
from baldric_coding.session.tree_helpers import (
    _is_branchable_tree_entry as _is_branchable_tree_entry,
)
from baldric_coding.session.tree_helpers import (
    _is_tool_call_tree_entry as _is_tool_call_tree_entry,
)
from baldric_coding.session.tree_helpers import (
    _messages_after_entry_on_active_path as _messages_after_entry_on_active_path,
)
from baldric_coding.session.tree_helpers import (
    _resolved_labels as _resolved_labels,
)
from baldric_coding.session.tree_helpers import (
    _tree_choice_label as _tree_choice_label,
)
from baldric_coding.session.tree_helpers import (
    _tree_layout as _tree_layout,
)

if TYPE_CHECKING:
    from baldric_coding.session.session import CodingSession


TREE_RUNNING_MESSAGE = "Baldric is still working. Press Escape to interrupt before using /tree."


@dataclass(frozen=True, slots=True)
class SessionTreeChoice:
    """One branchable entry in the active session tree."""

    entry_id: str
    label: str
    active: bool = False
    is_tool_call: bool = False
    bookmark_label: str | None = None
    label_timestamp: float | None = None


@dataclass(frozen=True, slots=True)
class SessionTreeBranchResult:
    """Result of moving the active session tree leaf."""

    message: str
    input_prefill: str | None = None


__all__ = ["branch_to_entry", "tree_choices", "set_label", "session_entries"]


async def branch_to_entry(
    session: CodingSession,
    entry_id: str,
    *,
    summarize: bool = False,
    custom_instructions: str | None = None,
    replace_instructions: bool = False,
) -> SessionTreeBranchResult:
    """Move the active leaf to a previous entry, preserving existing history."""
    if session._harness.is_running:
        raise RuntimeError(TREE_RUNNING_MESSAGE)
    await session._flush_pending_message_writes(context=session._diagnostic_context())
    entries = await session._read_session_entries()
    by_id = {entry.id: entry for entry in entries}
    if entry_id not in by_id:
        raise ValueError(f"Unknown session entry: {entry_id}")
    selected_entry = by_id[entry_id]
    if not _is_branchable_tree_entry(selected_entry):
        raise ValueError(f"Session entry cannot be branched from: {entry_id}")

    target_id: str | None = entry_id
    input_prefill: str | None = None
    summary_entry: BranchSummaryEntry | None = None
    if summarize:
        abandoned_messages = _messages_after_entry_on_active_path(
            entries,
            entry_id,
            session._last_parent_id,
        )
        if abandoned_messages:
            generated = await session._summarize_branch_messages(
                abandoned_messages,
                custom_instructions=custom_instructions,
                replace_instructions=replace_instructions,
            )
            summary_entry = BranchSummaryEntry(
                parent_id=entry_id,
                branch_root_id=entry_id,
                summary=generated.text,
                usage=generated.usage,
                provider=generated.provider,
                model=generated.model,
                response_provider=generated.response_provider,
            )
            await session._append_session_entry(summary_entry)
            target_id = summary_entry.id
    elif selected_entry.type == "message" and isinstance(selected_entry.message, UserMessage):
        target_id = selected_entry.parent_id
        input_prefill = selected_entry.message.text

    session._preview_model = None
    session._preview_thinking = None
    session._last_parent_id = target_id

    # Plain navigation is in-memory only. A summary above is the sole write,
    # and becomes the file-order tip when present.
    await session._refresh_persisted_state(leaf_id=target_id)
    history_repair = await session._persist_active_tool_history_repairs()
    if history_repair is None:
        session._harness.replace_messages(session._state.messages)
    session._invalidate_context_usage_cache()
    session._thinking_level = _state_thinking_level(
        session._state,
        default=_default_thinking_level_for_active_model(session),
    )
    session._sync_thinking_level_to_active_model()
    session._refresh_runtime_provider()
    suffix = " with branch summary" if summary_entry is not None else ""
    if history_repair is not None:
        suffix += " and repaired malformed tool history"
    if input_prefill is not None:
        return SessionTreeBranchResult(
            message=f"Branched session before {entry_id}{suffix}.",
            input_prefill=input_prefill,
        )
    return SessionTreeBranchResult(message=f"Branched session at {target_id}{suffix}.")


async def tree_choices(session: CodingSession) -> tuple[SessionTreeChoice, ...]:
    """Return branchable session entries for a tree picker."""
    entries = await session._read_session_entries()
    ordered_entries, branch_indents = _tree_layout(entries)
    labels_by_id, label_timestamps_by_id = _resolved_labels(entries)
    active_choice_id = _active_branchable_entry_id(entries, session._state.active_leaf_id)
    return tuple(
        SessionTreeChoice(
            entry_id=entry.id,
            label=_tree_choice_label(entry, branch_indent=branch_indents.get(entry.id, 0)),
            active=entry.id == active_choice_id,
            is_tool_call=_is_tool_call_tree_entry(entry),
            bookmark_label=labels_by_id.get(entry.id),
            label_timestamp=label_timestamps_by_id.get(entry.id),
        )
        for entry in ordered_entries
        if _is_branchable_tree_entry(entry)
    )


async def set_label(session: CodingSession, target_id: str, label: str | None) -> LabelEntry:
    """Set or clear the bookmark on an existing session entry."""
    if session._harness.is_running:
        raise RuntimeError(TREE_RUNNING_MESSAGE)
    await session._flush_pending_message_writes(context=session._diagnostic_context())
    entries = await session._read_session_entries()
    if target_id not in {entry.id for entry in entries}:
        raise ValueError(f"Unknown session entry: {target_id}")
    normalized = label.strip() if label is not None else ""
    entry = LabelEntry(
        parent_id=session._last_parent_id,
        target_id=target_id,
        label=normalized or None,
    )
    await session._append_session_entry(entry)
    session._last_parent_id = entry.id
    await session._refresh_persisted_state(leaf_id=entry.id)
    return entry


async def session_entries(session: CodingSession) -> tuple[SessionEntry, ...]:
    """Return append-only entries for frontend session inspection."""
    return tuple(await session._read_session_entries())
