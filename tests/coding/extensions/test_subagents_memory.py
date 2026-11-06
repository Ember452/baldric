"""Gap coverage for the memory name rule.

Directory layout, block rendering and truncation are asserted by the suite that
loads the capability end to end; what that suite never exercises directly is the
agent-name validity predicate on its own, which is what this file is for.
"""

from __future__ import annotations

from pathlib import Path

from baldric_coding.extensions.builtins.subagents.memory import (
    is_valid_agent_name,
)


def test_agent_name_validation(tmp_path: Path) -> None:
    assert is_valid_agent_name("a") is True
    assert is_valid_agent_name("a" * 128) is True
    assert is_valid_agent_name("a" * 129) is False
    for rejected in ("", "-", ".x", "1/", "a b", "/abs", "../x"):
        assert is_valid_agent_name(rejected) is False, rejected
