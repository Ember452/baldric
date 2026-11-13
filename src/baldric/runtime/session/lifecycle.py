"""Persistent coding-session wrapper built on AgentHarness."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import replace
from os import environ
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from baldric.ai.model_catalog import ModelCatalogProvider, RuntimeModelCatalog
from baldric.protocol.messages import (
    BashExecutionMessage,
)
from baldric.runtime.app import eligible_built_in_extensions, stage_runtime_for_reload
from baldric.runtime.commands.base import unhandled_result
from baldric.runtime.commands.registry import CommandResult
from baldric.runtime.config.paths import BaldricPaths
from baldric.runtime.context.prompts import (
    expand_prompt_template_command,
)
from baldric.runtime.context.resources import (
    ResourceDiagnostic,
    resource_paths_with_cwd,
    resource_paths_with_project_trust,
)
from baldric.runtime.context.skills.skills import expand_skill_command
from baldric.runtime.context.system_prompt import (
    BuildSystemPromptOptions,
    build_system_prompt,
)
from baldric.runtime.events import (
    SessionInfoChangedEvent,
)
from baldric.runtime.platform.api import UserBashEvent
from baldric.runtime.providers.config import (
    OpenAICodexProviderConfig,
    ProviderConfigError,
    resolve_provider_selection,
    validate_provider_model,
)
from baldric.runtime.providers.contracts import DynamicProvider
from baldric.runtime.providers.runtime import ClosableModelProvider
from baldric.runtime.providers.stores.codex_model_store import (
    save_codex_model_catalog,
)
from baldric.runtime.providers.stores.models_dev_store import (
    ModelsDevRefreshResult,
    refresh_models_dev_catalog,
)
from baldric.runtime.session.compaction.context_window import (
    DEFAULT_COMPACTION_KEEP_RECENT_TOKENS as DEFAULT_COMPACTION_KEEP_RECENT_TOKENS,
)
from baldric.runtime.session.manager import (
    InferenceProviderMode,
    normalize_session_name,
)
from baldric.runtime.session.model_selection import (
    ModelChoice as ModelChoice,
)
from baldric.runtime.session.model_selection import (
    ModelSelectionResult as ModelSelectionResult,
)
from baldric.runtime.session.provider_helpers import (  # noqa: F401
    _coerced_thinking_level as _coerced_thinking_level,
)
from baldric.runtime.session.provider_helpers import (
    _configured_inference_provider as _configured_inference_provider,
)
from baldric.runtime.session.provider_helpers import (
    _configured_inference_provider_mode as _configured_inference_provider_mode,
)
from baldric.runtime.session.provider_helpers import (
    _configured_model_supports_images as _configured_model_supports_images,
)
from baldric.runtime.session.provider_helpers import (
    _create_runtime_provider as _create_runtime_provider,
)
from baldric.runtime.session.provider_helpers import (
    _default_thinking_level_for_active_model as _default_thinking_level_for_active_model,
)
from baldric.runtime.session.provider_helpers import (
    _fallback_session_name as _fallback_session_name,
)
from baldric.runtime.session.provider_helpers import (
    _filter_tools as _filter_tools,
)
from baldric.runtime.session.provider_helpers import (
    _initial_model_for_config as _initial_model_for_config,
)
from baldric.runtime.session.provider_helpers import (
    _initial_thinking_level_for_config as _initial_thinking_level_for_config,
)
from baldric.runtime.session.provider_helpers import (
    _preferred_thinking_level_for_model as _preferred_thinking_level_for_model,
)
from baldric.runtime.session.provider_helpers import (
    _prepare_provider_selection as _prepare_provider_selection,
)
from baldric.runtime.session.provider_helpers import (
    _provider_config_for_name as _provider_config_for_name,
)
from baldric.runtime.session.provider_helpers import (
    _runtime_model_for_state as _runtime_model_for_state,
)
from baldric.runtime.session.provider_helpers import (
    _sanitize_session_name as _sanitize_session_name,
)
from baldric.runtime.session.provider_helpers import (
    _session_inference_provider as _session_inference_provider,
)
from baldric.runtime.session.provider_helpers import (
    _session_inference_provider_mode as _session_inference_provider_mode,
)
from baldric.runtime.session.provider_helpers import (
    _state_thinking_level as _state_thinking_level,
)
from baldric.runtime.session.provider_helpers import (
    _unavailable_thinking_message as _unavailable_thinking_message,
)
from baldric.runtime.session.resource_helpers import (  # noqa: F401
    SessionResources as SessionResources,
)
from baldric.runtime.session.resource_helpers import (
    TerminalCommandRequest as TerminalCommandRequest,
)
from baldric.runtime.session.resource_helpers import (
    _append_prompt_sections as _append_prompt_sections,
)
from baldric.runtime.session.resource_helpers import (
    _append_session_entry_sync as _append_session_entry_sync,
)
from baldric.runtime.session.resource_helpers import (
    _category_summary as _category_summary,
)
from baldric.runtime.session.resource_helpers import (
    _codex_account_id as _codex_account_id,
)
from baldric.runtime.session.resource_helpers import (
    _context_file_signatures as _context_file_signatures,
)
from baldric.runtime.session.resource_helpers import (
    _custom_prompt_source as _custom_prompt_source,
)
from baldric.runtime.session.resource_helpers import (
    _diagnostic_signatures as _diagnostic_signatures,
)
from baldric.runtime.session.resource_helpers import (
    _extension_signatures as _extension_signatures,
)
from baldric.runtime.session.resource_helpers import (
    _load_session_resources as _load_session_resources,
)
from baldric.runtime.session.resource_helpers import (
    _merge_context_files as _merge_context_files,
)
from baldric.runtime.session.resource_helpers import (
    _prompt_template_signatures as _prompt_template_signatures,
)
from baldric.runtime.session.resource_helpers import (
    _provider_config_or_none as _provider_config_or_none,
)
from baldric.runtime.session.resource_helpers import (
    _provider_settings_with_runtime_catalogs as _provider_settings_with_runtime_catalogs,
)
from baldric.runtime.session.resource_helpers import (
    _provider_with_runtime_model_catalog as _provider_with_runtime_model_catalog,
)
from baldric.runtime.session.resource_helpers import (
    _runtime_model_thinking_defaults as _runtime_model_thinking_defaults,
)
from baldric.runtime.session.resource_helpers import (
    _runtime_provider_model_metadata as _runtime_provider_model_metadata,
)
from baldric.runtime.session.resource_helpers import (
    _skill_signatures as _skill_signatures,
)
from baldric.runtime.session.resource_helpers import (
    _system_prompt_resource_signatures as _system_prompt_resource_signatures,
)
from baldric.runtime.session.resource_helpers import (
    _tool_history_repair_plan as _tool_history_repair_plan,
)
from baldric.runtime.session.resource_helpers import (
    default_session_path as default_session_path,
)
from baldric.runtime.session.resource_helpers import (
    jsonl_session_storage as jsonl_session_storage,
)
from baldric.runtime.session.resource_helpers import (
    parse_terminal_command as parse_terminal_command,
)
from baldric.runtime.session.tree_helpers import (  # noqa: F401
    _active_branchable_entry_id as _active_branchable_entry_id,
)
from baldric.runtime.session.tree_helpers import (
    _custom_message_from_entry as _custom_message_from_entry,
)
from baldric.runtime.session.tree_helpers import (
    _detach_missing_parents as _detach_missing_parents,
)
from baldric.runtime.session.tree_helpers import (
    _first_recent_context_index as _first_recent_context_index,
)
from baldric.runtime.session.tree_helpers import (
    _is_branchable_tree_entry as _is_branchable_tree_entry,
)
from baldric.runtime.session.tree_helpers import (
    _is_tool_call_tree_entry as _is_tool_call_tree_entry,
)
from baldric.runtime.session.tree_helpers import (
    _last_parent_id_from_state as _last_parent_id_from_state,
)
from baldric.runtime.session.tree_helpers import (
    _last_user_message_index as _last_user_message_index,
)
from baldric.runtime.session.tree_helpers import (
    _message_text_preview as _message_text_preview,
)
from baldric.runtime.session.tree_helpers import (
    _messages_after_entry_on_active_path as _messages_after_entry_on_active_path,
)
from baldric.runtime.session.tree_helpers import (
    _next_user_message_index as _next_user_message_index,
)
from baldric.runtime.session.tree_helpers import (
    _ordered_tree_entries as _ordered_tree_entries,
)
from baldric.runtime.session.tree_helpers import (
    _resolve_export_destination as _resolve_export_destination,
)
from baldric.runtime.session.tree_helpers import (
    _resolved_labels as _resolved_labels,
)
from baldric.runtime.session.tree_helpers import (
    _session_entry_for_message as _session_entry_for_message,
)
from baldric.runtime.session.tree_helpers import (
    _session_export_title as _session_export_title,
)
from baldric.runtime.session.tree_helpers import (
    _short_preview as _short_preview,
)
from baldric.runtime.session.tree_helpers import (
    _storage_path as _storage_path,
)
from baldric.runtime.session.tree_helpers import (
    _tree_branch_indents as _tree_branch_indents,
)
from baldric.runtime.session.tree_helpers import (
    _tree_choice_label as _tree_choice_label,
)
from baldric.runtime.session.tree_helpers import (
    _tree_entry_title as _tree_entry_title,
)
from baldric.runtime.session.tree_helpers import (
    _tree_layout as _tree_layout,
)
from baldric.runtime.session.tree_helpers import (
    is_context_overflow_error as is_context_overflow_error,
)
from baldric.runtime.session.tree_helpers import (
    is_retryable_huggingface_route_error as is_retryable_huggingface_route_error,
)
from baldric.runtime.tools.registry import create_bash_tool, create_coding_tools
from baldric.runtime.trust.policy import (
    format_trust_diagnostic,
)
from baldric.runtime.update.reload import CodingReloadSummary

if TYPE_CHECKING:
    from baldric.runtime.session.session import CodingSession, ManualCompactionResult, TerminalCommandResult


def _session_module() -> Any:
    import baldric.runtime.session.session as session_module

    return session_module


StreamingBehavior = Literal["steer", "follow_up"]
SESSION_NAME_SYSTEM_PROMPT = (
    "You write concise coding-agent session names. Reply with only a short title, "
    "maximum four words, no quotes, no punctuation-only output."
)
TREE_RUNNING_MESSAGE = "Baldric is still working. Press Escape to interrupt before using /tree."


async def reload(session: CodingSession) -> CodingReloadSummary:
    """Stage and atomically publish a complete replacement snapshot."""
    session._require_idle("reload")
    before_skills = _skill_signatures(session._skills)
    before_prompt_templates = _prompt_template_signatures(session._prompt_templates)
    before_context_files = _context_file_signatures(session._context_files)
    before_diagnostics = _diagnostic_signatures(session.resource_diagnostics)
    before_system_prompt_inputs = _system_prompt_resource_signatures(
        skills=session._skills,
        context_files=session._context_files,
        custom_system_prompt=session._custom_system_prompt,
        custom_system_prompt_path=session._custom_system_prompt_path,
        append_system_prompt=session._append_system_prompt,
        append_system_prompt_paths=session._append_system_prompt_paths,
    )
    before_extensions = _extension_signatures(session._extension_runtime)
    before_tool_names = tuple(tool.name for tool in session._harness.config.tools)
    before_guidelines = session._extension_runtime.prompt_guidelines
    before_sections = session._extension_runtime.sourced_prompt_sections

    # Nothing below mutates the live session. Eligible extensions are loaded
    # first so project code cannot import before the destination decision.
    unfiltered_paths = resource_paths_with_cwd(session._config.resource_paths, session.cwd)
    previous_ui = session._extension_runtime.ui
    staged_runtime = stage_runtime_for_reload(
        durable_providers=(session._provider_settings.providers if session._provider_settings else ()),
        credentials=session._extension_runtime.provider_credentials or session._credential_store,
        environment=session._extension_runtime.provider_environment,
        built_in_credentials=session._extension_runtime.built_in_credentials,
        built_in_http_client=session._extension_runtime.built_in_http_client,
        built_in_extensions=eligible_built_in_extensions(session._config),
        runtime_paths=(
            session._resource_paths.paths
            or BaldricPaths(
                home=session._resource_paths.root,
                agents_home=session._resource_paths.agents_root or Path.home() / ".agents",
            )
        ),
        unfiltered_resource_paths=unfiltered_paths,
        extra_paths=session._config.extension_paths,
        extensions_enabled=session._config.extensions_enabled,
    )

    staged_resolution = session._project_trust_resolution
    staged_paths = session._resource_paths
    coordinator = session._config.project_trust_coordinator
    trust_summary = None
    if coordinator is not None:
        trust_summary, staged_resolution = await coordinator.resolve(
            session.cwd,
            override=session._config.trust_override,
            default=session._config.trust_default,
            interactive=session._config.trust_interactive,
            prompt=session._config.trust_prompt,
            extension_deciders=(staged_runtime.decide_project_trust,),
            refresh=True,
            cache_result=False,
        )
        if staged_resolution.cancelled:
            raise ValueError("Project trust decision cancelled; keeping current resources")
        staged_paths = resource_paths_with_project_trust(
            resource_paths_with_cwd(session._config.resource_paths, trust_summary.cwd.value),
            trusted=staged_resolution.trusted,
        )

    resources = _session_module()._load_session_resources(
        staged_paths,
        session._config.context_files,
        skills_enabled=session._config.skills_enabled,
        system_prompt_enabled=session._config.system is None,
        custom_system_prompt_explicit=session._config.custom_system_prompt is not None,
    )
    if trust_summary is not None and trust_summary.categories:
        assert staged_resolution is not None
        resources = replace(
            resources,
            diagnostics=(
                *resources.diagnostics,
                ResourceDiagnostic(
                    kind="project-trust",
                    message=format_trust_diagnostic(trust_summary, staged_resolution),
                    severity="info" if staged_resolution.trusted else "warning",
                ),
            ),
        )
    if (
        staged_resolution is not None
        and staged_resolution.trusted
        and session._config.project_extensions_enabled
    ):
        staged_runtime.load(
            staged_paths,
            include_resource_dirs=True,
            include_project_dir=True,
            include_user_dir=False,
        )

    base_tools = (
        session._config.tools
        if session._config.tools is not None
        else create_coding_tools(
            cwd=session._config.cwd,
            shell_command_prefix=session._config.shell_command_prefix,
            shell=session._config.shell,
            image_support=session._image_support,
        )
    )
    staged_tools = _filter_tools(staged_runtime.compose_tools(base_tools), session._config.allowed_tool_names)
    staged_commands = session._config.command_registry or staged_runtime.build_command_registry()
    after_system_prompt_inputs = _system_prompt_resource_signatures(
        skills=resources.skills,
        context_files=resources.context_files,
        custom_system_prompt=resources.custom_system_prompt,
        custom_system_prompt_path=resources.custom_system_prompt_path,
        append_system_prompt=resources.append_system_prompt,
        append_system_prompt_paths=resources.append_system_prompt_paths,
    )
    after_guidelines = staged_runtime.prompt_guidelines
    after_sections = staged_runtime.sourced_prompt_sections
    system_prompt_rebuilt = session._config.system is None and (
        before_system_prompt_inputs != after_system_prompt_inputs
        or before_tool_names != tuple(tool.name for tool in staged_tools)
        or before_guidelines != after_guidelines
        or before_sections != after_sections
    )
    staged_system = session._harness.config.system
    if system_prompt_rebuilt:
        staged_system = build_system_prompt(
            BuildSystemPromptOptions(
                cwd=session._config.cwd,
                tools=staged_tools,
                skills=resources.skills,
                custom_prompt=(
                    session._config.custom_system_prompt
                    if session._config.custom_system_prompt is not None
                    else resources.custom_system_prompt
                ),
                append_sections=_append_prompt_sections(
                    resources.append_system_prompts,
                    resources.append_system_prompt_paths,
                    session._config.append_system_prompt,
                ),
                context_files=resources.context_files,
                extra_guidelines=after_guidelines,
                extra_sections=after_sections,
                custom_prompt_source=_custom_prompt_source(
                    explicit=session._config.custom_system_prompt is not None,
                    path=resources.custom_system_prompt_path,
                ),
            )
        )

    # Cancellable lifecycle work stays before the publication boundary. The
    # staged runtime may inspect the still-live session during session_start;
    # cancellation leaves that prior snapshot/runtime/cache untouched.
    old_runtime = session._extension_runtime
    await old_runtime.emit_session_shutdown("reload")
    old_runtime.clear_ui_components()
    staged_runtime.set_ui_bridge(previous_ui)
    staged_runtime.bind(session)
    await staged_runtime.emit_session_start("reload")

    # Publication is synchronous: cancellation can no longer report failure
    # after only part of the live snapshot or trust cache was adopted.
    if coordinator is not None and trust_summary is not None:
        assert staged_resolution is not None
        coordinator.commit(trust_summary.cwd, staged_resolution)
    old_runtime.retire()
    session._resource_paths = staged_paths
    session._config = replace(
        session._config,
        cwd=staged_paths.cwd or session._config.cwd,
        resource_paths=staged_paths,
        extension_runtime=staged_runtime,
    )
    session._project_trust_resolution = staged_resolution
    session._skills = resources.skills
    session._prompt_templates = resources.prompt_templates
    session._context_files = resources.context_files
    session._custom_system_prompt = resources.custom_system_prompt
    session._custom_system_prompt_path = resources.custom_system_prompt_path
    session._append_system_prompt = resources.append_system_prompt
    session._append_system_prompts = resources.append_system_prompts
    session._append_system_prompt_paths = resources.append_system_prompt_paths
    session._resource_diagnostics = resources.diagnostics
    session._command_registry = staged_commands
    session._extension_runtime = staged_runtime
    session._provider_registry = staged_runtime.provider_registry
    session._harness.config.tools = staged_tools
    session._harness.config.system = staged_system
    if system_prompt_rebuilt:
        session._invalidate_context_usage_cache()
    staged_runtime.attach_harness_listener(session._harness.subscribe)
    # Retirement invalidates publication synchronously; async close then
    # waits for cooperative provider callback cleanup or reports bounded
    # containment while the outgoing runtime still owns every task handle.
    # Caller cancellation at this committed seam is contained so reload
    # cannot report failure after the fresh snapshot became active.
    await _session_module()._finish_adopted_runtime_close(old_runtime)

    return CodingReloadSummary(
        skills=_category_summary(before_skills, _skill_signatures(resources.skills)),
        prompt_templates=_category_summary(
            before_prompt_templates, _prompt_template_signatures(resources.prompt_templates)
        ),
        context_files=_category_summary(
            before_context_files, _context_file_signatures(resources.context_files)
        ),
        extensions=_category_summary(before_extensions, _extension_signatures(staged_runtime)),
        diagnostics=_category_summary(
            before_diagnostics, _diagnostic_signatures(session.resource_diagnostics)
        ),
        system_prompt_rebuilt=system_prompt_rebuilt,
    )


async def refresh_model_catalogs(session: CodingSession, *, force: bool = False) -> ModelsDevRefreshResult:
    """Refresh public and authenticated catalogs and publish them to this session."""
    public_error: Exception | None = None
    result: ModelsDevRefreshResult | None = None
    try:
        result = await refresh_models_dev_catalog(
            paths=session._resource_paths.paths,
            force=force,
        )
        session.reload_provider_settings()
    except Exception as error:  # noqa: BLE001 - authenticated refresh still runs
        public_error = error
    await session._refresh_codex_model_catalog()
    if public_error is not None:
        raise public_error
    assert result is not None
    return result


async def _refresh_codex_model_catalog(session: CodingSession) -> None:
    """Refresh the account-specific Codex inventory without making it durable."""
    if environ.get("BALDRIC_OFFLINE") is not None or session._durable_provider_settings is None:
        return
    try:
        provider_config = session._durable_provider_settings.get_provider("openai-codex")
    except ProviderConfigError:
        return
    if not isinstance(provider_config, OpenAICodexProviderConfig):
        return
    if not session._provider_is_usable(provider_config):
        return

    # Use a fresh provider even when Codex is active. The active provider caches
    # its startup snapshot so reusing it would make `/model` unable to discover
    # versions or models released during a long-running Baldric process.
    temporary_provider = cast(
        ClosableModelProvider,
        _session_module().create_model_provider(
            provider_config,
            credential_store=session._credential_store,
            model=None,
            thinking_level=None,
        ),
    )
    if not isinstance(temporary_provider, ModelCatalogProvider):
        await temporary_provider.aclose()
        return
    try:
        catalog = await temporary_provider.discover_models()
        session._publish_runtime_model_catalog(provider_config.name, catalog)
        session._persist_codex_model_catalog(temporary_provider, catalog, provider_config)
    except Exception as exc:  # noqa: BLE001 - static catalog remains the safe fallback
        session._model_catalog_discovery_errors[provider_config.name] = f"{type(exc).__name__}: {exc}"
    finally:
        await temporary_provider.aclose()


def _persist_codex_model_catalog(
    session: CodingSession,
    provider: object,
    catalog: RuntimeModelCatalog,
    provider_config: OpenAICodexProviderConfig | None = None,
) -> None:
    config = provider_config or (
        session._runtime_provider_config
        if isinstance(session._runtime_provider_config, OpenAICodexProviderConfig)
        else None
    )
    if config is None:
        return
    account_id = getattr(provider, "account_id", None) or _codex_account_id(
        config,
        session._credential_store,
    )
    if not isinstance(account_id, str) or not account_id:
        return
    with suppress(OSError, TypeError, ValueError):
        save_codex_model_catalog(
            catalog,
            account_id=account_id,
            paths=session._resource_paths.paths,
        )


def _publish_runtime_model_catalog(
    session: CodingSession, provider_name: str, catalog: RuntimeModelCatalog
) -> None:
    if not catalog.models:
        raise ValueError("provider returned an empty model catalog")
    session._runtime_model_catalogs[provider_name] = catalog
    session._model_catalog_discovery_errors.pop(provider_name, None)
    session._invalidate_runtime_model_limits()
    session._apply_runtime_model_catalogs()


def _apply_runtime_model_catalogs(session: CodingSession) -> None:
    settings = session._durable_provider_settings
    if settings is None:
        session._provider_settings = None
        return
    providers = tuple(
        _provider_with_runtime_model_catalog(
            provider,
            session._runtime_model_catalogs.get(provider.name),
        )
        for provider in settings.providers
    )
    session._provider_settings = replace(settings, providers=providers)


def reload_provider_settings(session: CodingSession) -> None:
    """Reload provider settings for login and model-selection flows."""
    if session._provider_settings is None:
        return
    previous_settings = session._provider_settings
    previous_durable_settings = session._durable_provider_settings
    previous_thinking_level = session._thinking_level
    session._durable_provider_settings = _session_module().load_provider_settings(
        session._resource_paths.paths
    )
    session._apply_runtime_model_catalogs()
    active_config = session._active_provider_config()
    if active_config is None or session._harness.config.model not in active_config.models:
        # The refreshed picker snapshot is authoritative for new selections,
        # but cannot invalidate an already constructed, working provider.
        return
    try:
        session._sync_thinking_level_to_active_model()
        session._refresh_runtime_provider()
        session._sync_image_support()
    except ProviderConfigError:
        session._provider_settings = previous_settings
        session._durable_provider_settings = previous_durable_settings
        session.set_thinking_state(previous_thinking_level)
        raise


async def resume(session: CodingSession, session_id: str) -> str:
    """Replace this session's active state with another indexed session."""
    session._require_idle("resume")
    await session._flush_pending_message_writes(context=session._diagnostic_context())
    manager = session._config.session_manager
    if manager is None:
        raise ValueError("Session manager is not available")
    record = manager.get_session(session_id)
    if record is None:
        raise ValueError(f"Unknown session: {session_id}")

    provider_name = session._provider_name
    runtime_provider_config = session._runtime_provider_config
    model = session.model
    restore_record_model = False
    dynamic_resume = False
    if record.provider_name:
        effective = session._provider_registry.effective(record.provider_name)
        if effective is not None and isinstance(effective.definition, DynamicProvider):
            # Dynamic definitions are generation-local. Re-resolve the
            # reference in the fresh destination runtime instead of
            # carrying this runtime's provider object across cwd/trust
            # boundaries.
            provider_name = record.provider_name
            model = record.model
            runtime_provider_config = None
            dynamic_resume = True
            restore_record_model = True
        else:
            provider_name = record.provider_name
            model = record.model
            restore_record_model = True
            if session._provider_settings is None:
                # The destination runtime may provide a process-local
                # definition even when the source session did not.
                dynamic_resume = True
                runtime_provider_config = None
            else:
                try:
                    runtime_provider_config = session._provider_settings.get_provider(record.provider_name)
                except ProviderConfigError:
                    # Do not reject a dynamic overlay merely because the
                    # current cwd has not loaded its destination extension.
                    dynamic_resume = True
                    runtime_provider_config = None
                else:
                    if (
                        isinstance(runtime_provider_config, OpenAICodexProviderConfig)
                        and model not in runtime_provider_config.models
                    ):
                        # Re-discover a live-only destination model before validation.
                        dynamic_resume = True
                        runtime_provider_config = None
                    else:
                        validate_provider_model(runtime_provider_config, model)

    # Every field the caller can set has to survive the swap. `tools` is the one
    # that bites: a host that narrowed the tool set through config would silently
    # get the default catalogue back on resume. `dynamic_provider`,
    # `thinking_level_override` and `index_on_first_persist` are deliberately not
    # carried: the first is re-derived from live discovery, the second is a
    # per-launch flag, and the third belongs to the new storage.
    replacement = await type(session).load(
        _session_module().CodingSessionConfig(
            provider=None if dynamic_resume else session._harness.config.provider,
            model=model,
            cwd=record.cwd,
            storage=jsonl_session_storage(record.path),
            system=session._config.system,
            custom_system_prompt=session._config.custom_system_prompt,
            append_system_prompt=session._config.append_system_prompt,
            context_files=session._config.context_files,
            tools=session._config.tools,
            resource_paths=session._config.resource_paths,
            session_id=record.id,
            session_manager=manager,
            command_registry=session._config.command_registry,
            provider_name=provider_name,
            runtime_model_catalogs=dict(session._runtime_model_catalogs),
            inference_provider=None if dynamic_resume else record.inference_provider,
            inference_provider_mode=record.inference_provider_mode,
            requested_provider=provider_name if dynamic_resume else None,
            requested_model=model if dynamic_resume else None,
            session_provider_name=record.provider_name,
            provider_settings=session._durable_provider_settings,
            runtime_provider_config=runtime_provider_config,
            auto_compact_token_threshold=session._auto_compact_token_threshold,
            auto_compact_enabled=session._auto_compact_enabled,
            thinking_level=session._thinking_level,
            shell_command_prefix=session._config.shell_command_prefix,
            shell=session._config.shell,
            skills_enabled=session._config.skills_enabled,
            allowed_tool_names=session._config.allowed_tool_names,
            extension_paths=session._config.extension_paths,
            extensions_enabled=session._config.extensions_enabled,
            project_extensions_enabled=session._config.project_extensions_enabled,
            extension_runtime=session._extension_runtime,
            before_tool_call=session._config.before_tool_call,
            project_trust_coordinator=session._config.project_trust_coordinator,
            trust_override=session._config.trust_override,
            trust_default=session._config.trust_default,
            trust_interactive=session._config.trust_interactive,
            trust_prompt=session._config.trust_prompt,
            defer_authoritative_writes=dynamic_resume,
            owns_initial_provider=dynamic_resume,
            disabled_built_in_extensions=session._config.disabled_built_in_extensions,
        )
    )
    try:
        if not restore_record_model:
            # Only provider-less legacy records inherit the source model.
            # The staged loader has already resolved provider-aware records
            # against the destination's (possibly freshly discovered) catalog.
            replacement._harness.config.model = session._harness.config.model
            replacement._sync_thinking_level_to_active_model()
            replacement._refresh_runtime_provider()
            replacement._sync_image_support()
    except BaseException:
        # resume owns the loaded candidate until adoption takes ownership.
        await _session_module()._finish_aborted_session_close(replacement)
        raise
    await session._adopt_replacement(replacement, reason="resume")
    return f"Resumed session: {record.id}"


