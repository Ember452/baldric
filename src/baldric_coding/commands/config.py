"""Model, provider-login, thinking, theme, and local-backend commands."""

from __future__ import annotations

from baldric_coding.commands.base import CommandContext, CommandResult, CommandSession
from baldric_coding.context.thinking import normalize_thinking_level
from baldric_coding.providers.catalog import BUILTIN_PROVIDER_CATALOG, builtin_provider_entry

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
            return CommandResult(
                handled=True,
                message=f"Unknown model for provider {context.session.provider_name}: {model}\n"
                f"Available models: {models}",
            )
        if callable(getattr(context.session, "select_provider_model", None)):
            return CommandResult(
                handled=True,
                model_selection_provider=context.session.provider_name,
                model_selection_model=model,
            )
        context.session.set_model(model)
        return CommandResult(handled=True, message=f"Current model: {model}")

    return CommandResult(handled=True, model_picker_requested=True)


def _scoped_models_command(context: CommandContext) -> CommandResult:
    if context.args:
        return CommandResult(handled=True, message="Usage: /scoped-models")
    return CommandResult(handled=True, scoped_models_picker_requested=True)


def _thinking_command(context: CommandContext) -> CommandResult:
    session = context.session
    available = tuple(session.available_thinking_levels)
    if not context.args:
        lines = _thinking_status_lines(session)
        if available:
            lines.append(f"Available modes: {', '.join(available)}")
        else:
            lines.insert(1, f"Current model: {session.provider_name}:{session.model}")
        return CommandResult(handled=True, message="\n".join(lines))

    if not available:
        message = f"Thinking controls are unavailable for {session.provider_name}:{session.model}"
        reason = _thinking_unavailable_reason(session)
        if reason:
            message = f"{message}: {reason}"
        return CommandResult(
            handled=True,
            message=message,
        )
    try:
        level = normalize_thinking_level(context.args)
    except ValueError as exc:
        return CommandResult(handled=True, message=str(exc))
    if level not in available:
        modes = ", ".join(available)
        return CommandResult(
            handled=True,
            message=(
                f"Thinking mode {level} is not available for "
                f"{session.provider_name}:{session.model}\n"
                f"Available modes: {modes}"
            ),
        )
    return CommandResult(handled=True, thinking_level=level)


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
        return CommandResult(handled=True, theme_picker_requested=True)

    # Imported lazily so importing this module never pulls in `baldric_coding.tui`
    # (whose package __init__ imports Textual) until /theme actually executes.
    from baldric_coding.rendering.themes import available_tui_theme_names

    theme_name = context.args.strip()
    available = available_tui_theme_names()
    if theme_name not in available:
        themes = ", ".join(available)
        return CommandResult(
            handled=True,
            message=f"Unknown theme: {theme_name}\nAvailable themes: {themes}",
        )
    return CommandResult(handled=True, theme=theme_name)


def _local_command(context: CommandContext) -> CommandResult:
    if context.args:
        return CommandResult(handled=True, message="Usage: /local")
    return CommandResult(handled=True, local_requested=True)


def _sidebar_command(context: CommandContext) -> CommandResult:
    if context.args:
        return CommandResult(handled=True, message="Usage: /sidebar")
    return CommandResult(handled=True, sidebar_toggle_requested=True)


def _login_command(context: CommandContext) -> CommandResult:
    provider_name = context.args.strip()
    if provider_name in {"custom", "new", "add"}:
        return CommandResult(handled=True, custom_provider_login_requested=True)
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
            return CommandResult(
                handled=True,
                message=(f"Unknown login provider: {provider_name}\nAvailable providers: {providers}"),
            )
        return CommandResult(
            handled=True,
            login_provider=entry.name,
            login_method=login_method,
        )

    return CommandResult(handled=True, login_picker_requested=True)


def _logout_command(context: CommandContext) -> CommandResult:
    provider_name = context.args.strip()
    if provider_name:
        entry = builtin_provider_entry(provider_name)
        if entry is None:
            providers = ", ".join(entry.name for entry in BUILTIN_PROVIDER_CATALOG)
            return CommandResult(
                handled=True,
                message=(f"Unknown logout provider: {provider_name}\nAvailable providers: {providers}"),
            )
        return CommandResult(handled=True, logout_provider=entry.name)

    return CommandResult(handled=True, logout_picker_requested=True)
