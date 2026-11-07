"""Persistent coding-session wrapper built on AgentHarness."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal

from baldric_agent.session import (
    ModelChangeEntry,
    ThinkingLevelChangeEntry,
)
from baldric_coding.context.resources import (
    ResourceDiagnostic,
)
from baldric_coding.context.thinking import (
    DEFAULT_THINKING_LEVEL,
    next_thinking_level,
    normalize_thinking_level,
)
from baldric_coding.events import (
    ThinkingLevelChangedEvent,
)
from baldric_coding.extensions.providers import DynamicProvider
from baldric_coding.providers.config import (
    OpenAICodexProviderConfig,
    ProviderConfig,
    ProviderConfigError,
    provider_model_supports_images,
    provider_thinking_levels,
    resolve_startup_thinking_level,
    save_default_provider_model,
    save_provider_thinking_level,
    toggle_saved_scoped_model,
    toggle_saved_stable_scoped_model,
    validate_huggingface_inference_provider,
    validate_provider_model,
)
from baldric_coding.providers.runtime import (
    ClosableModelProvider,
    create_dynamic_model_provider,
)
from baldric_coding.session.compaction.context_window import (
    DEFAULT_COMPACTION_KEEP_RECENT_TOKENS as DEFAULT_COMPACTION_KEEP_RECENT_TOKENS,
)
from baldric_coding.session.manager import (
    InferenceProviderMode,
)
from baldric_coding.session.provider_helpers import (  # noqa: F401
    _coerced_thinking_level as _coerced_thinking_level,
)
from baldric_coding.session.provider_helpers import (
    _configured_inference_provider as _configured_inference_provider,
)
from baldric_coding.session.provider_helpers import (
    _configured_inference_provider_mode as _configured_inference_provider_mode,
)
from baldric_coding.session.provider_helpers import (
    _configured_model_supports_images as _configured_model_supports_images,
)
from baldric_coding.session.provider_helpers import (
    _create_runtime_provider as _create_runtime_provider,
)
from baldric_coding.session.provider_helpers import (
    _default_thinking_level_for_active_model as _default_thinking_level_for_active_model,
)
from baldric_coding.session.provider_helpers import (
    _fallback_session_name as _fallback_session_name,
)
from baldric_coding.session.provider_helpers import (
    _filter_tools as _filter_tools,
)
from baldric_coding.session.provider_helpers import (
    _initial_model_for_config as _initial_model_for_config,
)
from baldric_coding.session.provider_helpers import (
    _initial_thinking_level_for_config as _initial_thinking_level_for_config,
)
from baldric_coding.session.provider_helpers import (
    _preferred_thinking_level_for_model as _preferred_thinking_level_for_model,
)
from baldric_coding.session.provider_helpers import (
    _prepare_provider_selection as _prepare_provider_selection,
)
from baldric_coding.session.provider_helpers import (
    _provider_config_for_name as _provider_config_for_name,
)
from baldric_coding.session.provider_helpers import (
    _runtime_model_for_state as _runtime_model_for_state,
)
from baldric_coding.session.provider_helpers import (
    _sanitize_session_name as _sanitize_session_name,
)
from baldric_coding.session.provider_helpers import (
    _session_inference_provider as _session_inference_provider,
)
from baldric_coding.session.provider_helpers import (
    _session_inference_provider_mode as _session_inference_provider_mode,
)
from baldric_coding.session.provider_helpers import (
    _state_thinking_level as _state_thinking_level,
)
from baldric_coding.session.provider_helpers import (
    _unavailable_thinking_message as _unavailable_thinking_message,
)
from baldric_coding.session.resource_helpers import (  # noqa: F401
    SessionResources as SessionResources,
)
from baldric_coding.session.resource_helpers import (
    TerminalCommandRequest as TerminalCommandRequest,
)
from baldric_coding.session.resource_helpers import (
    _append_prompt_sections as _append_prompt_sections,
)
from baldric_coding.session.resource_helpers import (
    _append_session_entry_sync as _append_session_entry_sync,
)
from baldric_coding.session.resource_helpers import (
    _category_summary as _category_summary,
)
from baldric_coding.session.resource_helpers import (
    _codex_account_id as _codex_account_id,
)
from baldric_coding.session.resource_helpers import (
    _context_file_signatures as _context_file_signatures,
)
from baldric_coding.session.resource_helpers import (
    _custom_prompt_source as _custom_prompt_source,
)
from baldric_coding.session.resource_helpers import (
    _diagnostic_signatures as _diagnostic_signatures,
)
from baldric_coding.session.resource_helpers import (
    _extension_signatures as _extension_signatures,
)
from baldric_coding.session.resource_helpers import (
    _load_session_resources as _load_session_resources,
)
from baldric_coding.session.resource_helpers import (
    _merge_context_files as _merge_context_files,
)
from baldric_coding.session.resource_helpers import (
    _prompt_template_signatures as _prompt_template_signatures,
)
from baldric_coding.session.resource_helpers import (
    _provider_config_or_none as _provider_config_or_none,
)
from baldric_coding.session.resource_helpers import (
    _provider_settings_with_runtime_catalogs as _provider_settings_with_runtime_catalogs,
)
from baldric_coding.session.resource_helpers import (
    _provider_with_runtime_model_catalog as _provider_with_runtime_model_catalog,
)
from baldric_coding.session.resource_helpers import (
    _runtime_model_thinking_defaults as _runtime_model_thinking_defaults,
)
from baldric_coding.session.resource_helpers import (
    _runtime_provider_model_metadata as _runtime_provider_model_metadata,
)
from baldric_coding.session.resource_helpers import (
    _skill_signatures as _skill_signatures,
)
from baldric_coding.session.resource_helpers import (
    _system_prompt_resource_signatures as _system_prompt_resource_signatures,
)
from baldric_coding.session.resource_helpers import (
    _tool_history_repair_plan as _tool_history_repair_plan,
)
from baldric_coding.session.resource_helpers import (
    default_session_path as default_session_path,
)
from baldric_coding.session.resource_helpers import (
    jsonl_session_storage as jsonl_session_storage,
)
from baldric_coding.session.resource_helpers import (
    parse_terminal_command as parse_terminal_command,
)
from baldric_coding.session.tree_helpers import (  # noqa: F401
    _active_branchable_entry_id as _active_branchable_entry_id,
)
from baldric_coding.session.tree_helpers import (
    _custom_message_from_entry as _custom_message_from_entry,
)
from baldric_coding.session.tree_helpers import (
    _detach_missing_parents as _detach_missing_parents,
)
from baldric_coding.session.tree_helpers import (
    _first_recent_context_index as _first_recent_context_index,
)
from baldric_coding.session.tree_helpers import (
    _is_branchable_tree_entry as _is_branchable_tree_entry,
)
from baldric_coding.session.tree_helpers import (
    _is_tool_call_tree_entry as _is_tool_call_tree_entry,
)
from baldric_coding.session.tree_helpers import (
    _last_parent_id_from_state as _last_parent_id_from_state,
)
from baldric_coding.session.tree_helpers import (
    _last_user_message_index as _last_user_message_index,
)
from baldric_coding.session.tree_helpers import (
    _message_text_preview as _message_text_preview,
)
from baldric_coding.session.tree_helpers import (
    _messages_after_entry_on_active_path as _messages_after_entry_on_active_path,
)
from baldric_coding.session.tree_helpers import (
    _next_user_message_index as _next_user_message_index,
)
from baldric_coding.session.tree_helpers import (
    _ordered_tree_entries as _ordered_tree_entries,
)
from baldric_coding.session.tree_helpers import (
    _resolve_export_destination as _resolve_export_destination,
)
from baldric_coding.session.tree_helpers import (
    _resolved_labels as _resolved_labels,
)
from baldric_coding.session.tree_helpers import (
    _session_entry_for_message as _session_entry_for_message,
)
from baldric_coding.session.tree_helpers import (
    _session_export_title as _session_export_title,
)
from baldric_coding.session.tree_helpers import (
    _short_preview as _short_preview,
)
from baldric_coding.session.tree_helpers import (
    _storage_path as _storage_path,
)
from baldric_coding.session.tree_helpers import (
    _tree_branch_indents as _tree_branch_indents,
)
from baldric_coding.session.tree_helpers import (
    _tree_choice_label as _tree_choice_label,
)
from baldric_coding.session.tree_helpers import (
    _tree_entry_title as _tree_entry_title,
)
from baldric_coding.session.tree_helpers import (
    _tree_layout as _tree_layout,
)
from baldric_coding.session.tree_helpers import (
    is_context_overflow_error as is_context_overflow_error,
)
from baldric_coding.session.tree_helpers import (
    is_retryable_huggingface_route_error as is_retryable_huggingface_route_error,
)

if TYPE_CHECKING:
    from baldric_coding.session.session import CodingSession

StreamingBehavior = Literal["steer", "follow_up"]
SESSION_NAME_SYSTEM_PROMPT = (
    "You write concise coding-agent session names. Reply with only a short title, "
    "maximum four words, no quotes, no punctuation-only output."
)
TREE_RUNNING_MESSAGE = "Baldric is still working. Press Escape to interrupt before using /tree."


@dataclass(frozen=True, slots=True)
class ModelChoice:
    """A selectable model and the provider that serves it."""

    provider_name: str
    model: str


@dataclass(frozen=True, slots=True)
class ModelSelectionResult:
    """Result of a candidate-first provider/model selection."""

    choice: ModelChoice
    changed: bool


def set_model(session: CodingSession, model: str) -> None:
    """Switch the active model for future turns and make it the default."""
    provider = session._active_provider_config()
    if provider is not None:
        validate_provider_model(provider, model)
    session._harness.config.model = model
    session._inference_provider = _configured_inference_provider(provider, model)
    session._inference_provider_mode = _configured_inference_provider_mode(provider, model)
    session._sync_thinking_level_to_active_model()
    session._refresh_runtime_provider()
    session._sync_image_support()
    session._persist_default_model_choice()
    if session._config.session_id is not None and session._config.session_manager is not None:
        session._config.session_manager.touch_session(
            session._config.session_id,
            model=model,
            provider_name=session.provider_name,
            inference_provider=session._inference_provider,
            inference_provider_mode=session._inference_provider_mode,
            preserve_inference_provider=False,
        )


async def apply_startup_model_override(session: CodingSession, model: str) -> None:
    """Activate and persist an explicit startup model before the next turn."""
    provider = session._active_provider_config()
    if provider is not None:
        validate_provider_model(provider, model)
    if session.model == model:
        return

    session._harness.config.model = model
    session._inference_provider = _configured_inference_provider(provider, model)
    session._inference_provider_mode = _configured_inference_provider_mode(provider, model)
    session._sync_thinking_level_to_active_model()
    session._refresh_runtime_provider()
    session._sync_image_support()
    entry = ModelChangeEntry(
        parent_id=session._last_parent_id,
        model=model,
        provider=session.provider_name,
    )
    await session._append_session_entry(entry)
    session.set_active_leaf_id(entry.id)
    await session._refresh_persisted_state(leaf_id=entry.id)


async def select_provider_model(
    session: CodingSession, choice: ModelChoice, *, persist_default: bool = True
) -> ModelSelectionResult:
    """Switch provider/model with candidate-first durable publication.

    No active state changes until the candidate runtime exists and the
    provider-aware model entry is committed.
    """
    if session._harness.is_running:
        raise RuntimeError("Baldric is still working. Press Escape to interrupt before switching models.")
    if choice.provider_name == session.provider_name and choice.model == session.model:
        return ModelSelectionResult(choice, changed=False)

    candidate: ClosableModelProvider | None = None
    selected_dynamic: DynamicProvider | None = None
    selected_config: ProviderConfig | None = None
    selected_inference: str | None = None
    selected_inference_mode: InferenceProviderMode = "automatic"
    selected_thinking = session._thinking_level
    selected_image_support: bool | None = None
    try:
        effective = session._provider_registry.effective(choice.provider_name)
        if effective is not None and isinstance(effective.definition, DynamicProvider):
            selected_dynamic = effective.definition
            selected_model = next((item for item in selected_dynamic.models if item.id == choice.model), None)
            if selected_model is None:
                raise ProviderConfigError(
                    f"Model is not available for provider {choice.provider_name}: {choice.model}"
                )
            candidate = await create_dynamic_model_provider(
                selected_dynamic,
                model=choice.model,
                credential_store=session._credential_store,
            )
            if (
                selected_model.thinking_levels is not None
                and selected_thinking not in selected_model.thinking_levels
            ):
                selected_thinking = (
                    selected_model.thinking_levels[0]
                    if selected_model.thinking_levels
                    else DEFAULT_THINKING_LEVEL
                )
            selected_image_support = (
                "image" in selected_model.input_modalities
                if selected_model.input_modalities is not None
                else None
            )
        else:
            if session._provider_settings is None:
                raise ProviderConfigError(f"Provider is not available: {choice.provider_name}")
            selected_config = session._provider_settings.get_provider(choice.provider_name)
            validate_provider_model(selected_config, choice.model)
            selected_inference = _configured_inference_provider(selected_config, choice.model)
            selected_inference_mode = _configured_inference_provider_mode(selected_config, choice.model)
            selected_thinking = _coerced_thinking_level(
                selected_config,
                model=choice.model,
                current=session._thinking_level,
            )
            candidate = _create_runtime_provider(
                selected_config,
                credential_store=session._credential_store,
                model=choice.model,
                thinking_level=selected_thinking,
                inference_provider=selected_inference,
                response_headers_observer=(
                    session._observe_response_headers if selected_config.name == "huggingface" else None
                ),
            )
            selected_image_support = provider_model_supports_images(selected_config, choice.model)

        entry = ModelChangeEntry(
            parent_id=session._last_parent_id,
            model=choice.model,
            provider=choice.provider_name,
        )
        await session._append_session_entry(entry)
    except BaseException:
        if candidate is not None:
            await candidate.aclose()
        raise

    # From this point the transcript is authoritative. Only synchronous
    # assignments happen before control returns to the frontend.
    old_provider = session._harness.config.provider
    assert candidate is not None
    session._owned_providers.append(candidate)
    session._harness.config.provider = candidate
    session._harness.config.model = choice.model
    session._provider_name = choice.provider_name
    session._inference_provider = selected_inference
    session._inference_provider_mode = selected_inference_mode
    session._runtime_provider_config = selected_config
    session._config = replace(
        session._config,
        provider=candidate,
        model=choice.model,
        provider_name=choice.provider_name,
        inference_provider=selected_inference,
        inference_provider_mode=selected_inference_mode,
        runtime_provider_config=selected_config,
        dynamic_provider=selected_dynamic,
    )
    session.set_thinking_state(selected_thinking)
    session._image_support.supported = selected_image_support
    session.set_active_leaf_id(entry.id)
    session._invalidate_runtime_model_limits()
    session._invalidate_context_usage_cache()
    try:
        await session._refresh_persisted_state(leaf_id=entry.id)
    except Exception as exc:  # committed history wins over repairable index failure
        session._resource_diagnostics = (
            *session._resource_diagnostics,
            ResourceDiagnostic(
                kind="session-index",
                message=f"Committed model switch requires index repair: {type(exc).__name__}",
                severity="warning",
            ),
        )
    if old_provider is not candidate:
        with suppress(Exception):
            await session._close_replaced_provider(old_provider)
    if selected_config is not None and persist_default:
        session._persist_default_model_choice()
    return ModelSelectionResult(choice, changed=True)


def set_inference_provider(session: CodingSession, route: str | None) -> str:
    """Select or reset the active Hugging Face session route."""
    if session.provider_name != "huggingface":
        raise ProviderConfigError("Inference-provider routing requires the huggingface provider")
    normalized = validate_huggingface_inference_provider(route) if route is not None else None
    mode: InferenceProviderMode = "fixed" if normalized is not None else "automatic"
    provider, provider_config = session._build_runtime_provider(
        inference_provider=normalized,
    )
    session._owned_providers.append(provider)
    if session._config.session_manager is not None and session._config.session_id is not None:
        session._config.session_manager.touch_session(
            session._config.session_id,
            model=session.model,
            provider_name=session.provider_name,
            inference_provider=normalized,
            inference_provider_mode=mode,
            preserve_inference_provider=False,
        )
    session._inference_provider = normalized
    session._inference_provider_mode = mode
    session._config = replace(
        session._config,
        inference_provider=normalized,
        inference_provider_mode=mode,
    )
    session._activate_runtime_provider(provider, provider_config)
    return normalized or "automatic (will pin after the next successful response)"


def set_model_choice(session: CodingSession, choice: ModelChoice) -> None:
    """Switch provider/model as one operation."""
    if choice.provider_name == session.provider_name:
        session.set_model(choice.model)
        return
    session._set_provider_model(choice.provider_name, choice.model)


def is_scoped_model(session: CodingSession, choice: ModelChoice) -> bool:
    """Return whether a provider/model pair is in the scoped model list."""
    return choice in session.scoped_model_choices


def toggle_scoped_model(session: CodingSession, choice: ModelChoice) -> tuple[ModelChoice, ...]:
    """Add or remove a model from the persisted scoped model list."""
    if session._provider_settings is None:
        raise ProviderConfigError("Provider settings are not available for this session")
    available = set(session.available_model_choices)
    existing = choice in session.scoped_model_choices
    durable_settings = getattr(session, "_durable_provider_settings", session._provider_settings)
    effective = session._provider_registry.effective(choice.provider_name)
    if effective is not None and isinstance(effective.definition, DynamicProvider):
        if not (
            session._effective_stable_dynamic_scoped_provider(choice.provider_name)
            or (existing and session._stable_dynamic_scoped_provider(choice.provider_name))
        ):
            raise ProviderConfigError(
                "Only effective trusted built-in dynamic providers support scoped references"
            )
        if choice not in available and not existing:
            raise ProviderConfigError(f"Model is unavailable: {choice.provider_name}:{choice.model}")
        toggle = toggle_saved_stable_scoped_model
    else:
        if choice not in available:
            raise ProviderConfigError(f"Model is not available: {choice.provider_name}:{choice.model}")
        durable_provider = (
            durable_settings.get_provider(choice.provider_name) if durable_settings is not None else None
        )
        toggle = (
            toggle_saved_scoped_model
            if durable_provider is not None and choice.model in durable_provider.models
            else toggle_saved_stable_scoped_model
        )

    updated_settings = toggle(
        provider_name=choice.provider_name,
        model=choice.model,
        paths=session._resource_paths.paths,
        fallback_settings=durable_settings,
    )
    if hasattr(session, "_durable_provider_settings"):
        session._durable_provider_settings = updated_settings
        session._apply_runtime_model_catalogs()
    else:  # narrowly supports lightweight host/test session doubles
        session._provider_settings = updated_settings
    session._sync_thinking_level_to_active_model()
    return session.scoped_model_choices


def has_pending_selection(session: CodingSession) -> bool:
    """Whether a TUI selection has not yet been committed to history."""
    return session._preview_model is not None or session._preview_thinking is not None


def preview_model_choice(session: CodingSession, choice: ModelChoice) -> None:
    """Select a model for the next turn without constructing or persisting a provider."""
    if session._harness.is_running:
        raise RuntimeError("Cannot switch models while Baldric is working")
    if choice not in session.available_model_choices:
        raise ProviderConfigError(f"Model is not available: {choice.provider_name}:{choice.model}")
    session.set_preview_model(choice)
    levels = session.available_thinking_levels
    if not levels:
        session.set_preview_thinking("off")
    elif session.thinking_level not in levels:
        session.set_preview_thinking(levels[0])
    session._invalidate_runtime_model_limits()


def preview_thinking_level(session: CodingSession, level: str) -> str:
    """Select a thinking level for the next turn without touching durable settings."""
    normalized = normalize_thinking_level(level)
    levels = session.available_thinking_levels
    if not levels:
        raise ValueError(_unavailable_thinking_message(session))
    if normalized not in levels:
        raise ValueError(f"Thinking mode {normalized} is not available. Available: {', '.join(levels)}")
    session.set_preview_thinking(normalized)
    return f"Thinking mode: {normalized}"


def preview_cycle_thinking_level(session: CodingSession) -> str:
    return session.preview_thinking_level(
        next_thinking_level(session.thinking_level, available=session.available_thinking_levels)
    )


def preview_cycle_scoped_model(session: CodingSession, *, reverse: bool = False) -> ModelChoice:
    """Cycle through available scoped choices without changing durable state."""
    available = set(session.available_model_choices)
    scoped = tuple(choice for choice in session.scoped_model_choices if choice in available)
    if not scoped:
        raise ProviderConfigError("No scoped models configured.")
    current = ModelChoice(session.provider_name, session.model)
    try:
        index = scoped.index(current)
    except ValueError:
        index = 0 if reverse else -1
    choice = scoped[(index + (-1 if reverse else 1)) % len(scoped)]
    session.preview_model_choice(choice)
    return choice


async def _commit_preview(session: CodingSession) -> None:
    """Commit the final pending selection before the next accepted user turn."""
    choice, thinking = session._preview_model, session._preview_thinking
    if choice is None and thinking is None:
        return
    session.set_preview_model(None)
    session.set_preview_thinking(None)
    try:
        if choice is not None:
            await session.select_provider_model(choice, persist_default=False)
        if thinking is not None and thinking != session._state.thinking_level:
            if thinking == "off" and not session.available_thinking_levels:
                # A non-reasoning model has no effort control to rebuild.
                session.set_thinking_state("off")
            if thinking != session._thinking_level and session.available_thinking_levels:
                await session.set_thinking_level(thinking, persist_preference=False)
            elif thinking == session._thinking_level:
                # A model switch can clamp thinking before set_thinking_level
                # runs. Record that effective change on the same branch.
                entry = ThinkingLevelChangeEntry(parent_id=session._last_parent_id, thinking_level=thinking)
                await session._append_session_entry(entry)
                session.set_active_leaf_id(entry.id)
                await session._refresh_persisted_state(leaf_id=entry.id)
                session.queue_frontend_event(ThinkingLevelChangedEvent(level=thinking))
                await session._extension_runtime.emit_event(ThinkingLevelChangedEvent(level=thinking))
    except Exception:
        session.set_preview_model(choice)
        session.set_preview_thinking(thinking)
        raise


def cycle_scoped_model(session: CodingSession, *, reverse: bool = False) -> ModelChoice:
    """Switch to the next currently available configured scoped model."""
    available = set(session.available_model_choices)
    scoped = tuple(choice for choice in session.scoped_model_choices if choice in available)
    if not scoped:
        raise ProviderConfigError("No scoped models configured.")
    current = ModelChoice(provider_name=session.provider_name, model=session.model)
    try:
        current_index = scoped.index(current)
    except ValueError:
        current_index = -1 if not reverse else 0
    delta = -1 if reverse else 1
    choice = scoped[(current_index + delta) % len(scoped)]
    session.set_model_choice(choice)
    return choice


def set_provider(session: CodingSession, provider_name: str, *, persist_default: bool = True) -> None:
    """Switch the active provider and reset to that provider's default model."""
    if session._provider_settings is None:
        raise ProviderConfigError("Provider settings are not available for this session")
    provider_config = session._provider_settings.get_provider(provider_name)
    session._set_provider_model(
        provider_name,
        provider_config.default_model,
        persist_default=persist_default,
    )