async def set_session_name(session: CodingSession, name: str) -> str:
    """Persist a session name and notify extensions after it changes."""
    normalized = normalize_session_name(name)
    persisted = session._persist_session_name(
        normalized,
        only_if_unnamed=False,
        index_if_missing=True,
    )
    if persisted is None:
        return normalized
    session.queue_frontend_event(SessionInfoChangedEvent(name=persisted))
    await session._extension_runtime.emit_event(SessionInfoChangedEvent(name=persisted))
    return persisted


def _persist_session_name(
    session: CodingSession, name: str, *, only_if_unnamed: bool, index_if_missing: bool
) -> str | None:
    """Persist and return a changed name; return None for a no-op."""
    normalized = normalize_session_name(name)
    manager = session._config.session_manager
    session_id = session._config.session_id
    if manager is None or session_id is None:
        raise ValueError("Session manager is not available")
    record = manager.get_session(session_id)
    if record is None and index_if_missing:
        session.ensure_session_indexed()
        record = manager.get_session(session_id)
    if record is None:
        return None
    if only_if_unnamed and record.title:
        return None
    if record.title == normalized:
        return None
    updated = manager.touch_session(
        session_id,
        model=session.model,
        provider_name=session.provider_name,
        title=normalized,
    )
    if updated is None:
        if index_if_missing:
            raise ValueError(f"Unknown session: {session_id}")
        return None
    return updated.title or normalized


