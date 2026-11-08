"""Session-entry schema versioning.

The persisted entry protocol has to survive two directions: an older build must
keep reading a transcript that gained a field, and a build must refuse - with an
actionable message - a transcript written by a shape it does not know. These
tests pin both halves plus the byte-compatibility promise: at the current
version the field is not written at all, so transcripts stay identical to the
ones produced before versioning existed.
"""

from __future__ import annotations

import json

import pytest

from baldric_protocol.messages import AssistantMessage, TextContent, UserMessage
from baldric_protocol.session import (
    CURRENT_SCHEMA_VERSION,
    CustomEntry,
    MessageEntry,
    SessionInfoEntry,
    SessionJsonlError,
    SessionVersionError,
    entries_from_json_lines,
    entry_from_json_line,
    entry_to_json_line,
)


def _message_entry() -> MessageEntry:
    return MessageEntry(message=UserMessage(content="hello"))


def _payload(entry: object) -> dict[str, object]:
    return json.loads(entry_to_json_line(entry))  # type: ignore[arg-type]


def test_current_version_is_not_written_to_disk() -> None:
    line = entry_to_json_line(_message_entry())
    assert "schema_version" not in line


def test_entries_round_trip_without_losing_fields() -> None:
    entries = (
        _message_entry(),
        SessionInfoEntry(cwd="/tmp/project", title="example"),
        CustomEntry(namespace="example", data={"count": 1}),
    )
    for entry in entries:
        parsed = entry_from_json_line(entry_to_json_line(entry))
        assert parsed.model_dump() == entry.model_dump()


def test_missing_version_reads_as_the_current_version() -> None:
    payload = _payload(_message_entry())
    assert "schema_version" not in payload
    parsed = entry_from_json_line(json.dumps(payload))
    assert parsed.schema_version == CURRENT_SCHEMA_VERSION


def test_a_non_current_version_survives_the_round_trip() -> None:
    entry = MessageEntry(message=UserMessage(content="hello"), schema_version=0)
    assert "schema_version" in _payload(entry)
    assert entry_from_json_line(entry_to_json_line(entry)).schema_version == 0


def test_unknown_entry_field_is_ignored() -> None:
    payload = _payload(_message_entry())
    payload["future_entry_field"] = {"nested": True}
    parsed = entry_from_json_line(json.dumps(payload))
    assert isinstance(parsed, MessageEntry)
    assert "future_entry_field" not in parsed.model_dump()


def test_unknown_message_and_content_fields_are_ignored() -> None:
    entry = MessageEntry(message=AssistantMessage(content=[TextContent(text="hi")]))
    payload = _payload(entry)
    message = payload["message"]
    assert isinstance(message, dict)
    message["future_message_field"] = 1
    blocks = message["content"]
    assert isinstance(blocks, list)
    block = blocks[0]
    assert isinstance(block, dict)
    block["future_block_field"] = 2

    parsed = entry_from_json_line(json.dumps(payload))
    assert isinstance(parsed, MessageEntry)
    dumped = parsed.model_dump()
    assert "future_message_field" not in dumped["message"]
    assert "future_block_field" not in dumped["message"]["content"][0]


def test_a_newer_schema_version_is_refused_with_both_versions_named() -> None:
    payload = _payload(_message_entry())
    payload["schema_version"] = CURRENT_SCHEMA_VERSION + 1
    with pytest.raises(SessionVersionError) as excinfo:
        entry_from_json_line(json.dumps(payload), line_number=7)
    message = str(excinfo.value)
    assert "on line 7" in message
    assert str(CURRENT_SCHEMA_VERSION + 1) in message
    assert str(CURRENT_SCHEMA_VERSION) in message
    assert "Upgrade Baldric" in message


def test_an_unknown_entry_type_is_refused_by_name() -> None:
    payload = {"type": "future_entry", "id": "abc", "timestamp": 1.0}
    with pytest.raises(SessionVersionError) as excinfo:
        entry_from_json_line(json.dumps(payload))
    assert "future_entry" in str(excinfo.value)


def test_version_errors_are_jsonl_errors() -> None:
    assert issubclass(SessionVersionError, SessionJsonlError)


def test_transcript_surfaces_the_version_error_without_wrapping_it() -> None:
    lines = [entry_to_json_line(_message_entry()).strip(), json.dumps({"type": "future_entry"})]
    with pytest.raises(SessionVersionError):
        entries_from_json_lines(lines)


def test_word_that_looks_like_a_tag_is_not_mistaken_for_one() -> None:
    """A custom entry's payload may contain "type"/"role" keys of its own."""
    entry = CustomEntry(namespace="example", data={"type": "future_entry", "role": "user"})
    parsed = entry_from_json_line(entry_to_json_line(entry))
    assert parsed.model_dump()["data"] == {"type": "future_entry", "role": "user"}
