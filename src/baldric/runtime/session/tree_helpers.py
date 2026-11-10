"""Persistent coding-session wrapper built on AgentHarness."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from baldric.protocol.messages import (
    AgentMessage,
    AssistantMessage,
    CustomMessage,
    UserMessage,
    message_text,
)
from baldric.protocol.session import CustomMessageEntry, LabelEntry, MessageEntry
from baldric.protocol.session.entries import SessionEntry
from baldric.protocol.session.tree import SessionTreeError, path_to_entry
from baldric.runtime.session import SessionState, SessionStorage
from baldric.runtime.session.compaction.context_window import (
    estimate_message_tokens,
)
from baldric.runtime.session.export import (
    default_session_export_artifact_path,
)

if TYPE_CHECKING:
    from baldric.runtime.session.session import CodingSession


def _first_recent_context_index(
    rows: tuple[tuple[str, AgentMessage], ...],
    *,
    keep_recent_tokens: int,
) -> int:
    if keep_recent_tokens <= 0:
        return len(rows)

    accumulated_tokens = 0
    candidate_index: int | None = None
    for index in range(len(rows) - 1, -1, -1):
        _entry_id, message = rows[index]
        accumulated_tokens += estimate_message_tokens(message)
        if accumulated_tokens >= keep_recent_tokens:
            candidate_index = index
            break

    if candidate_index is None:
        return 0

    candidate_message = rows[candidate_index][1]
    if candidate_message.role == "user":
        if candidate_index > 0:
            boundary = candidate_index
        else:
            next_user_index = _next_user_message_index(rows, start=1)
            boundary = next_user_index if next_user_index is not None else 0
    else:
        next_user_index = _next_user_message_index(rows, start=candidate_index + 1)
        if next_user_index is not None:
            boundary = next_user_index
        else:
            for index in range(candidate_index, len(rows)):
                if rows[index][1].role != "toolResult":
                    boundary = index
                    break
            else:
                boundary = len(rows)

    last_user_index = _last_user_message_index(rows)
    if last_user_index is not None:
        boundary = min(boundary, last_user_index)
    return boundary


def _last_user_message_index(
    rows: tuple[tuple[str, AgentMessage], ...],
) -> int | None:
    for index in range(len(rows) - 1, -1, -1):
        if rows[index][1].role == "user":
            return index
    return None


def _next_user_message_index(
    rows: tuple[tuple[str, AgentMessage], ...],
    *,
    start: int,
) -> int | None:
    for index in range(start, len(rows)):
        if rows[index][1].role == "user":
            return index
    return None


def is_context_overflow_error(message: AssistantMessage) -> bool:
    """Return True when an assistant error looks like a context overflow."""
    text = message.error_message or ""
    normalized = text.lower()
    markers = (
        "context length",
        "context window",
        "context limit",
        "maximum context",
        "max context",
        "input is too long",
        "input length",
        "prompt is too long",
        "too many tokens",
        "token limit",
        "exceeds the limit",
        "exceeded the limit",
    )
    return any(marker in normalized for marker in markers)


def is_retryable_huggingface_route_error(message: AssistantMessage) -> bool:
    """Return whether a pre-output Hugging Face HTTP failure is safe to reroute."""
    if message.content:
        return False
    for diagnostic in message.diagnostics or []:
        if diagnostic.type != "provider_error" or diagnostic.details is None:
            continue
        status_code = diagnostic.details.get("status_code")
        if isinstance(status_code, int) and not isinstance(status_code, bool):
            return status_code in {408, 409, 425, 429} or status_code >= 500
    return False


def _session_entry_for_message(
    *, parent_id: str | None, message: AgentMessage
) -> MessageEntry | CustomMessageEntry:
    """Build the canonical persisted entry for one completed runtime message."""
    if isinstance(message, CustomMessage):
        return CustomMessageEntry(
            parent_id=parent_id,
            timestamp=message.timestamp / 1000,
            custom_type=message.custom_type,
            content=message.content,
            display=message.display,
            details=message.details,
        )
    return MessageEntry(parent_id=parent_id, message=message)


def _detach_missing_parents(entries: list[SessionEntry]) -> list[SessionEntry]:
    """Return entries with dangling parent pointers detached from external history."""
    entry_ids = {entry.id for entry in entries}
    return [
        entry.model_copy(update={"parent_id": None})
        if entry.parent_id is not None and entry.parent_id not in entry_ids
        else entry
        for entry in entries
    ]


def _last_parent_id_from_state(state: SessionState) -> str | None:
    if state.active_leaf_id is not None:
        return state.active_leaf_id
    if state.entries:
        return state.entries[-1].id
    return None


def _active_branchable_entry_id(entries: list[SessionEntry], active_leaf_id: str | None) -> str | None:
    if active_leaf_id is None:
        return None
    try:
        path = path_to_entry(entries, active_leaf_id)
    except SessionTreeError:
        return active_leaf_id
    return next((entry.id for entry in reversed(path) if _is_branchable_tree_entry(entry)), None)


def _resolved_labels(entries: list[SessionEntry]) -> tuple[dict[str, str], dict[str, float]]:
    """Resolve the latest label change for every target in storage order."""
    labels: dict[str, str] = {}
    timestamps: dict[str, float] = {}
    for entry in entries:
        if not isinstance(entry, LabelEntry):
            continue
        label = entry.label.strip() if entry.label is not None else ""
        if label:
            labels[entry.target_id] = label
            timestamps[entry.target_id] = entry.timestamp
        else:
            labels.pop(entry.target_id, None)
            timestamps.pop(entry.target_id, None)
    return labels, timestamps


def _is_branchable_tree_entry(entry: SessionEntry) -> bool:
    if entry.type in {"compaction", "branch_summary"}:
        return True
    if entry.type != "message":
        return False
    return isinstance(entry.message, UserMessage | AssistantMessage)


def _tree_choice_label(entry: SessionEntry, *, branch_indent: int = 0) -> str:
    prefix = "  " * branch_indent
    return f"{prefix}{_tree_entry_title(entry)}"


def _tree_branch_indents(entries: list[SessionEntry]) -> dict[str, int]:
    return _tree_layout(entries)[1]


def _ordered_tree_entries(entries: list[SessionEntry]) -> tuple[SessionEntry, ...]:
    return _tree_layout(entries)[0]


def _tree_layout(
    entries: list[SessionEntry],
) -> tuple[tuple[SessionEntry, ...], dict[str, int]]:
    tree_entries = [entry for entry in entries if entry.type != "leaf"]
    children_by_parent: dict[str | None, list[SessionEntry]] = {}
    entries_by_id: dict[str, SessionEntry] = {}
    for entry in tree_entries:
        children_by_parent.setdefault(entry.parent_id, []).append(entry)
        entries_by_id[entry.id] = entry

    # Resolve each child's longest path to a leaf without recursion. Processing
    # leaves upward also keeps deep sessions safe. Malformed cycles retain a
    # finite fallback length and are handled by the traversal's `seen` set.
    branch_lengths = dict.fromkeys(entries_by_id, 1)
    remaining_children = {entry_id: len(children_by_parent.get(entry_id, ())) for entry_id in entries_by_id}
    pending = [entry_id for entry_id, count in remaining_children.items() if count == 0]
    while pending:
        entry_id = pending.pop()
        parent_id = entries_by_id[entry_id].parent_id
        if parent_id not in remaining_children:
            continue
        branch_lengths[parent_id] = max(branch_lengths[parent_id], branch_lengths[entry_id] + 1)
        remaining_children[parent_id] -= 1
        if remaining_children[parent_id] == 0:
            pending.append(parent_id)

    def ordered_children(parent_id: str | None) -> list[SessionEntry]:
        return sorted(
            children_by_parent.get(parent_id, ()),
            key=lambda child: branch_lengths.get(child.id, 1),
            reverse=True,
        )

    ordered: list[SessionEntry] = []
    indents: dict[str, int] = {}
    seen: set[str] = set()

    def child_stack_items(children: list[SessionEntry], parent_indent: int) -> list[tuple[SessionEntry, int]]:
        if not children:
            return []
        main_child, *alternate_children = children
        display_children = [*alternate_children, main_child]
        return [
            (child, parent_indent if child is main_child else parent_indent + 1)
            for child in reversed(display_children)
        ]

    def append_subtrees(children: list[SessionEntry], parent_indent: int) -> None:
        # The longest child is the unindented main branch. Emit shorter siblings
        # immediately after their parent, indented one level, before continuing
        # down the main branch. Stable length sorting preserves storage order
        # when histories have equal lengths.
        stack = child_stack_items(children, parent_indent)
        while stack:
            entry, indent = stack.pop()
            if entry.id in seen:
                continue
            seen.add(entry.id)
            ordered.append(entry)
            indents[entry.id] = indent
            stack.extend(child_stack_items(ordered_children(entry.id), indent))

    append_subtrees(ordered_children(None), 0)
    for entry in tree_entries:
        if entry.id not in seen:
            append_subtrees([entry], 0)
    return tuple(ordered), indents


def _is_tool_call_tree_entry(entry: SessionEntry) -> bool:
    return (
        entry.type == "message"
        and isinstance(entry.message, AssistantMessage)
        and bool(entry.message.tool_calls)
    )


def _tree_entry_title(entry: SessionEntry) -> str:
    match entry.type:
        case "message":
            message = entry.message
            if isinstance(message, AssistantMessage) and message.tool_calls and not message.text.strip():
                tool_names = ", ".join(call.name for call in message.tool_calls)
                return f"tool call: {tool_names}"
            return f"{message.role}: {_message_text_preview(message)}"
        case "custom_message":
            return f"custom: {_short_preview(message_text(_custom_message_from_entry(entry)))}"
        case "compaction":
            return f"compaction summary: {_short_preview(entry.summary)}"
        case "branch_summary":
            return f"branch summary: {_short_preview(entry.summary)}"
        case _:
            return entry.type


def _message_text_preview(message: AgentMessage) -> str:
    return _short_preview(message_text(message))


def _short_preview(text: str, *, limit: int = 72) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized or "(empty)"
    return f"{normalized[: limit - 1]}..."


def _messages_after_entry_on_active_path(
    entries: list[SessionEntry],
    entry_id: str,
    active_leaf_id: str | None,
) -> tuple[AgentMessage, ...]:
    if active_leaf_id is None:
        return ()
    try:
        active_path = path_to_entry(entries, active_leaf_id)
    except SessionTreeError:
        return ()
    try:
        target_index = next(index for index, entry in enumerate(active_path) if entry.id == entry_id)
    except StopIteration:
        return ()
    messages: list[AgentMessage] = []
    for entry in active_path[target_index + 1 :]:
        if entry.type == "message":
            messages.append(entry.message)
        elif entry.type == "custom_message":
            messages.append(_custom_message_from_entry(entry))
    return tuple(messages)


def _custom_message_from_entry(entry: CustomMessageEntry) -> CustomMessage:
    return CustomMessage(
        custom_type=entry.custom_type,
        content=entry.content,
        display=entry.display,
        details=entry.details,
        timestamp=round(entry.timestamp * 1000),
    )


def _storage_path(storage: SessionStorage) -> Path | None:
    path = getattr(storage, "path", None)
    return path if isinstance(path, Path) else None


def _resolve_export_destination(
    destination: Path | None,
    *,
    cwd: Path,
    session_path: Path | None,
    format: str,
) -> Path:
    if destination is None:
        if session_path is not None:
            return default_session_export_artifact_path(
                session_path,
                destination_dir=cwd,
                format=format,
            )
        return cwd / f"baldric-session.{format}"

    resolved = destination if destination.is_absolute() else cwd / destination
    if resolved.suffix:
        return resolved
    name = session_path.stem if session_path is not None else "baldric-session"
    return default_session_export_artifact_path(
        Path(name),
        destination_dir=resolved,
        format=format,
    )


def _session_export_title(session: CodingSession) -> str:
    manager = session.session_manager
    session_id = session.session_id
    if manager is not None and session_id is not None:
        record = manager.get_session(session_id)
        if record is not None and record.title:
            return record.title
    return f"Baldric session {session_id}" if session_id is not None else "Baldric Session Export"
