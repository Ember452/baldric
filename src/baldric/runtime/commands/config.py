"""Model, provider-login, thinking, theme, and local-backend commands."""

from __future__ import annotations

from baldric.runtime.commands.base import (
    CommandContext,
    CommandKind,
    CommandOutcome,
    CommandResult,
    CommandSession,
    PickerKind,
    handled_result,
    message_outcome,
)
from baldric.runtime.context.thinking import normalize_thinking_level
from baldric.runtime.providers.catalog import (
    BUILTIN_PROVIDER_CATALOG,
    builtin_provider_entry,
)

LOGIN_PROVIDER_ALIASES = {
    "anthropic-api": ("anthropic", "api-key"),
    "anthropic-subscription": ("anthropic", "subscription"),
}


def _model_command(context: CommandContext) -> CommandResult:
    # The picker uses the current snapshot and refreshes catalogs after opening.
    # Rebuilding the active provider here can prevent the picker from opening.
    if context.args:
        model = context.args.strip()
        available_models = set(context.session.available_models)
        if available_models and model not in available_models:
            models = ", ".join(sorted(available_models))
            return handled_result(
                message_outcome(
                    f"Unknown model for provider {context.session.provider_name}: {model}\n"
                    f"Available models: {models}"
                )
            )
        if callable(getattr(context.session, "select_provider_model", None)):
            return handled_result(
                CommandOutcome(
                    kind=CommandKind.MODEL_SELECTED,
                    provider=context.session.provider_name,
                    text=model,
                )
            )
        context.session.set_model(model)
        return handled_result(message_outcome(f"Current model: {model}"))

    return handled_result(CommandOutcome(kind=CommandKind.OPEN_PICKER, picker=PickerKind.MODEL))


def _scoped_models_command(context: CommandContext) -> CommandResult:
    if context.args:
        return handled_result(message_outcome("Usage: /scoped-models"))
    return handled_result(CommandOutcome(kind=CommandKind.OPEN_PICKER, picker=PickerKind.SCOPED_MODELS))


def _thinking_command(context: CommandContext) -> CommandResult:
    session = context.session
    available = tuple(session.available_thinking_levels)
    if not context.args:
        lines = _thinking_status_lines(session)
        if available:
            lines.append(f"Available modes: {', '.join(available)}")
        else:
            lines.insert(1, f"Current model: {session.provider_name}:{session.model}")
        return handled_result(message_outcome("\n".join(lines)))

    if not available:
        message = f"Thinking controls are unavailable for {session.provider_name}:{session.model}"
        reason = _thinking_unavailable_reason(session)
        if reason:
            message = f"{message}: {reason}"
        return handled_result(message_outcome(message))

    try:
        level = normalize_thinking_level(context.args)
    except ValueError as exc:
        return handled_result(message_outcome(str(exc)))
    if level not in available:
        modes = ", ".join(available)
        return handled_result(
            message_outcome(
                f"Thinking mode {level} is not available for "
                f"{session.provider_name}:{session.model}\n"
                f"Available modes: {modes}"
            )
        )
    return handled_result(CommandOutcome(kind=CommandKind.THINKING_SET, text=level))


def _thinking_status_lines(session: CommandSession) -> list[str]:
    if tuple(session.available_thinking_levels):
        return [f"Thinking mode: {session.thinking_level}"]
    lines = ["Thinking mode: unavailable"]
    reason = _thinking_unavailable_reason(session)
    if reason:
        lines.append(f"Thinking unavailable: {reason}")
    return lines


def _thinking_unavailable_reason(session: CommandSession) -> str | None:
    reason = getattr(session, "thinking_unavailable_reason", None)
    return reason if isinstance(reason, str) and reason else None


def _theme_command(context: CommandContext) -> CommandResult:
    if not context.args:
        return handled_result(CommandOutcome(kind=CommandKind.OPEN_PICKER, picker=PickerKind.THEME))

    # Imported lazily so importing this module never pulls in `baldric.runtime.tui`
    # (whose package __init__ imports Textual) until /theme actually executes.
    from baldric.runtime.rendering.themes import available_tui_theme_names

    theme_name = context.args.strip()
    available = available_tui_theme_names()
    if theme_name not in available:
        themes = ", ".join(available)
        return handled_result(message_outcome(f"Unknown theme: {theme_name}\nAvailable themes: {themes}"))
    return handled_result(CommandOutcome(kind=CommandKind.THEME_SET, text=theme_name))


def _local_command(context: CommandContext) -> CommandResult:
    if context.args:
        return handled_result(message_outcome("Usage: /local"))
    return handled_result(CommandOutcome(kind=CommandKind.OPEN_PICKER, picker=PickerKind.LOCAL_BACKEND))


def _sidebar_command(context: CommandContext) -> CommandResult:
    if context.args:
        return handled_result(message_outcome("Usage: /sidebar"))
    return handled_result(CommandOutcome(kind=CommandKind.TOGGLE_SIDEBAR))


def _approvals_command(context: CommandContext) -> CommandResult:
    if context.args:
        return handled_result(message_outcome("Usage: /approvals"))
    # The frontend owns the durable setting and reports the new mode; the
    # registry only records the toggle intent.
    return handled_result(CommandOutcome(kind=CommandKind.TOGGLE_APPROVALS))


def _login_command(context: CommandContext) -> CommandResult:
    provider_name = context.args.strip()
    if provider_name in {"custom", "new", "add"}:
        return handled_result(
            CommandOutcome(kind=CommandKind.OPEN_PICKER, picker=PickerKind.CUSTOM_PROVIDER_LOGIN)
        )
    if provider_name:
        aliased_provider = LOGIN_PROVIDER_ALIASES.get(provider_name)
        if aliased_provider is not None:
            provider_name, login_method = aliased_provider
        else:
            login_method = None
        entry = builtin_provider_entry(provider_name)
        if entry is None:
            providers = ", ".join(
                [
                    *(entry.name for entry in BUILTIN_PROVIDER_CATALOG),
                    *LOGIN_PROVIDER_ALIASES,
                ]
            )
            return handled_result(
                message_outcome(f"Unknown login provider: {provider_name}\nAvailable providers: {providers}")
            )
        return handled_result(
            CommandOutcome(
                kind=CommandKind.OPEN_PICKER,
                picker=PickerKind.LOGIN_PROVIDER,
                provider=entry.name,
                method=login_method,
            )
        )

    return handled_result(CommandOutcome(kind=CommandKind.OPEN_PICKER, picker=PickerKind.LOGIN_METHOD))


def _logout_command(context: CommandContext) -> CommandResult:
    provider_name = context.args.strip()
    if provider_name:
        entry = builtin_provider_entry(provider_name)
        if entry is None:
            providers = ", ".join(entry.name for entry in BUILTIN_PROVIDER_CATALOG)
            return handled_result(
                message_outcome(f"Unknown logout provider: {provider_name}\nAvailable providers: {providers}")
            )
        return handled_result(
            CommandOutcome(
                kind=CommandKind.OPEN_PICKER,
                picker=PickerKind.LOGOUT_PROVIDER,
                provider=entry.name,
            )
        )

    return handled_result(CommandOutcome(kind=CommandKind.OPEN_PICKER, picker=PickerKind.LOGOUT_PROVIDER))