async def new_session(session: CodingSession) -> str:
    """Replace this session's active state with a pending unindexed session."""
    session._require_idle("start a new session")
    await session._flush_pending_message_writes(context=session._diagnostic_context())
    manager = session._config.session_manager
    if manager is None:
        raise ValueError("Session manager is not available")

    provider_name = session._provider_name
    model = session._harness.config.model
    runtime_provider_config = session._runtime_provider_config
    thinking_level = session._thinking_level
    if session._provider_settings is not None:
        selection = resolve_provider_selection(session._provider_settings)
        provider_name = selection.provider.name
        model = selection.model
        runtime_provider_config = selection.provider
        thinking_level = _coerced_thinking_level(
            selection.provider,
            model=model,
            current=session._thinking_level,
        )

    effective = session._provider_registry.effective(provider_name)
    dynamic_provider = (
        effective.definition
        if effective is not None and isinstance(effective.definition, DynamicProvider)
        else None
    )
    if dynamic_provider is not None:
        model = next(
            (item.id for item in dynamic_provider.models if item.id == model),
            dynamic_provider.default_model
            or (dynamic_provider.models[0].id if dynamic_provider.models else model),
        )
        runtime_provider_config = None
    inference_provider = (
        None
        if dynamic_provider is not None
        else _configured_inference_provider(runtime_provider_config, model)
    )
    inference_provider_mode: InferenceProviderMode = (
        "automatic"
        if dynamic_provider is not None
        else _configured_inference_provider_mode(runtime_provider_config, model)
    )
    record = (
        manager.prepare_session(
            cwd=session.cwd,
            model=model,
            provider_name=provider_name,
            inference_provider=inference_provider,
            inference_provider_mode=inference_provider_mode,
        )
        if inference_provider is not None
        else manager.prepare_session(
            cwd=session.cwd,
            model=model,
            provider_name=provider_name,
        )
    )
    replacement = await type(session).load(
        replace(
            session._config,
            # The old runtime may belong to a different provider. Stage a
            # fresh runtime for the new session's default provider/model.
            provider=(session._harness.config.provider if session._provider_settings is None else None),
            model=record.model or model,
            cwd=record.cwd,
            storage=jsonl_session_storage(record.path),
            session_id=record.id,
            provider_name=provider_name,
            inference_provider=inference_provider,
            inference_provider_mode=inference_provider_mode,
            requested_provider=provider_name if dynamic_provider is not None else None,
            requested_model=model if dynamic_provider is not None else None,
            session_provider_name=provider_name,
            provider_settings=session._durable_provider_settings,
            runtime_provider_config=runtime_provider_config,
            dynamic_provider=dynamic_provider,
            owns_initial_provider=False,
            defer_authoritative_writes=dynamic_provider is not None,
            thinking_level=thinking_level,
            index_on_first_persist=True,
            extension_runtime=session._extension_runtime,
            # Carry the harness gate across /new. Dropping it here let a user
            # who turned on approval mode create a session where mutating
            # tools ran without ever asking — a silent, session-wide failure.
            before_tool_call=session._config.before_tool_call,
        )
    )
    await session._adopt_replacement(replacement, reason="new")
    return f"Started new session: {record.id}"


