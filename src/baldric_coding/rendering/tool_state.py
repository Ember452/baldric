"""Per-state tool row colours and duration formatting (spec 2026-11-08 §6).

pi completes a tool row with a state background and the elapsed time; the
three-state backgrounds default to opencode-dark's role values
(``tool_pending #141414`` stays border-only, ``tool_success #144922``,
``tool_error #410a13``). Theme-owned values arrive via ``ThemeTokens`` when
the widget layer consumes it — the flat ``TuiTheme`` contract stays untouched.
"""

from __future__ import annotations

from rich.style import Style

from baldric_coding.rendering.themes import TuiRoleStyle

TOOL_SUCCESS_BACKGROUND = "#144922"
TOOL_ERROR_BACKGROUND = "#410a13"


def split_rich_style_colors(style: str) -> tuple[str | None, str | None]:
    """Split the foreground/background colors from a simple Rich style string."""
    text_style = Style.parse(style)
    foreground = text_style.color.name if text_style.color is not None else None
    background = text_style.bgcolor.name if text_style.bgcolor is not None else None
    return foreground, background


def tool_state_background(tool_is_error: bool | None, *, has_result: bool) -> str | None:
    """Return the row background for a finished tool call, or ``None``.

    Pending rows keep border-only signalling, and a row without an explicit
    outcome keeps its theme's plain tool background.
    """
    if not has_result or tool_is_error is None:
        return None
    return TOOL_ERROR_BACKGROUND if tool_is_error else TOOL_SUCCESS_BACKGROUND


def format_tool_duration(seconds: float) -> str:
    """Format a completed duration: ``4.2s`` under a minute, then ``1m 23s``."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def tool_row_role_style(
    *,
    tool_is_error: bool | None,
    tool_result_text: str,
    base: TuiRoleStyle,
    success_border: str,
    error_border: str,
) -> TuiRoleStyle:
    """Return the tool row's role style, honouring an explicit outcome.

    An explicit outcome wins over the formatted ``✓``/``✗`` text and carries
    the state background; rows without one keep the theme's plain tool style,
    with the legacy text-prefix heuristic for the border colour only.
    """
    if tool_is_error is None:
        if tool_result_text.startswith("✓"):
            return TuiRoleStyle(border=success_border, body=base.body)
        if tool_result_text.startswith("✗"):
            return TuiRoleStyle(border=error_border, body=base.body)
        return base
    border = error_border if tool_is_error else success_border
    foreground, _ = split_rich_style_colors(base.body)
    state_bg = tool_state_background(tool_is_error, has_result=True)
    body = f"{foreground} on {state_bg}" if state_bg else base.body
    return TuiRoleStyle(border=border, body=body)


def tool_accent_color(
    *,
    is_tool: bool,
    tool_result_text: str | None,
    tool_is_error: bool | None,
    pending_border: str,
    success_text: str,
    error_text: str,
) -> str | None:
    """Return the row accent colour: pending border, then success/error text."""
    if not is_tool:
        return None
    if tool_result_text is None or tool_result_text.startswith("…"):
        return pending_border
    if tool_is_error is not None:
        return error_text if tool_is_error else success_text
    if tool_result_text.startswith("✓"):
        return success_text
    if tool_result_text.startswith("✗"):
        return error_text
    return None
