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

from baldric_coding.tools.base import ToolInputError
from baldric_coding.tools.edit import (
    apply_argument_edits_to_content,
    generate_unified_patch,
)
from baldric_protocol.types import JSONValue

MUTATING_TOOL_NAMES = frozenset({"edit", "write", "bash"})

# A bare prefix match is unsafe for shell commands: remembering `ls` would
# also allow `lsblk`, and `ls; rm -rf ~` starts with the same token. A command
# that composes shells (pipes, chaining, redirection, substitution) is never
# covered by an Always rule — it always asks, because the remembered program
# token does not describe what will actually run.
_SHELL_COMPOSITION_MARKERS = (";", "&&", "||", "|", "&", ">", "<", "`", "$(", "\n")

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

    edit/write rules match one exact resolved path; bash rules match one exact
    simple command. Neither is a prefix, so a rule can never silently widen to
    cover a different file or a compound shell command. The card spells the
    rule out verbatim so the user sees exactly what will be remembered.
    """

    tool_name: str
    prefix: str

    def describe(self) -> str:
        if self.tool_name == "bash":
            return f"the exact command `{self.prefix}`"
        return f"the exact path `{self.prefix}`"


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    """The user's answer to one approval card."""

    approved: bool
    remember: bool = False
    reason: str | None = None


DEFAULT_REJECT_REASON = "Rejected by user"


@dataclass
class ApprovalPolicy:
    """Decides whether a mutating tool call needs the user's approval.

    Always rules are deliberately narrow: an edit/write rule covers one exact
    resolved path (not its children or siblings), and a bash rule covers one
    exact simple command (not a compound one). A rule must never quietly widen
    the set of things that run without asking.
    """

    rules: list[ApprovalRule] = field(default_factory=list)

    def decide(self, tool_name: str, target: str) -> ApprovalRule | None:
        """Return the matching Always rule, or None when approval is required."""
        candidate = self._canonical(tool_name, target)
        if candidate is None:
            # Unparseable/compound target: no Always rule can cover it.
            return None
        for rule in self.rules:
            if rule.tool_name == tool_name and rule.prefix == candidate:
                return rule
        return None

    def preview_rule(self, tool_name: str, target: str) -> ApprovalRule:
        """Return the Always rule *would be* remembered, without storing it.

        For a bash command the remembered rule is the whole command as typed
        (not just the program token), so an Always never grants a broader
        command than the one the user actually saw and approved.
        """
        prefix = self._canonical(tool_name, target) or target.strip() or target
        return ApprovalRule(tool_name=tool_name, prefix=prefix)

    def remember(self, tool_name: str, target: str) -> ApprovalRule:
        """Record an Always rule for this call and return it."""
        rule = self.preview_rule(tool_name, target)
        if rule not in self.rules:
            self.rules.append(rule)
        return rule

    def _canonical(self, tool_name: str, target: str) -> str | None:
        """Return the exact-match key for *target*, or None when it is unsafe.

        edit/write resolve to an absolute normalized path so ``a/../b.py`` and
        ``b.py`` are the same rule and ``file.py.bak`` is *not*. bash resolves to
        the single simple command only; a compound command yields None so it can
        never be auto-approved by a rule remembered from a simpler one.
        """
        if tool_name == "bash":
            command = target.strip()
            if not command:
                return None
            if any(marker in command for marker in _SHELL_COMPOSITION_MARKERS):
                return None
            return command
        if not target.strip():
            return None
        try:
            return str(Path(target).expanduser().resolve())
        except (OSError, RuntimeError):
            return target


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