async def _adopt_replacement(
    session: CodingSession, replacement: CodingSession, *, reason: Literal["new", "resume", "branch"]
) -> None:
    """Adopt a replacement session's state and re-bind the extension runtime.

    The extension runtime is long-lived and shared with the replacement; it
    must be re-bound to this outer session object because later state
    (transcript persistence, parent ids) mutates here, not on the discarded
    replacement instance.
    """
    old_runtime = session._extension_runtime
    try:
        if (
            replacement.project_trust_resolution is not None
            and replacement.project_trust_resolution.cancelled
        ):
            raise ValueError("Project trust decision cancelled; current session unchanged")

        # Destination transcript initialization/repair is the durable
        # commit point. It must succeed before the outgoing runtime enters
        # its shutdown path.
        await replacement._commit_prepared_entries()

        # The replacement remains the explicit owner of its providers
        # through every cancellable/erroring pre-publication seam.
        await old_runtime.emit_session_shutdown(reason)
        old_runtime.clear_ui_components()
        await replacement._extension_runtime.emit_session_start(reason)
        replacement._commit_project_trust_resolution()
        replacement._session_start_pending = False
    except BaseException:
        await _session_module()._finish_aborted_session_close(replacement)
        raise

    # Every cancellable boundary has completed. Adopt synchronously so a
    # reported cancellation cannot expose only part of the destination.
    old_runtime.retire()
    session._config = replacement._config
    session._state = replacement._state
    session._harness = replacement._harness
    session.set_preview_model(None)
    session.set_preview_thinking(None)
    # Detach the replacement's persistence listener so writes advance
    # this session's parent pointers, not the discarded replacement's.
    if replacement._persistence_unsubscribe is not None:
        replacement._persistence_unsubscribe()
        replacement._persistence_unsubscribe = None
    session._attach_persistence_listener()
    session._invalidate_context_usage_cache()
    session.set_active_leaf_id(replacement._last_parent_id)
    session._skills = replacement._skills
    session._prompt_templates = replacement._prompt_templates
    session._context_files = replacement._context_files
    session._custom_system_prompt = replacement._custom_system_prompt
    session._custom_system_prompt_path = replacement._custom_system_prompt_path
    session._append_system_prompt = replacement._append_system_prompt
    session._append_system_prompts = replacement._append_system_prompts
    session._append_system_prompt_paths = replacement._append_system_prompt_paths
    session._resource_diagnostics = replacement._resource_diagnostics
    session._command_registry = replacement._command_registry
    session._provider_name = replacement._provider_name
    session._inference_provider = replacement._inference_provider
    session._inference_provider_mode = replacement._inference_provider_mode
    session._provider_settings = replacement._provider_settings
    session._durable_provider_settings = replacement._durable_provider_settings
    session._runtime_model_catalogs = replacement._runtime_model_catalogs
    session._model_catalog_discovery_errors = replacement._model_catalog_discovery_errors
    session._runtime_provider_config = replacement._runtime_provider_config
    session._resource_paths = replacement._resource_paths
    session._auto_compact_token_threshold = replacement._auto_compact_token_threshold
    session._auto_compact_enabled = replacement._auto_compact_enabled
    session.set_thinking_state(replacement._thinking_level)
    session._pending_initial_entries = replacement._pending_initial_entries
    session._pending_message_writes = replacement._pending_message_writes
    session._extension_runtime = replacement._extension_runtime
    session._provider_registry = replacement._provider_registry
    session._adopt_system_prompt_builder(replacement)
    session._credential_store = replacement._credential_store
    session._diagnostic_logger = replacement._diagnostic_logger
    session._runtime_model_limits = replacement._runtime_model_limits
    session._runtime_model_limits_key = replacement._runtime_model_limits_key
    session._model_limits_discovery_error = replacement._model_limits_discovery_error
    session._prepared_entries = replacement._prepared_entries
    session._owned_providers.extend(replacement._owned_providers)
    replacement._owned_providers.clear()
    session._image_support = replacement._image_support
    session._project_trust_resolution = replacement._project_trust_resolution
    session._project_trust_commit_pending = False
    session._session_start_pending = False
    session._extension_runtime.bind(session)
    session._extension_runtime.attach_harness_listener(session._harness.subscribe)
    # Adoption is already committed. Finish outgoing cleanup under a
    # shielded owner and contain cancellation rather than reporting that
    # the requested destination failed to replace the source session.
    await _session_module()._finish_adopted_runtime_close(old_runtime)


