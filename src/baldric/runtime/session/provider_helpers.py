"""Persistent coding-session wrapper built on AgentHarness."""

from __future__ import annotations

import string
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from os import environ
from typing import TYPE_CHECKING, Any, cast

from baldric.ai.model_catalog import ModelCatalogProvider, RuntimeModelCatalog
from baldric.protocol.messages import (
    BashExecutionMessage,
    bash_execution_text,
)
from baldric.protocol.tools import AgentTool
from baldric.runtime.auth.credentials import FileCredentialStore
from baldric.runtime.context.thinking import (
    ThinkingLevel,
    normalize_thinking_level,
)
from baldric.runtime.extensions.provider_registry import DynamicProviderRegistry
from baldric.runtime.extensions.providers import DynamicProvider
from baldric.runtime.providers.config import (
    OpenAICodexProviderConfig,
    OpenAICompatibleProviderConfig,
    ProviderConfig,
    ProviderConfigError,
    provider_default_thinking_level,
    provider_model_supports_images,
    provider_thinking_levels,
    resolve_provider_selection,
    resolve_startup_thinking_level,
    validate_provider_model,
)
from baldric.runtime.providers.runtime import (
    ClosableModelProvider,
    create_dynamic_model_provider,
)
from baldric.runtime.session import SessionState
from baldric.runtime.session.manager import (
    InferenceProviderMode,
)

if TYPE_CHECKING:
    from baldric.runtime.session.session import CodingSession, CodingSessionConfig

from baldric.runtime.session.resource_helpers import _provider_with_runtime_model_catalog


def _session_module() -> Any:
    import baldric.runtime.session.session as session_module

    return session_module


@dataclass(frozen=True, slots=True)
class _PreparedProvider:
    """A runtime candidate built after the destination environment is trusted."""

    provider: ClosableModelProvider
    provider_name: str
    model: str
    inference_provider: str | None
    inference_provider_mode: InferenceProviderMode
    runtime_provider_config: ProviderConfig | None
    dynamic_provider: DynamicProvider | None
    runtime_model_catalog: RuntimeModelCatalog | None = None


async def _prepare_provider_selection(
    config: CodingSessionConfig,
    *,
    state: SessionState,
    provider_registry: DynamicProviderRegistry,
    credential_store: FileCredentialStore | None = None,
) -> _PreparedProvider:
    """Resolve and construct the provider after extension/project staging."""
    requested_provider = config.requested_provider
    requested_model = config.requested_model
    provider_name = requested_provider or state.provider or config.session_provider_name
    explicit = requested_provider is not None or requested_model is not None

    if provider_name is not None:
        effective = provider_registry.effective(provider_name)
        if effective is not None and isinstance(effective.definition, DynamicProvider):
            dynamic = effective.definition
            model = requested_model
            if model is None and state.provider == provider_name:
                model = state.model
            if model is None:
                model = dynamic.default_model
            if model is None and len(dynamic.models) == 1:
                model = dynamic.models[0].id
            if (
                (model is None or not any(item.id == model for item in dynamic.models))
                and dynamic.refresh_models is not None
                and (explicit or state.provider == provider_name)
            ):
                refreshed = await provider_registry.refresh(
                    provider_name,
                    allow_network=True,
                    timeout_seconds=5.0,
                )
                if refreshed.provider is not None:
                    dynamic = refreshed.provider
                if model is None:
                    model = dynamic.default_model
                    if model is None and len(dynamic.models) == 1:
                        model = dynamic.models[0].id
            if model is None:
                raise ProviderConfigError(
                    f"Provider {provider_name} has no selectable models; refresh it explicitly."
                )
            selected = next((item for item in dynamic.models if item.id == model), None)
            if selected is None:
                raise ProviderConfigError(f"Model is not available for provider {provider_name}: {model}")
            try:
                runtime = await create_dynamic_model_provider(
                    dynamic,
                    model=model,
                    credential_store=provider_registry.credentials,
                    environment=provider_registry.environment,
                )
            except (ProviderConfigError, RuntimeError) as exc:
                raise ProviderConfigError(str(exc)) from exc
            return _PreparedProvider(
                provider=runtime,
                provider_name=provider_name,
                model=model,
                inference_provider=None,
                inference_provider_mode="automatic",
                runtime_provider_config=None,
                dynamic_provider=dynamic,
            )

    settings = config.provider_settings
    discovered_catalog: RuntimeModelCatalog | None = None
    if settings is None:
        raise ProviderConfigError(
            f"Provider is not available after trusted extension loading: {provider_name or config.model}"
        )
    selected_model = requested_model or (state.model if state.provider == provider_name else None)
    selected_provider = settings.get_provider(provider_name or settings.default_provider)
    if (
        isinstance(selected_provider, OpenAICodexProviderConfig)
        and selected_model is not None
        and selected_model not in selected_provider.models
        and environ.get("BALDRIC_OFFLINE") is None
    ):
        # Live-only explicit/resumed models need discovery before static validation.
        discovery_provider = None
        try:
            discovery_provider = _session_module().create_model_provider(
                selected_provider,
                credential_store=credential_store,
                model=None,
                thinking_level=None,
            )
            if isinstance(discovery_provider, ModelCatalogProvider):
                catalog = await discovery_provider.discover_models()
                if catalog.models:
                    discovered_catalog = catalog
                    live_provider = _provider_with_runtime_model_catalog(selected_provider, catalog)
                    settings = replace(
                        settings,
                        providers=tuple(
                            live_provider if item.name == selected_provider.name else item
                            for item in settings.providers
                        ),
                    )
        except Exception:  # noqa: BLE001 - retain ordinary static validation on failure
            pass
        finally:
            if discovery_provider is not None:
                await discovery_provider.aclose()
    selection = resolve_provider_selection(
        settings,
        provider_name=provider_name,
        model=selected_model,
    )
    inference_provider = _session_inference_provider(
        config,
        state,
        selection.provider.name,
        selection.model,
    )
    inference_provider_mode = _session_inference_provider_mode(
        config,
        state,
        selection.provider,
        selection.model,
        inference_provider,
    )
    try:
        runtime = _create_runtime_provider(
            selection.provider,
            credential_store=credential_store,
            model=selection.model,
            inference_provider=inference_provider,
            thinking_level=resolve_startup_thinking_level(
                selection.provider,
                selection.model,
            ),
        )
    except RuntimeError as exc:
        raise ProviderConfigError(str(exc)) from exc
    return _PreparedProvider(
        provider=runtime,
        provider_name=selection.provider.name,
        model=selection.model,
        inference_provider=inference_provider,
        inference_provider_mode=inference_provider_mode,
        runtime_provider_config=selection.provider,
        dynamic_provider=None,
        runtime_model_catalog=discovered_catalog,
    )


