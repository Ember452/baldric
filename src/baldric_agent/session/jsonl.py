"""JSONL serialization and Baldric-v1 persisted-session migration."""

from __future__ import annotations

import json
import types
from typing import Annotated, Any, TypeAliasType, Union, get_args, get_origin

from pydantic import BaseModel, TypeAdapter, ValidationError

from baldric_agent.session.entries import (
    CURRENT_SCHEMA_VERSION,
    SESSION_ENTRY_MODELS,
    SessionEntry,
)

_SESSION_ENTRY_ADAPTER: TypeAdapter[SessionEntry] = TypeAdapter(SessionEntry)

_KNOWN_ENTRY_TYPES: frozenset[str] = frozenset(
    model.model_fields["type"].default for model in SESSION_ENTRY_MODELS
)

# Union members carry their tag in one of these fields; `AgentMessage` uses
# `role`, every content block and entry uses `type`.
_TAG_FIELDS = ("type", "role")


class SessionJsonlError(ValueError):
    """Raised when a session JSONL line cannot be decoded."""


class SessionVersionError(SessionJsonlError):
    """Raised when a transcript needs a schema version this build cannot read.

    The message names both versions so the failure is actionable: the session was
    written by a build that knows a shape this one does not, or by a future build
    altogether. Refusing to open with a clear error is deliberate; silently
    dropping entries would corrupt the branch that resumes from them.
    """


def entry_to_json_line(entry: SessionEntry) -> str:
    """Serialize one entry in Baldric's canonical persisted shape."""
    return _SESSION_ENTRY_ADAPTER.dump_json(entry, exclude_none=True).decode() + "\n"


def entry_from_json_line(line: str, *, line_number: int | None = None) -> SessionEntry:
    """Deserialize one entry, migrating persisted Baldric-v1 messages first."""
    location = f" on line {line_number}" if line_number is not None else ""
    try:
        payload = json.loads(line)
        migrated = _migrate_session_entry(payload, legacy_label_target_id=None)
        return _stored_entry(migrated, location=location)
    except SessionVersionError:
        raise
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        raise SessionJsonlError(f"Invalid session entry{location}: {exc}") from exc


def entries_from_json_lines(lines: list[str]) -> list[SessionEntry]:
    """Deserialize non-empty JSONL lines in order.

    Legacy session-level labels had no target. They deterministically become a
    bookmark on the earliest branchable entry, preserving the old value without
    conflating bookmarks with ``SessionInfoEntry.title``. If the transcript has
    no branchable entry, the earliest ordinary entry is used instead.
    """
    decoded: list[tuple[int, Any]] = []
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            decoded.append((index, json.loads(line)))
        except json.JSONDecodeError as exc:
            raise SessionJsonlError(f"Invalid session entry on line {index}: {exc}") from exc

    legacy_target_id = _legacy_label_target_id([value for _line, value in decoded])
    entries: list[SessionEntry] = []
    for line_number, value in decoded:
        location = f" on line {line_number}"
        try:
            migrated = _migrate_session_entry(value, legacy_label_target_id=legacy_target_id)
            entries.append(_stored_entry(migrated, location=location))
        except SessionVersionError:
            raise
        except (ValidationError, TypeError, ValueError) as exc:
            raise SessionJsonlError(f"Invalid session entry{location}: {exc}") from exc
    return entries


def entries_from_transcript(text: str) -> tuple[list[SessionEntry], bool]:
    """Parse a transcript, tolerating only an incomplete final line.

    A process killed mid-append can leave a partial last line. Dropping it is
    safe because it was never a record; corruption anywhere else is not. The
    second value reports whether a line was dropped so the caller can log it.
    """
    lines = text.split("\n")
    has_unterminated_tail = bool(lines) and bool(lines[-1].strip())
    try:
        return entries_from_json_lines(lines), False
    except SessionJsonlError:
        if not has_unterminated_tail:
            raise
    try:
        return entries_from_json_lines(lines[:-1]), True
    except SessionJsonlError:
        raise