async def compact_detailed(session: CodingSession, instructions: str | None = None) -> ManualCompactionResult:
    """Compact older context while preserving a real recent-entry boundary."""
    await session._flush_pending_message_writes(context=session._diagnostic_context())
    plan = session._recent_preserving_compaction_plan()
    if plan is None:
        raise ValueError("Not enough context to compact while preserving recent entries")
    tokens_before = session.context_token_estimate
    generated = await session._generate_compaction_summary(
        plan.messages_to_summarize,
        custom_instructions=instructions,
    )
    await session._append_compaction(
        generated.text,
        first_kept_entry_id=plan.first_kept_entry_id,
        tokens_before=tokens_before,
        usage=generated.usage,
        provider=generated.provider,
        model=generated.model,
        response_provider=generated.response_provider,
    )
    return cast(
        "ManualCompactionResult",
        _session_module().ManualCompactionResult(
            summary=generated.text,
            first_kept_entry_id=plan.first_kept_entry_id,
            tokens_before=tokens_before,
            estimated_tokens_after=session.context_token_estimate,
            replaced_entry_count=plan.replaced_entry_count,
        ),
    )


async def compact(session: CodingSession, instructions: str | None = None) -> str:
    """Generate a manual compaction summary and rebuild active context."""
    result = await session.compact_detailed(instructions)
    return f"Compacted {result.replaced_entry_count} context entries."