def _set_provider_model(
    session: CodingSession, provider_name: str, model: str, *, persist_default: bool = True
) -> None:
    """Switch active provider/model without constructing an intermediate provider."""
    if session._provider_settings is None:
        raise ProviderConfigError("Provider settings are not available for this session")

    provider_config = session._provider_settings.get_provider(provider_name)
    if model not in provider_config.models:
        raise ProviderConfigError(f"Model is not configured: {provider_name}:{model}")
    thinking_level = _coerced_thinking_level(
        provider_config,
        model=model,
        current=session._thinking_level,
    )
    try:
        provider = _create_runtime_provider(
            provider_config,
            credential_store=session._credential_store,
            model=model,
            thinking_level=thinking_level,
            inference_provider=_configured_inference_provider(provider_config, model),
            response_headers_observer=(
                session._observe_response_headers if provider_config.name == "huggingface" else None
            ),
        )
    except RuntimeError as exc:
        raise ProviderConfigError(str(exc)) from exc
    session._owned_providers.append(provider)
    session._harness.config.provider = provider
    session._provider_name = provider_config.name
    session._inference_provider = _configured_inference_provider(provider_config, model)
    session._inference_provider_mode = _configured_inference_provider_mode(provider_config, model)
    session._runtime_provider_config = provider_config
    session._invalidate_runtime_model_limits()
    session._harness.config.model = model
    session.set_thinking_state(thinking_level)
    session._sync_image_support()
    if persist_default:
        session._persist_default_model_choice()
    if session._config.session_id is not None and session._config.session_manager is not None:
        session._config.session_manager.touch_session(
            session._config.session_id,
            model=model,
            provider_name=session.provider_name,
            inference_provider=session._inference_provider,
            inference_provider_mode=session._inference_provider_mode,
            preserve_inference_provider=False,
        )