def _migrate_session_entry(value: Any, *, legacy_label_target_id: str | None) -> Any:
    """Return a canonical copy of one decoded persisted entry.

    The extension API may break in lockstep, but user session history must not.
    Migration is intentionally confined to this persistence boundary so runtime
    models and extension-facing constructors retain one strict protocol.
    """
    if not isinstance(value, dict):
        return value
    if value.get("type") == "label" and "target_id" not in value:
        migrated = dict(value)
        migrated["target_id"] = legacy_label_target_id or value.get("parent_id") or value.get("id")
        return migrated
    if value.get("type") == "custom_message":
        migrated = dict(value)
        if "customType" in migrated:
            migrated.setdefault("custom_type", migrated["customType"])
            migrated.pop("customType")
        return migrated
    if value.get("type") != "message":
        return value

    migrated = dict(value)
    message = _migrate_message(value.get("message"))
    if isinstance(message, dict) and message.get("role") == "custom":
        message_timestamp = message.get("timestamp")
        if isinstance(message_timestamp, int | float) and not isinstance(message_timestamp, bool):
            migrated["timestamp"] = message_timestamp / 1000
        migrated["type"] = "custom_message"
        migrated["custom_type"] = message.get("customType", message.get("custom_type"))
        migrated["content"] = message.get("content")
        migrated["display"] = message.get("display", True)
        migrated["details"] = message.get("details")
        migrated.pop("message", None)
        return migrated

    migrated["message"] = message
    return migrated


def _stored_entry(value: Any, *, location: str) -> SessionEntry:
    """Validate one migrated entry, tolerating fields this build does not know."""
    if not isinstance(value, dict):
        raise SessionJsonlError(f"Invalid session entry{location}: expected a JSON object")
    version = value.get("schema_version", CURRENT_SCHEMA_VERSION)
    if isinstance(version, int) and version > CURRENT_SCHEMA_VERSION:
        raise SessionVersionError(
            f"Invalid session entry{location}: schema version {version} is newer than the "
            f"{CURRENT_SCHEMA_VERSION} this build supports. Upgrade Baldric to read this session."
        )
    entry_type = value.get("type")
    if entry_type not in _KNOWN_ENTRY_TYPES:
        raise SessionVersionError(
            f"Invalid session entry{location}: unknown type {entry_type!r}, which was written by a "
            "newer Baldric. Upgrade Baldric to read this session."
        )
    return _SESSION_ENTRY_ADAPTER.validate_python(_strip_unknown_fields(value, SessionEntry))


def _strip_unknown_fields(value: Any, annotation: Any) -> Any:
    """Drop fields the annotated model does not declare, at every depth.

    Pi's durable records carry an explicit kind and version, and readers dispatch
    on them. This boundary does the equivalent for pydantic unions: resolve the
    member by its tag, then keep only declared fields. Runtime models stay
    strict; only the persistence boundary is tolerant, which is what lets an
    older build read a transcript that gained a field.
    """
    annotation = _unwrap_annotated(annotation)
    origin = get_origin(annotation)
    if origin in (Union, types.UnionType):
        member = _tagged_member(value, get_args(annotation))
        if member is None:
            return value
        return _strip_unknown_fields(value, member)
    if origin in (list, tuple):
        args = get_args(annotation)
        if not args or not isinstance(value, list):
            return value
        return [_strip_unknown_fields(item, args[0]) for item in value]
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if not isinstance(value, dict):
            return value
        allowed = _allowed_keys(annotation)
        return {
            key: _strip_unknown_fields(item, allowed[key]) for key, item in value.items() if key in allowed
        }
    return value