def _session_inference_provider(
    config: CodingSessionConfig,
    state: SessionState,
    provider_name: str,
    model: str,
) -> str | None:
    """Preserve HF routing only for the same logical provider/model."""
    if provider_name != "huggingface":
        return None
    if state.provider == provider_name and state.model == model:
        return config.inference_provider
    provider = config.provider_settings.get_provider(provider_name) if config.provider_settings else None
    if isinstance(provider, OpenAICompatibleProviderConfig):
        return provider.inference_providers.get(model) or provider.default_inference_provider
    return None


def _session_inference_provider_mode(
    config: CodingSessionConfig,
    state: SessionState,
    provider: ProviderConfig,
    model: str,
    inference_provider: str | None,
) -> InferenceProviderMode:
    """Preserve automatic/fixed HF routing for the same resumed model."""
    if provider.name != "huggingface":
        return "automatic"
    if state.provider == provider.name and state.model == model:
        return config.inference_provider_mode or ("fixed" if inference_provider is not None else "automatic")
    return _configured_inference_provider_mode(provider, model)


def _filter_tools(tools: Sequence[AgentTool], allowed_tool_names: frozenset[str] | None) -> list[AgentTool]:
    """Apply ``CodingSessionConfig.allowed_tool_names`` to a composed tool list."""
    if allowed_tool_names is None:
        return list(tools)
    return [tool for tool in tools if tool.name in allowed_tool_names]


def _configured_model_supports_images(config: CodingSessionConfig, model: str) -> bool | None:
    if config.dynamic_provider is not None:
        selected = next((item for item in config.dynamic_provider.models if item.id == model), None)
        if selected is None or selected.input_modalities is None:
            return None
        return "image" in selected.input_modalities
    provider = config.runtime_provider_config
    if provider is None and config.provider_settings is not None:
        try:
            provider = config.provider_settings.get_provider(config.provider_name)
        except ProviderConfigError:
            return None
    return provider_model_supports_images(provider, model) if provider is not None else None


def _initial_model_for_config(config: CodingSessionConfig) -> str:
    if config.provider_settings is None or config.runtime_provider_config is None:
        return config.model
    provider = _provider_config_for_name(config, config.provider_name)
    if provider is None:
        return config.model
    try:
        validate_provider_model(provider, config.model)
    except ProviderConfigError:
        return provider.default_model
    return config.model


def _runtime_model_for_state(config: CodingSessionConfig, state: SessionState) -> str:
    state_model = state.model or config.model
    if config.dynamic_provider is not None:
        return config.model
    if config.provider_settings is None or config.runtime_provider_config is None:
        return state_model
    provider = _provider_config_for_name(config, config.provider_name)
    if provider is None:
        return state_model
    try:
        validate_provider_model(provider, state_model)
    except ProviderConfigError:
        return config.model if config.model in provider.models else provider.default_model
    return state_model


