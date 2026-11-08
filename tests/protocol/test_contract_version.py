"""Protocol contract version and freeze.

The wire contract is published for third-party use, so its version must only
change deliberately. This pins the current version and asserts the golden
snapshots that lock the bytes still exist, so a change to the wire shape has to
touch this file too (a reviewed, explicit step).
"""

from __future__ import annotations

from pathlib import Path

import baldric_protocol

REPO_ROOT = Path(__file__).resolve().parents[2]

# Bump together with an intentional, reviewed wire change; say why in the commit.
EXPECTED_PROTOCOL_VERSION = 1


def test_protocol_version_is_pinned() -> None:
    assert baldric_protocol.PROTOCOL_VERSION == EXPECTED_PROTOCOL_VERSION


def test_wire_snapshot_goldens_exist() -> None:
    """The snapshots that lock the wire bytes must remain present.

    If a snapshot file is deleted, the corresponding ``test_wire_contract`` /
    ``test_session_entry_contract`` golden test would silently stop guarding the
    persisted shape. This asserts the fixtures exist so that lock stays real.
    """
    golden = REPO_ROOT / "tests" / "expected"
    names = {
        "agent_message_union.jsonl",
        "provider_events.jsonl",
        "agent_events.jsonl",
        "session_entries.jsonl",
    }
    present = {p.name for p in golden.rglob("*.jsonl")} if golden.exists() else set()
    missing = names - present
    assert not missing, f"wire snapshot goldens missing: {sorted(missing)} (looked in {golden})"