def _allowed_keys(model: type[BaseModel]) -> dict[str, Any]:
    """Map every accepted payload key (field name and alias) to its annotation.

    The wire models serialize with camelCase aliases, so keeping only field names
    would drop ``toolCallId`` and friends. Both spellings are accepted, matching
    the models' own ``validate_by_name``/``validate_by_alias`` configuration.
    """
    allowed: dict[str, Any] = {}
    for name, field in model.model_fields.items():
        allowed[name] = field.annotation
        for alias in (field.alias, field.validation_alias):
            if isinstance(alias, str):
                allowed[alias] = field.annotation
            else:
                choices = getattr(alias, "choices", ())
                for choice in choices:
                    if isinstance(choice, str):
                        allowed[choice] = field.annotation
    return allowed


def _unwrap_annotated(annotation: Any) -> Any:
    """Resolve PEP 695 ``type`` aliases and ``Annotated`` wrappers to the shape."""
    while True:
        if isinstance(annotation, TypeAliasType):
            annotation = annotation.__value__
            continue
        if get_origin(annotation) is Annotated:
            annotation = get_args(annotation)[0]
            continue
        return annotation


def _tagged_member(value: Any, members: tuple[Any, ...]) -> Any | None:
    """Return the union member whose tag field matches ``value``, if any."""
    if not isinstance(value, dict):
        return None
    for tag_field in _TAG_FIELDS:
        tag = value.get(tag_field)
        if not isinstance(tag, str):
            continue
        for member in members:
            member = _unwrap_annotated(member)
            if not (isinstance(member, type) and issubclass(member, BaseModel)):
                continue
            field = member.model_fields.get(tag_field)
            if field is not None and field.default == tag:
                return member
    return None


def _legacy_label_target_id(values: list[Any]) -> str | None:
    """Choose one stable target for target-less pre-bookmark label records."""
    branchable_types = {"message", "compaction", "branch_summary"}
    for value in values:
        if isinstance(value, dict) and value.get("type") in branchable_types:
            entry_id = value.get("id")
            if isinstance(entry_id, str):
                return entry_id
    for value in values:
        if isinstance(value, dict) and value.get("type") not in {"label", "leaf"}:
            entry_id = value.get("id")
            if isinstance(entry_id, str):
                return entry_id
    return None


def _migrate_message(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    message = dict(value)
    role = message.get("role")

    if role == "user" and ("custom_type" in message or "customType" in message):
        message["role"] = "custom"
        message["customType"] = message.pop("custom_type", message.get("customType"))
        message.pop("custom_type", None)
        message.setdefault("display", True)
        return message

    if role == "assistant":
        usage = message.get("usage")
        if isinstance(usage, dict) and usage.get("cost") is None:
            usage = dict(usage)
            usage["cost"] = {}
            message["usage"] = usage

        content = message.get("content", "")
        if isinstance(content, str):
            blocks: list[Any] = []
            if content:
                blocks.append({"type": "text", "text": content})
            blocks.extend(message.pop("tool_calls", message.pop("toolCalls", [])) or [])
            message["content"] = blocks
        elif "tool_calls" in message or "toolCalls" in message:
            blocks = list(content or [])
            blocks.extend(message.pop("tool_calls", message.pop("toolCalls", [])) or [])
            message["content"] = blocks
        return message

    if role == "tool":
        message["role"] = "toolResult"
        message["toolName"] = message.pop("name", message.get("toolName", "unknown"))
        message["toolCallId"] = message.pop("tool_call_id", message.get("toolCallId", ""))
        message["isError"] = not bool(message.pop("ok", True))
        content = message.get("content", "")
        if isinstance(content, str):
            message["content"] = [{"type": "text", "text": content}] if content else []
        data = message.pop("data", None)
        details = message.get("details")
        if isinstance(data, dict) and isinstance(details, dict):
            message["details"] = {**data, **details}
        elif details is None and data is not None:
            message["details"] = data
        error = message.pop("error", None)
        if error and not message["content"]:
            message["content"] = [{"type": "text", "text": str(error)}]
        return message

    return message