async def set_thinking_level(session: CodingSession, level: str, *, persist_preference: bool = True) -> str:
    """Persist and activate a thinking mode for future turns."""
    normalized = normalize_thinking_level(level)
    available = session.available_thinking_levels
    if not available:
        raise ValueError(_unavailable_thinking_message(session))
    if normalized not in available:
        modes = ", ".join(available)
        raise ValueError(
            f"Thinking mode {normalized} is not available for "
            f"{session._provider_name}:{session.model}. Available modes: {modes}"
        )
    if normalized == session._thinking_level:
        return f"Thinking mode: {normalized}"

    previous = session._thinking_level
    session.set_thinking_state(normalized)
    try:
        session._refresh_runtime_provider()
    except ProviderConfigError:
        session.set_thinking_state(previous)
        raise

    entry = ThinkingLevelChangeEntry(
        parent_id=session._last_parent_id,
        thinking_level=normalized,
    )
    await session._append_session_entry(entry)
    session.set_active_leaf_id(entry.id)

    if persist_preference:
        session._persist_thinking_level_choice()
    await session._refresh_persisted_state(leaf_id=entry.id)
    session.queue_frontend_event(ThinkingLevelChangedEvent(level=normalized))
    await session._extension_runtime.emit_event(ThinkingLevelChangedEvent(level=normalized))
    return f"Thinking mode: {normalized}"