async def aclose(session: CodingSession) -> None:
    """Close every owned extension/provider resource exactly once.

    Caller cancellation is remembered but cannot cancel the durable close
    task. The first call propagates it only after all ownership ledgers are
    discharged; later calls observe the same completed task idempotently.
    """
    close_task = session._close_task
    if close_task is None:
        close_task = asyncio.create_task(
            session._close_owned_resources(),
            name="baldric-coding-session-close",
        )
        session._close_task = close_task

    cancelled = await _session_module()._await_cleanup_completion(close_task)
    error: BaseException | None = None
    try:
        close_task.result()
    except BaseException as exc:  # all resources were attempted before this outcome
        error = exc
    if cancelled:
        raise asyncio.CancelledError
    if error is not None:
        raise error


async def _close_owned_resources(session: CodingSession) -> None:
    """Run the sole close pass, continuing after individual failures."""
    error: BaseException | None = None
    try:
        if session._extension_runtime.active:
            await session._extension_runtime.emit_session_shutdown("quit")
    except BaseException as exc:
        error = exc

    # Final close has no successor sharing the UI bridge. Remove any
    # source-owned widgets/interceptors before invalidating the API.
    try:
        session._extension_runtime.clear_ui_components()
    except BaseException as exc:
        if error is None:
            error = exc

    # A runtime may already be synchronously retired by replacement. Close
    # still owns the async drain/containment step and must never skip it.
    try:
        await session._extension_runtime.aclose()
    except BaseException as exc:
        if error is None:
            error = exc

    # Remove each provider from the ownership ledger before its only close
    # attempt. One hostile provider cannot prevent later providers closing.
    providers = tuple(session._owned_providers)
    session._owned_providers.clear()
    for provider in providers:
        try:
            await provider.aclose()
        except BaseException as exc:
            if error is None:
                error = exc

    if error is not None:
        raise error


