"""Approval card rendering for the opt-in tool approval mode.

One card = one pending mutating tool call: what will run (a unified diff for
edit/write, the verbatim command for bash), how big the change is, and the
three answers with the exact Always rule spelled out before it is remembered.
"""

from __future__ import annotations

from rich.console import Group, RenderableType
from rich.text import Text

from baldric_coding.rendering.diffs import render_patch
from baldric_coding.rendering.themes import TuiTheme
from baldric_coding.rendering.widths import truncate_to_cells
from baldric_coding.trust.approvals import (
    ApprovalRequest,
    ApprovalRule,
    summarize_preview_changes,
)


def _looks_like_unified_diff(preview: str) -> bool:
    return preview.startswith("--- ") or "\n--- " in preview or preview.startswith("@@") or "\n@@" in preview


def render_approval_card(
    request: ApprovalRequest,
    *,
    theme: TuiTheme,
    always_rule: ApprovalRule,
) -> RenderableType:
    """Render the approval card for one pending call."""
    header = Text(f"Approval required — {request.tool_name}", style=f"bold {theme.accent}")
    target = Text(f"target: {truncate_to_cells(request.target, 100)}", style=theme.prompt_text)

    parts: list[RenderableType] = [header, target]
    if _looks_like_unified_diff(request.preview):
        parts.append(Text(summarize_preview_changes(request.preview), style=theme.muted_text))
        diff = render_patch(request.preview, theme=theme)
        if diff is not None:
            parts.append(diff)
        else:
            parts.append(Text(request.preview, style=theme.prompt_text))
    elif request.preview:
        parts.append(Text(request.preview, style=theme.prompt_text))

    footer = Text(
        f"[Y] allow once   [A] always — {always_rule.describe()}   [N] reject · Esc rejects",
        style=theme.completion_description,
    )
    parts.append(Text(""))
    parts.append(footer)
    return Group(*parts)