async def cycle_thinking_level(session: CodingSession) -> str:
    """Cycle to the next supported thinking mode and persist it."""
    return await session.set_thinking_level(
        next_thinking_level(
            session._thinking_level,
            available=session.available_thinking_levels,
        )
    )


def _selected_provider_config(session: CodingSession) -> ProviderConfig | None:
    """Resolve displayed capabilities without changing the committed runtime."""
    if session._preview_model is None:
        return session._active_provider_config()
    if session._provider_settings is None:
        return None
    try:
        return session._provider_settings.get_provider(session.provider_name)
    except ProviderConfigError:
        return None


def _active_provider_config(session: CodingSession) -> ProviderConfig | None:
    if session._provider_settings is None:
        return None
    try:
        provider = session._provider_settings.get_provider(session._provider_name)
    except ProviderConfigError:
        return None
    runtime = session._runtime_provider_config
    if (
        isinstance(provider, OpenAICodexProviderConfig)
        and session._harness.config.model not in provider.models
        and runtime is not None
        and runtime.name == provider.name
        and session._harness.config.model in runtime.models
    ):
        # Picker visibility must not invalidate an already selected runtime.
        return runtime
    return provider


def _apply_thinking_level_override(session: CodingSession) -> None:
    """Apply the one-shot startup thinking override to the loaded session.

    Runs once during :meth:`load`, after session state is replayed and
    before the level is synced to the active model, so the override wins
    over both remembered defaults and the resumed transcript state. The
    override is validated strictly against either the active dynamic model
    or the durable provider configuration when its capabilities are known.
    """
    override = session._config.thinking_level_override
    if override is None:
        return
    dynamic = session._active_dynamic_provider
    if dynamic is not None:
        model = session._active_dynamic_model
        levels = model.thinking_levels if model is not None else None
        if not levels:
            raise ProviderConfigError(f"Thinking modes are unavailable for {dynamic.id}:{session.model}")
        if override not in levels:
            allowed = ", ".join(levels)
            raise ProviderConfigError(
                f'Thinking mode "{override}" is not available for '
                f"{dynamic.id}:{session.model}. Available modes: {allowed}"
            )
        session.set_thinking_state(override)
        return
    provider = session._active_provider_config()
    if provider is None:
        session.set_thinking_state(override)
        return
    resolved = resolve_startup_thinking_level(provider, session.model, cli_override=override)
    if resolved is not None:
        session.set_thinking_state(resolved)


