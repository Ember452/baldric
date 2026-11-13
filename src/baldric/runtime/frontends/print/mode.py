"""Print frontend: run one prompt non-interactively and print streamed events.

This is the print surface's orchestration only. All rendering lives in
``baldric.runtime.rendering`` (the shared renderer library) which this module
consumes via :func:`create_event_renderer`; no rendering implementation is owned
here (structural plan §3.1).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import typer

from baldric.protocol.provider import ModelProvider
from baldric.protocol.session import SessionEntry
from baldric.runtime.commands.base import CommandKind
from baldric.runtime.commands.registry import format_reload_summary
from baldric.runtime.config.shell_config import load_shell_settings
from baldric.runtime.context.resources import BaldricResourcePaths
from baldric.runtime.context.thinking import ThinkingLevel
from baldric.runtime.frontends.session_records import resolve_mode_session_record
from baldric.runtime.platform import StderrUiBridge
from baldric.runtime.providers.config import (
    DEFAULT_PROVIDER_NAME,
    OpenAICompatibleProviderConfig,
    ProviderConfig,
    ProviderConfigError,
    ProviderSettings,
    load_provider_settings,
    resolve_provider_selection,
    resolve_startup_thinking_level,
)
from baldric.runtime.providers.runtime import ClosableModelProvider, create_model_provider
from baldric.runtime.rendering import PrintOutputMode, create_event_renderer
from baldric.runtime.session import SessionStorage
from baldric.runtime.session.manager import SessionManager
from baldric.runtime.session.model_selection import ModelChoice
from baldric.runtime.session.prepare import prepare_coding_session
from baldric.runtime.session.session import (
    CodingSession,
    CodingSessionConfig,
    TerminalCommandResult,
    jsonl_session_storage,
    parse_terminal_command,
)
from baldric.runtime.trust.policy import TrustDefault, TrustOverride


async def run_openai_print_mode(
    prompt: str,
    model: str | None,
    cwd: Path,
    output: PrintOutputMode = PrintOutputMode.text,
    provider_name: str | None = None,
    session_manager: SessionManager | None = None,
    extension_paths: tuple[Path, ...] = (),
    extensions_enabled: bool = True,
    project_extensions_enabled: bool = False,
    session_id: str | None = None,
    custom_system_prompt: str | None = None,
    append_system_prompt: str | None = None,
    trust_override: TrustOverride | None = None,
    resume_session_id: str | None = None,
    *,
    thinking_level_override: ThinkingLevel | None = None,
) -> bool:
    """Run a new or resumed print-mode turn using the configured provider."""
    settings = load_provider_settings()
    shell_settings = load_shell_settings()
    manager = session_manager or SessionManager()
    record = resolve_mode_session_record(
        manager,
        resume_session_id=resume_session_id,
        cwd=cwd,
        settings=settings,
        provider_name=provider_name,
        model=model,
        session_id=session_id,
    )
    explicit_selection = provider_name is not None or model is not None
    selection = None
    if not explicit_selection and record.provider_name is None:
        selection = resolve_provider_selection(settings)
    elif not explicit_selection and record.provider_name is not None:
        try:
            selection = resolve_provider_selection(
                settings,
                provider_name=record.provider_name,
                model=record.model,
            )
        except ProviderConfigError:
            selection = None
    selected_model = model or record.model or (selection.model if selection is not None else "")
    selected_provider: str = (
        provider_name
        if provider_name is not None
        else record.provider_name
        or (selection.provider.name if selection is not None else DEFAULT_PROVIDER_NAME)
    )
    # Durable providers retain the established print-mode construction seam.
    # Dynamic providers are absent from ProviderSettings and therefore remain
    # None until CodingSession's trusted staged environment resolves them.
    static_selection = selection
    if static_selection is None:
        try:
            static_selection = resolve_provider_selection(
                settings,
                provider_name=selected_provider,
                model=selected_model or None,
            )
        except ProviderConfigError:
            static_selection = None
    initial_provider: ClosableModelProvider | None = None
    runtime_config: ProviderConfig | None = None
    runtime_inference = record.inference_provider
    runtime_inference_mode: Literal["automatic", "fixed"] = record.inference_provider_mode or "automatic"
    if static_selection is not None:
        runtime_inference = (
            record.inference_provider
            if (
                resume_session_id is not None
                and record.provider_name == "huggingface"
                and static_selection.provider.name == "huggingface"
                and record.model == static_selection.model
            )
            else (
                static_selection.provider.inference_providers.get(static_selection.model)
                or static_selection.provider.default_inference_provider
                if isinstance(static_selection.provider, OpenAICompatibleProviderConfig)
                and static_selection.provider.name == "huggingface"
                else None
            )
        )
        runtime_inference_mode = (
            record.inference_provider_mode
            if (
                resume_session_id is not None
                and record.provider_name == "huggingface"
                and static_selection.provider.name == "huggingface"
                and record.model == static_selection.model
            )
            else "fixed"
            if runtime_inference is not None
            else "automatic"
        )
        initial_provider = create_model_provider(
            static_selection.provider,
            model=static_selection.model,
            inference_provider=runtime_inference,
            thinking_level=resolve_startup_thinking_level(
                static_selection.provider,
                static_selection.model,
                cli_override=thinking_level_override,
            ),
        )
        selected_provider = static_selection.provider.name
        selected_model = static_selection.model
        runtime_config = static_selection.provider
    try:
        return await run_print_mode(
            prompt=prompt,
            model=selected_model,
            cwd=record.cwd,
            provider=initial_provider,
            output=output,
            storage=jsonl_session_storage(record.path),
            session_id=record.id,
            session_manager=manager,
            provider_name=selected_provider,
            inference_provider=runtime_inference,
            provider_settings=settings,
            runtime_provider_config=runtime_config,
            requested_provider=provider_name if explicit_selection else None,
            requested_model=model if explicit_selection else None,
            session_provider_name=record.provider_name,
            shell_command_prefix=shell_settings.shell_command_prefix,
            shell=shell_settings.shell,
            extension_paths=extension_paths,
            extensions_enabled=extensions_enabled,
            project_extensions_enabled=project_extensions_enabled,
            custom_system_prompt=custom_system_prompt,
            append_system_prompt=append_system_prompt,
            trust_override=trust_override,
            trust_default=shell_settings.default_project_trust,
            startup_model_override=False,
            inference_provider_mode=runtime_inference_mode,
            thinking_level_override=thinking_level_override,
        )
    finally:
        # This remains the ownership path for the compatibility provider
        # constructed by this legacy wrapper. Dynamic candidates are created
        # and owned inside the staged CodingSession instead.
        if initial_provider is not None:
            await initial_provider.aclose()


async def run_print_mode(
    *,
    prompt: str,
    model: str,
    cwd: Path,
    provider: ModelProvider | None,
    output: PrintOutputMode = PrintOutputMode.text,
    resource_paths: BaldricResourcePaths | None = None,
    storage: SessionStorage | None = None,
    session_id: str | None = None,
    session_manager: SessionManager | None = None,
    provider_name: str = DEFAULT_PROVIDER_NAME,
    inference_provider: str | None = None,
    inference_provider_mode: Literal["automatic", "fixed"] | None = None,
    provider_settings: ProviderSettings | None = None,
    runtime_provider_config: ProviderConfig | None = None,
    requested_provider: str | None = None,
    requested_model: str | None = None,
    session_provider_name: str | None = None,
    shell_command_prefix: str | None = None,
    shell: str = "auto",
    extension_paths: tuple[Path, ...] = (),
    extensions_enabled: bool = True,
    project_extensions_enabled: bool = False,
    custom_system_prompt: str | None = None,
    append_system_prompt: str | None = None,
    trust_override: TrustOverride | None = None,
    trust_default: TrustDefault = "ask",
    startup_model_override: bool = False,
    thinking_level_override: ThinkingLevel | None = None,
) -> bool:
    """Run one non-interactive prompt and print streamed events.

    Returns False when the agent emits a non-recoverable error so CLI callers
    can fail non-interactive runs while still rendering the error message.
    """
    prepared = await prepare_coding_session(
        CodingSessionConfig(
            provider=provider,
            model=model,
            thinking_level_override=thinking_level_override,
            cwd=cwd,
            storage=storage or _MemorySessionStorage(),
            resource_paths=resource_paths,
            session_id=session_id,
            session_manager=session_manager,
            provider_name=provider_name,
            inference_provider=inference_provider,
            inference_provider_mode=inference_provider_mode,
            provider_settings=provider_settings,
            runtime_provider_config=runtime_provider_config,
            requested_provider=requested_provider,
            requested_model=requested_model,
            session_provider_name=session_provider_name,
            shell_command_prefix=shell_command_prefix,
            shell=shell,
            extension_paths=extension_paths,
            extensions_enabled=extensions_enabled,
            project_extensions_enabled=project_extensions_enabled,
            custom_system_prompt=custom_system_prompt,
            append_system_prompt=append_system_prompt,
            trust_override=trust_override,
            trust_default=trust_default,
        ),
        session_loader=CodingSession,
    )
    # Informational print commands must not publish the staged initial
    # transcript; /system explicitly promises not to save anything.
    if (stripped_prompt := prompt.strip()) == "/system" or stripped_prompt.startswith("/system "):
        command = prepared.session.handle_command(prompt)
        await prepared.abort()
        if command.outcome.message:
            typer.echo(command.outcome.message)
        return True
    session = await prepared.adopt()
    if startup_model_override:
        await session.apply_startup_model_override(model)
    session.extension_runtime.set_ui_bridge(StderrUiBridge())
    for diagnostic in session.resource_diagnostics:
        if diagnostic.kind == "project-trust":
            typer.echo(diagnostic.format(), err=True)
    await session.emit_pending_session_start()
    renderer = create_event_renderer(
        output,
        custom_message_renderer=session.extension_runtime.render_custom_message,
        cwd=session.cwd,
    )
    try:
        terminal_command = parse_terminal_command(prompt)
        if terminal_command is not None:
            result = await session.run_terminal_command(
                terminal_command.command,
                add_to_context=terminal_command.add_to_context,
            )
            typer.echo(_format_terminal_command_result(result))
            return result.ok
        command = session.handle_command(prompt)
        if command.handled:
            outcome = command.outcome
            message: str | None = outcome.message
            # Intents the TUI performs through its own screens are applied here
            # instead of being dropped: `/model X` used to return "handled" with
            # no message, so print mode printed nothing and exited 0 without
            # changing the model.
            if outcome.kind is CommandKind.MODEL_SELECTED:
                choice = ModelChoice(
                    provider_name=outcome.provider or session.provider_name,
                    model=outcome.text or "",
                )
                try:
                    await session.select_provider_model(choice)
                except (ProviderConfigError, ValueError) as exc:
                    message = f"Could not switch model: {exc}"
                else:
                    message = f"Current model: {choice.provider_name}:{choice.model}"
            elif outcome.kind is CommandKind.THINKING_SET:
                try:
                    level = await session.set_thinking_level(outcome.text or "")
                except ValueError as exc:
                    message = f"Could not set thinking mode: {exc}"
                else:
                    message = f"Thinking mode: {level}"
            elif outcome.kind is CommandKind.SESSION_NAMED:
                try:
                    renamed = await session.set_session_name(outcome.text or "")
                except ValueError as exc:
                    message = f"Could not rename session: {exc}"
                else:
                    message = f"Session renamed: {renamed}"
            elif outcome.kind is CommandKind.RELOAD:
                try:
                    summary = await session.reload()
                except ValueError as exc:
                    message = f"Could not reload: {exc}"
                else:
                    message = format_reload_summary(summary)
            elif outcome.kind is not CommandKind.MESSAGE:
                # One central sentence for every screen-only intent (pickers,
                # /new, /export, /compact, /quit in a one-shot print run), so a
                # new command can never silently no-op here again.
                message = f"{_command_name(prompt)} is interactive-only in print mode."
            typer.echo(message or "")
            return True
        async for event in session.prompt(prompt):
            renderer.render(event)
        return renderer.finish()
    finally:
        await session.aclose()


class _MemorySessionStorage:
    """Append-only in-memory storage for direct print-mode tests."""

    def __init__(self) -> None:
        self.entries: list[SessionEntry] = []

    async def append(self, entry: SessionEntry) -> None:
        self.entries.append(entry)

    async def append_batch(self, entries: Sequence[SessionEntry]) -> None:
        self.entries.extend(entries)

    async def read_all(self) -> list[SessionEntry]:
        return list(self.entries)


def _format_terminal_command_result(result: TerminalCommandResult) -> str:
    context_status = "added to context" if result.added_to_context else "not added to context"
    return f"$ {result.command}\n[{context_status}]\n{result.output}"


def _command_name(prompt: str) -> str:
    """Return the slash command named by ``prompt``, for an explanatory message."""
    stripped = prompt.strip()
    if not stripped:
        return "This command"
    name = stripped.split(maxsplit=1)[0]
    return name if name.startswith("/") else "This command"


__all__ = [
    "run_openai_print_mode",
    "run_print_mode",
]