def _initial_thinking_level_for_config(
    config: CodingSessionConfig,
    *,
    model: str,
) -> ThinkingLevel:
    provider = _provider_config_for_name(config, config.provider_name)
    if config.thinking_level_override is not None:
        if provider is None:
            return config.thinking_level_override
        resolved = resolve_startup_thinking_level(
            provider,
            model,
            cli_override=config.thinking_level_override,
        )
        if resolved is not None:
            return resolved
    if provider is None:
        return config.thinking_level
    return _preferred_thinking_level_for_model(
        provider,
        model=model,
        fallback=config.thinking_level,
    )


def _provider_config_for_name(
    config: CodingSessionConfig,
    provider_name: str,
) -> ProviderConfig | None:
    if (
        isinstance(config.runtime_provider_config, OpenAICodexProviderConfig)
        and config.runtime_provider_config.name == provider_name
    ):
        return config.runtime_provider_config
    if config.provider_settings is not None:
        try:
            return config.provider_settings.get_provider(provider_name)
        except ProviderConfigError:
            pass
    if config.runtime_provider_config is not None:
        return config.runtime_provider_config
    return None


def _state_thinking_level(
    state: SessionState,
    default: ThinkingLevel,
) -> ThinkingLevel:
    thinking_level = getattr(state, "thinking_level", None)
    if thinking_level is None:
        return default
    return normalize_thinking_level(thinking_level)


def _create_runtime_provider(
    provider: ProviderConfig,
    *,
    credential_store: FileCredentialStore | None,
    model: str,
    thinking_level: ThinkingLevel | None,
    inference_provider: str | None,
    response_headers_observer: Callable[[Mapping[str, str]], None] | None = None,
) -> ClosableModelProvider:
    if inference_provider is None and response_headers_observer is None:
        return cast(
            ClosableModelProvider,
            _session_module().create_model_provider(
                provider,
                credential_store=credential_store,
                model=model,
                thinking_level=thinking_level,
            ),
        )
    if inference_provider is None:
        return cast(
            ClosableModelProvider,
            _session_module().create_model_provider(
                provider,
                credential_store=credential_store,
                model=model,
                thinking_level=thinking_level,
                response_headers_observer=response_headers_observer,
            ),
        )
    return cast(
        ClosableModelProvider,
        _session_module().create_model_provider(
            provider,
            credential_store=credential_store,
            model=model,
            thinking_level=thinking_level,
            inference_provider=inference_provider,
            response_headers_observer=response_headers_observer,
        ),
    )


def _terminal_command_context_message(command: str, output: str) -> str:
    """Return the model-facing text for one persisted bash execution."""
    return bash_execution_text(BashExecutionMessage(command=command, output=output))


def _configured_inference_provider(
    provider: ProviderConfig | None,
    model: str,
) -> str | None:
    if not isinstance(provider, OpenAICompatibleProviderConfig) or provider.name != "huggingface":
        return None
    return provider.inference_providers.get(model) or provider.default_inference_provider


def _configured_inference_provider_mode(
    provider: ProviderConfig | None,
    model: str,
) -> InferenceProviderMode:
    return "fixed" if _configured_inference_provider(provider, model) is not None else "automatic"


def _default_thinking_level_for_active_model(session: CodingSession) -> ThinkingLevel:
    provider = session._active_provider_config()
    if provider is None:
        return session._config.thinking_level
    return _preferred_thinking_level_for_model(
        provider,
        model=session.model,
        fallback=session._config.thinking_level,
    )


def _preferred_thinking_level_for_model(
    provider: ProviderConfig,
    *,
    model: str,
    fallback: ThinkingLevel,
) -> ThinkingLevel:
    levels = provider_thinking_levels(provider, model=model)
    preferred = provider.thinking_defaults.get(model)
    if preferred in levels:
        return preferred
    if fallback in levels or not levels:
        return fallback
    default = provider_default_thinking_level(provider, model=model)
    return default or levels[0]


def _coerced_thinking_level(
    provider: ProviderConfig,
    *,
    model: str,
    current: ThinkingLevel,
    preferred: ThinkingLevel | None = None,
) -> ThinkingLevel:
    levels = provider_thinking_levels(provider, model=model)
    if not levels or current in levels:
        return current
    if preferred in levels:
        return preferred
    default = provider_default_thinking_level(provider, model=model)
    return default or levels[0]


def _unavailable_thinking_message(session: CodingSession) -> str:
    message = f"Thinking controls are unavailable for {session.provider_name}:{session.model}"
    reason = session.thinking_unavailable_reason
    if reason:
        return f"{message}: {reason}"
    return message


def _sanitize_session_name(text: str) -> str | None:
    cleaned = " ".join(text.split()).strip()
    cleaned = cleaned.strip("\"'`“”‘’")
    cleaned = cleaned.strip(string.punctuation + " ")
    words = [word.strip(string.punctuation + "\"'`“”‘’") for word in cleaned.split()]
    words = [word for word in words if word]
    if not words:
        return None
    return " ".join(words[:4])


def _fallback_session_name(first_message: str) -> str | None:
    return _sanitize_session_name(first_message)