def _sync_thinking_level_to_active_model(session: CodingSession) -> None:
    provider = session._active_provider_config()
    if provider is None:
        return
    committed_model = session._harness.config.model
    session.set_thinking_state(
        _coerced_thinking_level(
            provider,
            model=committed_model,
            current=session._thinking_level,
            preferred=provider.thinking_defaults.get(committed_model),
        )
    )


def _sync_image_support(session: CodingSession) -> None:
    provider = session._active_provider_config() or session._runtime_provider_config
    session._image_support.supported = (
        provider_model_supports_images(provider, session._harness.config.model)
        if provider is not None
        else None
    )


def _persist_default_model_choice(session: CodingSession) -> None:
    if session._durable_provider_settings is None:
        return
    durable_provider = session._durable_provider_settings.get_provider(session.provider_name)
    if session.model not in durable_provider.models:
        # Account-specific inventory is deliberately not written into catalog.toml.
        return
    session._durable_provider_settings = save_default_provider_model(
        provider_name=session.provider_name,
        model=session.model,
        paths=session._resource_paths.paths,
        fallback_settings=session._durable_provider_settings,
    )
    session._apply_runtime_model_catalogs()
    session._sync_thinking_level_to_active_model()


def _persist_thinking_level_choice(session: CodingSession) -> None:
    if session._provider_settings is None:
        return
    provider = session._active_provider_config()
    if provider is None or session._thinking_level not in provider_thinking_levels(
        provider,
        model=session.model,
    ):
        return
    try:
        session._durable_provider_settings = save_provider_thinking_level(
            provider_name=session.provider_name,
            model=session.model,
            thinking_level=session._thinking_level,
            paths=session._resource_paths.paths,
            fallback_settings=session._durable_provider_settings,
        )
        session._apply_runtime_model_catalogs()
    except ProviderConfigError:
        return
