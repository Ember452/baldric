"""RPC frontend: run a persistent Pi-compatible JSONL RPC session.

Owns the mode's provider selection and session lifecycle; the wire protocol lives
in ``server.py`` / ``wire.py``. This mirrors ``frontends/print/mode.py``: the CLI
only parses arguments and dispatches, the frontend owns its own mode entry.
"""

from __future__ import annotations

from pathlib import Path

from baldric.runtime.config.shell_config import load_shell_settings
from baldric.runtime.context.thinking import ThinkingLevel
from baldric.runtime.frontends.rpc.server import RpcServer
from baldric.runtime.frontends.session_records import resolve_mode_session_record
from baldric.runtime.platform import StderrUiBridge
from baldric.runtime.providers.config import (
    OpenAICompatibleProviderConfig,
    ProviderConfigError,
    load_provider_settings,
    resolve_provider_selection,
    resolve_startup_thinking_level,
)
from baldric.runtime.providers.runtime import create_model_provider
from baldric.runtime.session.manager import SessionManager
from baldric.runtime.session.session import (
    CodingSession,
    CodingSessionConfig,
    jsonl_session_storage,
)
from baldric.runtime.trust.policy import TrustOverride


async def run_openai_rpc_mode(
    model: str | None,
    cwd: Path,
    provider_name: str | None = None,
    resume_session_id: str | None = None,
    extension_paths: tuple[Path, ...] = (),
    extensions_enabled: bool = True,
    project_extensions_enabled: bool = False,
    custom_system_prompt: str | None = None,
    append_system_prompt: str | None = None,
    trust_override: TrustOverride | None = None,
    *,
    thinking_level_override: ThinkingLevel | None = None,
) -> None:
    """Run a persistent Pi-compatible JSONL RPC session."""
    settings = load_provider_settings()
    shell_settings = load_shell_settings()
    manager = SessionManager()
    record = resolve_mode_session_record(
        manager,
        resume_session_id=resume_session_id,
        cwd=cwd,
        settings=settings,
        provider_name=provider_name,
        model=model,
        session_id=None,
    )
    explicit_selection = provider_name is not None or model is not None
    selected_provider = provider_name if explicit_selection else record.provider_name
    selected_model = model if explicit_selection else record.model
    try:
        selection = resolve_provider_selection(
            settings, provider_name=selected_provider, model=selected_model
        )
    except ProviderConfigError:
        if (selected_provider or settings.default_provider) != "openai-codex":
            raise
        # Bootstrap with the static default; the staged loader discovers and
        # validates the requested/resumed live-only model before activating it.
        selection = resolve_provider_selection(settings, provider_name="openai-codex")
    inference_provider = (
        record.inference_provider
        if resume_session_id is not None
        and record.provider_name == "huggingface"
        and selection.provider.name == "huggingface"
        and record.model == selection.model
        else selection.provider.inference_providers.get(selection.model)
        or selection.provider.default_inference_provider
        if isinstance(selection.provider, OpenAICompatibleProviderConfig)
        and selection.provider.name == "huggingface"
        else None
    )
    inference_provider_mode = (
        record.inference_provider_mode
        if resume_session_id is not None
        and record.provider_name == "huggingface"
        and selection.provider.name == "huggingface"
        and record.model == selection.model
        else "fixed"
        if inference_provider is not None
        else "automatic"
    )
    provider = create_model_provider(
        selection.provider,
        model=selection.model,
        inference_provider=inference_provider,
        thinking_level=resolve_startup_thinking_level(
            selection.provider,
            selection.model,
            cli_override=thinking_level_override,
        ),
    )
    session = await CodingSession.load(
        CodingSessionConfig(
            provider=provider,
            model=selected_model or selection.model,
            requested_provider=selected_provider if explicit_selection else None,
            requested_model=selected_model if explicit_selection else None,
            session_provider_name=record.provider_name,
            thinking_level_override=thinking_level_override,
            cwd=record.cwd,
            storage=jsonl_session_storage(record.path),
            session_id=record.id,
            session_manager=manager,
            provider_name=selection.provider.name,
            inference_provider=inference_provider,
            inference_provider_mode=inference_provider_mode,
            provider_settings=settings,
            runtime_provider_config=selection.provider,
            shell_command_prefix=shell_settings.shell_command_prefix,
            shell=shell_settings.shell,
            extension_paths=extension_paths,
            extensions_enabled=extensions_enabled,
            project_extensions_enabled=project_extensions_enabled,
            custom_system_prompt=custom_system_prompt,
            append_system_prompt=append_system_prompt,
            trust_override=trust_override,
            trust_default=shell_settings.default_project_trust,
        )
    )
    session.extension_runtime.set_ui_bridge(StderrUiBridge())
    try:
        await RpcServer(session).run()
    finally:
        await provider.aclose()


__all__ = ["run_openai_rpc_mode"]
