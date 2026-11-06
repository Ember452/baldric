"""Resource, prompt, skill, and diagnostics slash commands."""

from __future__ import annotations

from baldric_coding.commands.base import CommandContext, CommandResult
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
        return CommandResult(handled=True, message="Usage: /system")
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
    return CommandResult(
        handled=True,
        message=format_system_prompt_inspection(inspection),
        system_prompt_inspection=inspection,
    )


def _skills_command(context: CommandContext) -> CommandResult:
    if context.args:
        return CommandResult(handled=True, message="Usage: /skills")
    return CommandResult(handled=True, skills_picker_requested=True)


def _diagnostics_command(context: CommandContext) -> CommandResult:
    if context.args:
        return CommandResult(handled=True, message="Usage: /diagnostics")
    return CommandResult(
        handled=True,
        message=format_resource_diagnostics(context.session.resource_diagnostics),
    )


def _reload_command(context: CommandContext) -> CommandResult:
    # Reload owns async extension lifecycle hooks, so frontends execute it from
    # their async command path rather than inside this synchronous registry.
    return CommandResult(handled=True, reload_requested=True)


def _context_command(context: CommandContext) -> CommandResult:
    session = context.session
    if not session.context_files:
        lines = ["No project context files loaded."]
        if session.resource_diagnostics:
            lines.append("")
            lines.extend(_format_diagnostics(session.resource_diagnostics, kind="context"))
        return CommandResult(handled=True, message="\n".join(lines))

    lines = ["Active project context files:"]
    lines.extend(f"- {context_file.path}" for context_file in session.context_files)
    if session.resource_diagnostics:
        lines.append("")
        lines.extend(_format_diagnostics(session.resource_diagnostics, kind="context"))
    return CommandResult(handled=True, message="\n".join(lines))


def _skill_command(context: CommandContext) -> CommandResult:
    return CommandResult(
        handled=True,
        message="Use /skill:<name> [request] to expand a loaded skill into your prompt.",
    )


def _prompts_command(context: CommandContext) -> CommandResult:
    if context.args:
        return CommandResult(handled=True, message="Usage: /prompts")
    return CommandResult(handled=True, prompts_picker_requested=True)
