"""Resource, prompt, skill, and diagnostics slash commands."""

from __future__ import annotations

from baldric_coding.commands.base import (
    CommandContext,
    CommandKind,
    CommandOutcome,
    CommandResult,
    MessageDisplay,
    PickerKind,
    handled_result,
    message_outcome,
)
from baldric_coding.commands.formatting import (
    _format_diagnostics,
    format_resource_diagnostics,
)
from baldric_coding.context.system_prompt import (
    SystemPromptInspection,
    SystemPromptSource,
    format_system_prompt_inspection,
)


def _system_command(context: CommandContext) -> CommandResult:
    if context.args:
        return handled_result(message_outcome("Usage: /system"))
    inspection = getattr(context.session, "system_prompt_inspection", None)
    if inspection is None:
        inspection = SystemPromptInspection(
            text=context.session.system_prompt,
            sources=(
                SystemPromptSource(
                    kind="runtime",
                    label="Effective system prompt",
                    source="active Baldric session",
                    content=context.session.system_prompt,
                ),
            ),
        )
    # /system renders as a transcript document (it carries the inspection the
    # TUI shows as a full system-prompt view), not a popup.
    return CommandResult(
        outcome=CommandOutcome(
            kind=CommandKind.MESSAGE,
            message=format_system_prompt_inspection(inspection),
            display=MessageDisplay.TRANSCRIPT,
            system_prompt_inspection=inspection,
        )
    )


def _skills_command(context: CommandContext) -> CommandResult:
    if context.args:
        return handled_result(message_outcome("Usage: /skills"))
    return handled_result(CommandOutcome(kind=CommandKind.OPEN_PICKER, picker=PickerKind.SKILLS))


def _diagnostics_command(context: CommandContext) -> CommandResult:
    if context.args:
        return handled_result(message_outcome("Usage: /diagnostics"))
    return handled_result(
        message_outcome(format_resource_diagnostics(context.session.resource_diagnostics))
    )


def _extensions_command(context: CommandContext) -> CommandResult:
    if context.args:
        return handled_result(message_outcome("Usage: /extensions"))
    return handled_result(
        CommandOutcome(kind=CommandKind.OPEN_PICKER, picker=PickerKind.EXTENSIONS)
    )


def _reload_command(context: CommandContext) -> CommandResult:
    # Reload owns async extension lifecycle hooks, so frontends execute it from
    # their async command path rather than inside this synchronous registry.
    return handled_result(CommandOutcome(kind=CommandKind.RELOAD))


def _context_command(context: CommandContext) -> CommandResult:
    session = context.session
    if not session.context_files:
        lines = ["No project context files loaded."]
        if session.resource_diagnostics:
            lines.append("")
            lines.extend(_format_diagnostics(session.resource_diagnostics, kind="context"))
        return handled_result(message_outcome("\n".join(lines)))

    lines = ["Active project context files:"]
    lines.extend(f"- {context_file.path}" for context_file in session.context_files)
    if session.resource_diagnostics:
        lines.append("")
        lines.extend(_format_diagnostics(session.resource_diagnostics, kind="context"))
    return handled_result(message_outcome("\n".join(lines)))


def _skill_command(context: CommandContext) -> CommandResult:
    return handled_result(
        message_outcome("Use /skill:<name> [request] to expand a loaded skill into your prompt.")
    )


def _prompts_command(context: CommandContext) -> CommandResult:
    if context.args:
        return handled_result(message_outcome("Usage: /prompts"))
    return handled_result(
        CommandOutcome(kind=CommandKind.OPEN_PICKER, picker=PickerKind.PROMPTS)
    )