def handle_command(session: CodingSession, text: str) -> CommandResult:
    """Handle coding-session slash commands.

    Prompt-template slash commands are expansion directives, so they remain
    unhandled here and flow through `prompt()` for on-the-fly replacement.
    """
    if expand_prompt_template_command(text, session._prompt_templates) is not None:
        return unhandled_result()
    return session._command_registry.execute(session, text)


def ensure_session_indexed(session: CodingSession) -> None:
    """Persist pending session metadata and add this session to the resume index."""
    if session._config.session_id is None or session._config.session_manager is None:
        return
    if session._config.session_manager.get_session(session._config.session_id) is None:
        session._config.session_manager.create_session(
            cwd=session.cwd,
            model=session.model,
            provider_name=session.provider_name,
            inference_provider=session._inference_provider,
            inference_provider_mode=session._inference_provider_mode,
            session_id=session._config.session_id,
        )
    session._config = replace(session._config, index_on_first_persist=False)
    session._ensure_session_file_initialized()


def expand_prompt_text(session: CodingSession, text: str) -> str:
    """Expand prompt text using loaded markdown resources."""
    expanded_prompt = expand_prompt_template_command(text, session._prompt_templates)
    if expanded_prompt is not None:
        return expanded_prompt
    expanded_skill = expand_skill_command(text, session._skills)
    return expanded_skill if expanded_skill is not None else text


