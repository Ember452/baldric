"""Session-management slash commands."""

from __future__ import annotations

from baldric_coding.commands.base import (
    CommandContext,
    CommandKind,
    CommandOutcome,
    CommandResult,
    MessageDisplay,
    PickerKind,
    handled_result,
    message_outcome,
)
from baldric_coding.commands.formatting import _format_session_record
from baldric_coding.session.manager import normalize_session_name


def _resume_command(context: CommandContext) -> CommandResult:
    if not context.args:
        return handled_result(CommandOutcome(kind=CommandKind.OPEN_PICKER, picker=PickerKind.SESSION_RESUME))
    manager = context.session.session_manager
    if manager is None:
        return handled_result(message_outcome("Session manager is not available."))
    session_id = context.args.strip()
    if manager.get_session(session_id) is None:
        return handled_result(message_outcome(f"Unknown session: {session_id}"))
    return handled_result(
        CommandOutcome(
            kind=CommandKind.OPEN_PICKER,
            picker=PickerKind.SESSION_RESUME,
            session_id=session_id,
        )
    )


def _tree_command(context: CommandContext) -> CommandResult:
    if context.args:
        return handled_result(message_outcome("Usage: /tree"))
    return handled_result(CommandOutcome(kind=CommandKind.OPEN_PICKER, picker=PickerKind.TREE))


def _name_command(context: CommandContext) -> CommandResult:
    manager = context.session.session_manager
    session_id = context.session.session_id
    if manager is None or session_id is None:
        return handled_result(message_outcome("Session manager is not available."))

    if not context.args:
        record = manager.get_session(session_id)
        title = (record.title if record is not None else context.session.session_title) or "Untitled session"
        return handled_result(message_outcome(f"Current session name: {title}\nUsage: /name <new name>"))

    try:
        name = _validated_session_name(context.args)
    except ValueError as exc:
        return handled_result(message_outcome(str(exc)))

    # /name reports in the notification strip; the frontend consumes the rename.
    return CommandResult(
        outcome=CommandOutcome(
            kind=CommandKind.SESSION_NAMED,
            message=f"Session renamed: {name}",
            display=MessageDisplay.NOTIFICATION,
            text=name,
        )
    )


def _format_sessions(context: CommandContext) -> str:
    manager = context.session.session_manager
    if manager is None:
        return "Session manager is not available."

    records = manager.list_sessions(context.session.cwd)
    if not records:
        return "No sessions found."

    lines = ["Indexed sessions:"]
    for record in records:
        lines.append(_format_session_record(record))
    return "\n".join(lines)


def _validated_session_name(value: str) -> str:
    if not value.strip():
        raise ValueError("Usage: /name <new name>")
    return normalize_session_name(value)
