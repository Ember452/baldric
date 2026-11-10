"""Model-runtime logic for CodingSession: provider build, failover, limits, cost."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import suppress
from dataclasses import replace
from os import environ
from typing import TYPE_CHECKING

from baldric.agent.events import AgentEndEvent, MessageEndEvent, ToolExecutionEndEvent
from baldric.ai.model_catalog import ModelCatalogProvider
from baldric.ai.model_limits import ModelLimitsProvider
from baldric.protocol.messages import (
    AssistantMessage,
)
from baldric.protocol.provider import ModelProvider
from baldric.runtime.events import (
    AutoRetryEndEvent,
    AutoRetryStartEvent,
    CodingSessionEvent,
    SessionAgentEndEvent,
)
from baldric.runtime.observability.diagnostics import (
    AgentCallDiagnosticContext,
)
from baldric.runtime.providers.config import (
    ProviderConfig,
    ProviderConfigError,
    validate_huggingface_inference_provider,
    validate_provider_model,
)
from baldric.runtime.providers.runtime import (
    ClosableModelProvider,
)
from baldric.runtime.session.provider_helpers import (
    _create_runtime_provider as _create_runtime_provider,
)
from baldric.runtime.session.provider_helpers import (
    _provider_config_for_name as _provider_config_for_name,
)
from baldric.runtime.session.tree_helpers import (
    is_context_overflow_error as is_context_overflow_error,
)
from baldric.runtime.session.tree_helpers import (
    is_retryable_huggingface_route_error as is_retryable_huggingface_route_error,
)

if TYPE_CHECKING:
    from baldric.runtime.session.session import CodingSession


async def run_huggingface_route_failover(
    session: CodingSession,
    *,
    context: AgentCallDiagnosticContext,
) -> AsyncIterator[CodingSessionEvent]:
    """Retry the interrupted run once through unsuffixed Hugging Face routing."""
    failed_route = session._reset_automatic_inference_provider_for_failover()
    retry_start = AutoRetryStartEvent(
        attempt=1,
        max_attempts=1,
        delay_ms=0,
        error_message=f"Hugging Face route {failed_route} failed; rerouting automatically",
    )
    await session._extension_runtime.emit_event(retry_start)
    yield retry_start

    retry_events = session._harness.continue_()
    session._invalidate_context_usage_cache()
    final_error: str | None = None
    try:
        async for retry_event in retry_events:
            if isinstance(retry_event, ToolExecutionEndEvent):
                session._invalidate_context_usage_cache()
            if (
                isinstance(retry_event, MessageEndEvent)
                and isinstance(retry_event.message, AssistantMessage)
                and retry_event.message.stop_reason in {"error", "aborted"}
            ):
                final_error = retry_event.message.error_message or "Provider request aborted"
                if retry_event.message.stop_reason == "error":
                    session._last_diagnostic_log_path = session._diagnostic_logger.log_assistant_error(
                        context=context,
                        phase="agent_loop_route_failover",
                        message=retry_event.message,
                    )
            if isinstance(retry_event, AgentEndEvent):
                yield SessionAgentEndEvent(
                    messages=retry_event.messages,
                    will_retry=False,
                )
            else:
                yield retry_event
    finally:
        aclose = getattr(retry_events, "aclose", None)
        if aclose is not None:
            with suppress(Exception):
                await aclose()

    failover_succeeded = final_error is None
    session._last_diagnostic_log_path = session._diagnostic_logger.log_huggingface_route_failover(
        context=context,
        failed_route=failed_route,
        replacement_route=session._inference_provider,
        success=failover_succeeded,
        error_message=final_error,
    )
    retry_end = AutoRetryEndEvent(
        success=failover_succeeded,
        attempt=1,
        final_error=final_error,
    )
    await session._extension_runtime.emit_event(retry_end)
    yield retry_end


def observe_response_headers(session: CodingSession, headers: Mapping[str, str]) -> None:
    if (
        session.provider_name != "huggingface"
        or session._inference_provider_mode != "automatic"
        or session._inference_provider is not None
    ):
        return
    route = next(
        (value for key, value in headers.items() if key.casefold() == "x-inference-provider"),
        None,
    )
    if route is None:
        return
    try:
        route = validate_huggingface_inference_provider(route)
    except ProviderConfigError:
        return
    provider, provider_config = session._build_runtime_provider(
        inference_provider=route,
    )
    # Track staged providers immediately so a later index-write failure does
    # not leak a provider-owned client. The active runtime remains unchanged.
    session._owned_providers.append(provider)
    if session._config.session_manager is not None and session._config.session_id is not None:
        session._config.session_manager.touch_session(
            session._config.session_id,
            model=session.model,
            provider_name=session.provider_name,
            inference_provider=route,
            inference_provider_mode="automatic",
            preserve_inference_provider=False,
        )
    session._inference_provider = route
    session._config = replace(
        session._config,
        inference_provider=route,
        inference_provider_mode="automatic",
    )
    session._activate_runtime_provider(provider, provider_config)


async def refresh_runtime_model_limits(session: CodingSession) -> None:
    key = (session.provider_name, session.model)
    if session._runtime_model_limits_key == key:
        return
    session._runtime_model_limits = None
    session._runtime_model_limits_key = key
    session._model_limits_discovery_error = None
    provider = session._harness.config.provider
    if (
        session.provider_name == "openai-codex"
        and isinstance(provider, ModelCatalogProvider)
        and environ.get("BALDRIC_OFFLINE") is not None
    ):
        return
    try:
        cached_catalog = session._runtime_model_catalogs.get(session.provider_name)
        if session.provider_name == "openai-codex" and cached_catalog is not None:
            model = cached_catalog.model(session.model)
            session._runtime_model_limits = model.limits if model is not None else None
            return
        if isinstance(provider, ModelCatalogProvider):
            catalog = await provider.discover_models()
            session._publish_runtime_model_catalog(session.provider_name, catalog)
            if session.provider_name == "openai-codex":
                session._persist_codex_model_catalog(provider, catalog)
        if isinstance(provider, ModelLimitsProvider):
            session._runtime_model_limits = await provider.discover_model_limits(session.model)
    except Exception as exc:  # static catalog remains the safe fallback
        error = f"{type(exc).__name__}: {exc}"
        session._model_limits_discovery_error = error
        if isinstance(provider, ModelCatalogProvider):
            session._model_catalog_discovery_errors[session.provider_name] = error


def pricing_for_response(
    session: CodingSession,
    provider_name: str,
    model: str,
    input_tokens: int,
) -> dict[str, float] | None:
    provider = _provider_config_for_name(session._config, provider_name)
    if provider is None or provider.name != provider_name or not hasattr(provider, "model_metadata"):
        return None
    metadata = provider.model_metadata.get(model)
    if metadata is None:
        return None
    for tier in metadata.cost_tiers:
        if tier.max_input_tokens is None or input_tokens <= tier.max_input_tokens:
            return dict(tier.cost)
    return dict(metadata.cost) if metadata.cost else None


def reset_automatic_inference_provider_for_failover(session: CodingSession) -> str:
    failed_route = session._inference_provider
    if failed_route is None:
        raise ProviderConfigError("Hugging Face failover requires a pinned route")
    provider, provider_config = session._build_runtime_provider(inference_provider=None)
    session._owned_providers.append(provider)
    if session._config.session_manager is not None and session._config.session_id is not None:
        session._config.session_manager.touch_session(
            session._config.session_id,
            model=session.model,
            provider_name=session.provider_name,
            inference_provider=None,
            inference_provider_mode="automatic",
            preserve_inference_provider=False,
        )
    session._inference_provider = None
    session._config = replace(
        session._config,
        inference_provider=None,
        inference_provider_mode="automatic",
    )
    session._activate_runtime_provider(provider, provider_config)
    return failed_route


def build_runtime_provider(
    session: CodingSession,
    *,
    inference_provider: str | None,
) -> tuple[ClosableModelProvider, ProviderConfig]:
    if session._runtime_provider_config is None:
        raise ProviderConfigError("Runtime provider configuration is unavailable")
    provider_config = session._active_provider_config() or session._runtime_provider_config
    committed_model = session._harness.config.model
    validate_provider_model(provider_config, committed_model)
    try:
        provider = _create_runtime_provider(
            provider_config,
            credential_store=session._credential_store,
            model=committed_model,
            thinking_level=session._thinking_level,
            inference_provider=inference_provider,
            response_headers_observer=(
                session._observe_response_headers if provider_config.name == "huggingface" else None
            ),
        )
    except RuntimeError as exc:
        raise ProviderConfigError(str(exc)) from exc
    return provider, provider_config


def activate_runtime_provider(
    session: CodingSession,
    provider: ClosableModelProvider,
    provider_config: ProviderConfig,
) -> None:
    session._harness.config.provider = session._apply_provider_hooks(provider)
    session._runtime_provider_config = provider_config
    session._invalidate_runtime_model_limits()


def refresh_runtime_provider(session: CodingSession) -> None:
    if session._runtime_provider_config is None:
        return
    provider, provider_config = session._build_runtime_provider(
        inference_provider=session._inference_provider,
    )
    session._owned_providers.append(provider)
    session._activate_runtime_provider(provider, provider_config)


def invalidate_runtime_model_limits(session: CodingSession) -> None:
    session._runtime_model_limits = None
    session._runtime_model_limits_key = None
    session._model_limits_discovery_error = None


def should_auto_failover_huggingface_route(
    session: CodingSession,
    message: AssistantMessage,
) -> bool:
    return (
        session.provider_name == "huggingface"
        and session._inference_provider_mode == "automatic"
        and session._inference_provider is not None
        and is_retryable_huggingface_route_error(message)
    )


def will_auto_retry(session: CodingSession, message: AssistantMessage) -> bool:
    """Return whether session orchestration will retry this assistant error."""
    return (
        message.is_tool_result_recovery
        or is_context_overflow_error(message)
        or session._should_auto_failover_huggingface_route(message)
    )


async def close_replaced_provider(session: CodingSession, provider: ModelProvider) -> None:
    """Close a Baldric-owned provider once after a committed publication."""
    if provider not in session._owned_providers:
        return
    session._owned_providers.remove(provider)
    close = getattr(provider, "aclose", None)
    if close is not None:
        await close()
