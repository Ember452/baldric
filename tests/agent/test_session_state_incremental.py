"""Incremental session state for the persist hot path.

Every persisted message used to re-read the transcript (a deep copy of every
entry) and replay the whole branch, so persisting was quadratic in session
length. The fast path derives the new state from the old one; these tests pin
that it is indistinguishable from a full replay.
"""

from __future__ import annotations

from baldric.protocol.messages import AssistantMessage, UserMessage
from baldric.protocol.session import (
    CompactionEntry,
    LabelEntry,
    MessageEntry,
    ModelChangeEntry,
    SessionInfoEntry,
)
from baldric.runtime.session import SessionState


def _message(content: str, parent_id: str | None) -> MessageEntry:
    return MessageEntry(parent_id=parent_id, message=UserMessage(content=content))


def test_incremental_appends_match_a_full_replay() -> None:
    entries = [SessionInfoEntry(cwd="/tmp/project")]
    state = SessionState.from_entries(list(entries))

    for index in range(25):
        entry = _message(f"message {index}", state.active_leaf_id)
        assert state.accepts_appended_message(entry)
        entries.append(entry)
        state = state.with_appended_message(entry, leaf_id=entry.id)

        assert state == SessionState.from_entries(list(entries))
        assert state.active_leaf_id == entry.id


def test_incremental_appends_match_a_full_replay_after_compaction() -> None:
    first = _message("one", None)
    second = _message("two", first.id)
    compaction = CompactionEntry(parent_id=second.id, summary="summary", first_kept_entry_id=second.id)
    entries = [first, second, compaction]
    state = SessionState.from_entries(list(entries))

    entry = _message("three", state.active_leaf_id)
    assert state.accepts_appended_message(entry)
    entries.append(entry)
    state = state.with_appended_message(entry, leaf_id=entry.id)

    assert state == SessionState.from_entries(list(entries))


def test_an_entry_that_is_not_a_tip_message_falls_back_to_the_replay() -> None:
    entries = [SessionInfoEntry(cwd="/tmp/project")]
    state = SessionState.from_entries(list(entries))

    assert not state.accepts_appended_message(ModelChangeEntry(model="gpt-5"))
    assert not state.accepts_appended_message(LabelEntry(target_id="x", label="keep"))
    mismatched = _message("stray", parent_id="not-the-tip")
    assert not state.accepts_appended_message(mismatched)


def test_a_root_message_grows_an_empty_path() -> None:
    state = SessionState.from_entries([])
    entry = _message("hello", None)

    assert state.accepts_appended_message(entry)
    assert state.with_appended_message(entry, leaf_id=entry.id) == SessionState.from_entries([entry])


def test_incremental_state_keeps_messages_and_context_ids_in_step() -> None:
    state = SessionState.from_entries([])
    entry = _message("hello", None)
    updated = state.with_appended_message(entry, leaf_id=entry.id)

    assert updated.messages == (entry.message,)
    assert updated.context_entry_ids == (entry.id,)
    assert updated.entries == (entry,)


def test_an_assistant_message_can_use_the_fast_path() -> None:
    state = SessionState.from_entries([])
    entry = MessageEntry(parent_id=None, message=AssistantMessage(content="hi"))

    assert state.accepts_appended_message(entry)
    assert state.with_appended_message(entry, leaf_id=entry.id) == SessionState.from_entries([entry])
