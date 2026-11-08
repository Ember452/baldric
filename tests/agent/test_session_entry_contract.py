"""Persisted session-entry contract snapshots.

A session file is user data: once written, older and newer Baldric versions both
have to read it, and third-party tools may parse it. This test pins the canonical
JSONL shape of every entry type and proves each one round-trips.

Entry models are intentionally snake_case while the nested messages they carry
are camelCase wire models; the snapshot makes that mixed shape explicit so a
future change to either half shows up as one reviewed line per entry type.
"""

from __future__ import annotations

from typing import get_args

from baldric_protocol.messages import TextContent, Usage, UserMessage
from baldric_protocol.session import (
    BranchSummaryEntry,
    CompactionEntry,
    CustomEntry,
    CustomMessageEntry,
    LabelEntry,
    LeafEntry,
    MessageEntry,
    ModelChangeEntry,
    SessionEntry,
    SessionInfoEntry,
    ThinkingLevelChangeEntry,
)
from baldric_protocol.session.jsonl import entry_from_json_line, entry_to_json_line
from tests.helpers.golden import assert_matches_expected

_TIMESTAMP = 1_700_000_000.0


def _entries() -> tuple[SessionEntry, ...]:
    return (
        MessageEntry(
            id="entry-1",
            parent_id=None,
            timestamp=_TIMESTAMP,
            message=UserMessage(content="hello", timestamp=1_700_000_000_000),
        ),
        CustomMessageEntry(
            id="entry-2",
            parent_id="entry-1",
            timestamp=_TIMESTAMP,
            custom_type="subagent-notification",
            content=[TextContent(text="<task-notification/>")],
            display=True,
            details={"run_id": "run-1"},
        ),
        ModelChangeEntry(
            id="entry-3",
            parent_id="entry-2",
            timestamp=_TIMESTAMP,
            model="golden-model",
            provider="golden-provider",
        ),
        ThinkingLevelChangeEntry(
            id="entry-4",
            parent_id="entry-3",
            timestamp=_TIMESTAMP,
            thinking_level="high",
        ),
        CompactionEntry(
            id="entry-5",
            parent_id="entry-4",
            timestamp=_TIMESTAMP,
            summary="earlier work",
            first_kept_entry_id="entry-4",
            tokens_before=1234,
            usage=Usage(input=10, output=5, total_tokens=15),
            provider="golden-provider",
            model="golden-model",
            response_provider="golden-upstream",
        ),
        BranchSummaryEntry(
            id="entry-6",
            parent_id="entry-5",
            timestamp=_TIMESTAMP,
            summary="explored approach A",
            branch_root_id="entry-1",
            usage=Usage(input=3, output=2, total_tokens=5),
            provider="golden-provider",
            model="golden-model",
        ),
        LabelEntry(
            id="entry-7",
            parent_id="entry-6",
            timestamp=_TIMESTAMP,
            target_id="entry-1",
            label="checkpoint",
        ),
        LeafEntry(
            id="entry-8",
            parent_id="entry-7",
            timestamp=_TIMESTAMP,
            entry_id="entry-6",
        ),
        SessionInfoEntry(
            id="entry-9",
            parent_id="entry-8",
            timestamp=_TIMESTAMP,
            created_at=_TIMESTAMP,
            cwd="D:/work/example",
            title="golden session",
        ),
        CustomEntry(
            id="entry-10",
            parent_id="entry-9",
            timestamp=_TIMESTAMP,
            namespace="baldric.example",
            data={"count": 1, "nested": {"ok": True}},
        ),
    )


def _union_members(alias: object) -> frozenset[type]:
    """Every branch declared by a ``type X = Annotated[Union[...], Field(...)]`` alias."""
    value = getattr(alias, "__value__", alias)
    annotated = get_args(value)
    return frozenset(get_args(annotated[0]))


def test_session_entry_wire_format_is_stable() -> None:
    snapshot = "".join(entry_to_json_line(entry) for entry in _entries())

    assert_matches_expected("session_entries.jsonl", snapshot)


def test_session_entry_snapshot_covers_every_entry_type() -> None:
    """A new entry type must extend this snapshot, not slip past it."""
    covered = {type(entry) for entry in _entries()}

    assert covered == set(_union_members(SessionEntry))


def test_session_entries_round_trip_through_canonical_jsonl() -> None:
    for entry in _entries():
        assert entry_from_json_line(entry_to_json_line(entry)) == entry
