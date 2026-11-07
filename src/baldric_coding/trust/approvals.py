"""Session-scoped tool approval policy for the opt-in approval mode.

The mode is off by default: in a trusted project every tool runs directly
(agent-first, the pi posture). When the user turns approval on, mutating tool
calls (edit/write/bash) pause for an in-terminal approval card offering Once /
Always / Reject. "Always" rules are session-scoped on purpose — an opt-in ask
mode must never silently become permanent, and persisted rules belong to a
later, reviewed feature with explicit management UI.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from baldric_agent.types import JSONValue
from baldric_coding.tools.base import ToolInputError
from baldric_coding.tools.edit import (
    apply_argument_edits_to_content,
    generate_unified_patch,
)

MUTATING_TOOL_NAMES = frozenset({"edit", "write", "bash"})

_PREVIEW_MAX_LINES = 60
_PREVIEW_FALLBACK = "(preview unavailable: arguments could not be interpreted)"


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    """Everything the approval card needs to render one decision."""

    tool_name: str
    target: str
    preview: str


@dataclass(frozen=True, slots=True)
class ApprovalRule:
    """One remembered Always rule.

    edit/write rules match the target path by prefix; bash rules match the
    command's first token (the program), which the card spells out verbatim
    so the user always sees exactly what will be remembered.
    """

    tool_name: str
    prefix: str

    def describe(self) -> str:
        if self.tool_name == "bash":
            return f"bash commands starting with `{self.prefix}`"
        return f"{self.tool_name} paths starting with `{self.prefix}`"


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    """The user's answer to one approval card."""

    approved: bool
    remember: bool = False
    reason: str | None = None


DEFAULT_REJECT_REASON = "Rejected by user"


@dataclass
class ApprovalPolicy:
    """Decides whether a mutating tool call needs the user's approval."""

    rules: list[ApprovalRule] = field(default_factory=list)

    def decide(self, tool_name: str, target: str) -> ApprovalRule | None:
        """Return the matching Always rule, or None when approval is required."""
        for rule in self.rules:
            if rule.tool_name == tool_name and target.startswith(rule.prefix):
                return rule
        return None

    def preview_rule(self, tool_name: str, target: str) -> ApprovalRule:
        """Return the Always rule *would be* remembered, without storing it."""
        prefix = target
        if tool_name == "bash":
            tokens = target.strip().split()
            prefix = tokens[0] if tokens else target
        return ApprovalRule(tool_name=tool_name, prefix=prefix)

    def remember(self, tool_name: str, target: str) -> ApprovalRule:
        """Record an Always rule for this call and return it."""
        rule = self.preview_rule(tool_name, target)
        if rule not in self.rules:
            self.rules.append(rule)
        return rule


def approval_target(tool_name: str, arguments: Mapping[str, JSONValue]) -> str:
    """Return the human-facing target of a mutating call (path or command)."""
    if tool_name == "bash":
        return str(arguments.get("command", ""))
    return str(arguments.get("path", ""))


def _edit_preview(arguments: Mapping[str, JSONValue], path: Path) -> str | None:
    try:
        content = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        new_content = apply_argument_edits_to_content(content, arguments, str(path))
    except (ToolInputError, KeyError, TypeError, ValueError):
        # A malformed or non-matching edit argument still deserves a card;
        # the preview just degrades to the fallback text.
        return None
    return generate_unified_patch(str(path), content, new_content)


def _write_preview(arguments: Mapping[str, JSONValue], path: Path) -> str | None:
    content = arguments.get("content")
    if not isinstance(content, str):
        return None
    try:
        old = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        old = ""
    return generate_unified_patch(str(path), old, content)


def build_approval_preview(
    tool_name: str,
    arguments: Mapping[str, JSONValue],
    *,
    cwd: Path,
) -> str:
    """Build the preview shown on the approval card.

    edit/write previews are unified patches computed without executing the
    tool; bash previews are the verbatim command. Anything uninterpretable
    degrades to a short fallback rather than failing the gate.
    """
    if tool_name == "bash":
        return str(arguments.get("command", ""))
    raw_path = arguments.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return _PREVIEW_FALLBACK
    path = Path(raw_path)
    if not path.is_absolute():
        path = cwd / path
    if tool_name == "edit":
        preview = _edit_preview(arguments, path)
    elif tool_name == "write":
        preview = _write_preview(arguments, path)
    else:
        preview = None
    if preview is None:
        return _PREVIEW_FALLBACK
    lines = preview.splitlines()
    if len(lines) > _PREVIEW_MAX_LINES:
        kept = "\n".join(lines[:_PREVIEW_MAX_LINES])
        return f"{kept}\n… (+{len(lines) - _PREVIEW_MAX_LINES} more diff lines)"
    return preview


def summarize_preview_changes(preview: str) -> str:
    """Return a one-line ``+N -M`` change summary for a unified-diff preview."""
    added = sum(1 for line in preview.splitlines() if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in preview.splitlines() if line.startswith("-") and not line.startswith("---"))
    if not added and not removed:
        return "no changes"
    return f"+{added} -{removed} lines"
