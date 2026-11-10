"""Core slash commands: session lifecycle, export, status, and help."""

from __future__ import annotations

from baldric.coding.commands.base import (
    CommandContext,
    CommandKind,
    CommandOutcome,
    CommandResult,
    PickerKind,
    _parse_export_args,
    handled_result,
    message_outcome,
)
from baldric.coding.commands.config import _thinking_status_lines


def _help_command(context: CommandContext) -> CommandResult:
    lines = ["Available commands:"]
    for command in context.registry.list_commands():
        lines.append(f"{command.usage}\t{command.description}")
    return handled_result(message_outcome("\n".join(lines)))


def _exit_command(context: CommandContext) -> CommandResult:
    return CommandResult(outcome=CommandOutcome(kind=CommandKind.EXIT, message="Exiting session."))


def _new_command(context: CommandContext) -> CommandResult:
    return CommandResult(outcome=CommandOutcome(kind=CommandKind.NEW_SESSION))


def _compact_command(context: CommandContext) -> CommandResult:
    return CommandResult(outcome=CommandOutcome(kind=CommandKind.COMPACT, text=context.args.strip()))


def _export_command(context: CommandContext) -> CommandResult:
    try:
        export_format, destination = _parse_export_args(context.args)
    except ValueError as exc:
        return handled_result(message_outcome(str(exc)))
    return CommandResult(
        outcome=CommandOutcome(
            kind=CommandKind.EXPORT,
            text=str(destination) if destination is not None else None,
            format=export_format,
        )
    )


def _status_command(context: CommandContext) -> CommandResult:
    session = context.session
    context_usage = getattr(session, "context_usage", None)
    lines = [
        f"Model: {session.model}",
        f"Provider: {session.provider_name}",
        f"CWD: {session.cwd}",
        f"Tools: {len(session.tools)}",
        f"Skills: {len(session.skills)}",
        f"Prompt templates: {len(session.prompt_templates)}",
        f"Context files: {len(session.context_files)}",
        f"Estimated context tokens: {session.context_token_estimate}",
        f"Context window: {session.context_window_tokens}",
    ]
    if session.provider_name == "huggingface":
        route = getattr(session, "inference_provider", None)
        mode = getattr(session, "inference_provider_mode", "fixed" if route else "automatic")
        if mode == "automatic":
            route_status = f"automatic (currently {route})" if route else "automatic"
        else:
            route_status = f"{route} (fixed)" if route else "fixed"
        lines.append(f"Hugging Face inference provider: {route_status}")
    context_window_source = getattr(session, "context_window_source", None)
    if context_window_source:
        lines.append(f"Context window source: {context_window_source}")
    discovery_error = getattr(session, "model_limits_discovery_error", None)
    if discovery_error:
        lines.append(f"Model limit discovery: unavailable ({discovery_error})")
    if context_usage is not None:
        if context_usage.uses_provider_usage:
            lines.append(
                "Context token basis: "
                f"provider={context_usage.provider_tokens}, "
                f"estimated trailing={context_usage.trailing_tokens}",
            )
        else:
            lines.append(
                "Context token breakdown: "
                f"system={context_usage.system_tokens}, "
                f"messages={context_usage.message_tokens}, "
                f"tools={context_usage.tool_tokens}",
            )
    lines.extend(_thinking_status_lines(session))
    lines.append(f"Resource diagnostics: {len(session.resource_diagnostics)}")
    if session.auto_compact_token_threshold is not None:
        lines.append(f"Auto compact threshold: {session.auto_compact_token_threshold}")
    if session.session_id is not None:
        lines.append(f"Session: {session.session_id}")
    if session.session_title:
        lines.append(f"Session name: {session.session_title}")
    return handled_result(message_outcome("\n".join(lines)))


def _hotkeys_command(context: CommandContext) -> CommandResult:
    lines = [
        "Common keyboard shortcuts:",
        "- Enter: submit prompt",
        "- Shift+Enter: insert newline",
        "- Ctrl+E: edit prompt in external editor ($VISUAL/$EDITOR)",
        "- Alt+Enter: queue follow-up while running",
        "- Esc: cancel active run",
        "- Ctrl+K: open slash-command completions",
        "- Ctrl+R: open session picker",
        "- Ctrl+P / Shift+Ctrl+P: cycle scoped models forward / backward",
        "- Shift+Tab: cycle thinking mode",
        "- Ctrl+T: toggle thinking tokens",
        "- Ctrl+O: collapse or expand tool output",
        "- Ctrl+C: clear prompt input",
        "- Ctrl+D: quit",
    ]
    return handled_result(message_outcome("\n".join(lines)))


def _tools_command(context: CommandContext) -> CommandResult:
    return CommandResult(outcome=CommandOutcome(kind=CommandKind.OPEN_PICKER, picker=PickerKind.TOOLS))