async def run_terminal_command(
    session: CodingSession, command: str, *, add_to_context: bool
) -> TerminalCommandResult:
    """Run a shell command in the session cwd, optionally adding output to context."""
    normalized_command = command.strip()
    if not normalized_command:
        raise ValueError("Terminal command cannot be empty")

    # Ports Pi's user_bash: an extension may answer the command itself (remote
    # shells, sandboxes). The first handler returning a result wins and the local
    # shell never runs; None defers to the next handler, then local execution.
    extension_result = await session._extension_runtime.run_user_bash(
        UserBashEvent(
            command=normalized_command,
            cwd=session.cwd,
            exclude_from_context=not add_to_context,
        )
    )
    if extension_result is not None:
        added = add_to_context and not extension_result.cancelled
        if added:
            await session._flush_pending_message_writes(context=session._diagnostic_context())
            context_message = BashExecutionMessage(
                command=normalized_command,
                output=extension_result.output,
                exit_code=extension_result.exit_code,
            )
            session._harness.append_message(context_message)
            session._invalidate_context_usage_cache()
            await session._persist_message(context_message)
        return cast(
            "TerminalCommandResult",
            _session_module().TerminalCommandResult(
                command=normalized_command,
                output=extension_result.output,
                exit_code=extension_result.exit_code,
                ok=extension_result.exit_code == 0 and not extension_result.cancelled,
                added_to_context=added,
            ),
        )

    bash_tool = create_bash_tool(
        cwd=session.cwd,
        shell_command_prefix=session._config.shell_command_prefix,
        shell=session._config.shell,
    )
    result = await bash_tool.execute("terminal-command", {"command": normalized_command})
    exit_code = None
    if isinstance(result.details, dict):
        raw_exit_code = result.details.get("exit_code")
        exit_code = raw_exit_code if isinstance(raw_exit_code, int) else None

    if add_to_context:
        await session._flush_pending_message_writes(context=session._diagnostic_context())
        context_message = BashExecutionMessage(
            command=normalized_command,
            output=result.text,
            exit_code=exit_code,
        )
        session._harness.append_message(context_message)
        session._invalidate_context_usage_cache()
        await session._persist_message(context_message)

    return cast(
        "TerminalCommandResult",
        _session_module().TerminalCommandResult(
            command=normalized_command,
            output=result.text,
            exit_code=exit_code,
            ok=exit_code == 0,
            added_to_context=add_to_context,
        ),
    )
