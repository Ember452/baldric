"""Persistent coding-session wrapper built on AgentHarness."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field, replace
from os import environ
from pathlib import Path
from typing import Literal

from baldric_agent.events import AgentEndEvent, AgentEvent, MessageEndEvent, ToolExecutionEndEvent
from baldric_agent.harness import AgentHarness, AgentHarnessConfig, QueuedMessages
from baldric_agent.messages import (
    AgentMessage,
    AssistantMessage,
    CustomMessage,
    Usage,
    UserMessage,
    message_text,
)
from baldric_agent.provider import ModelProvider
from baldric_agent.session import (
    BranchSummaryEntry,
    CompactionEntry,
    CustomEntry,
    LabelEntry,
    ModelChangeEntry,
    SessionInfoEntry,
    SessionState,
    SessionStorage,
    ThinkingLevelChangeEntry,
)
from baldric_agent.session.entries import SessionEntry
from baldric_agent.tool_history import ToolHistoryRepair
from baldric_agent.tools import AgentTool
from baldric_agent.types import JSONValue
from baldric_ai.model_catalog import ModelCatalogProvider, RuntimeModelCatalog
from baldric_ai.model_limits import ModelLimitsProvider, RuntimeModelLimits
from baldric_coding.auth.credentials import FileCredentialStore, credentials_path
from baldric_coding.commands.registry import CommandRegistry, CommandResult, create_default_command_registry
from baldric_coding.config.paths import BaldricPaths
from baldric_coding.context.prompts import (
    PromptTemplate,
    expand_prompt_template_command,
)
from baldric_coding.context.resources import (
    BaldricResourcePaths,
    ResourceDiagnostic,
    resource_paths_with_cwd,
    resource_paths_with_project_trust,
)
from baldric_coding.context.skills.skills import Skill, expand_skill_command
from baldric_coding.context.system_prompt import (
    BuildSystemPromptOptions,
    ProjectContextFile,
    SystemPromptInspection,
    SystemPromptSource,
    build_system_prompt,
    build_system_prompt_inspection,
)
from baldric_coding.context.thinking import (
    DEFAULT_THINKING_LEVEL,
    THINKING_LEVELS,
    ThinkingLevel,
)
from baldric_coding.events import (
    AgentSettledEvent,
    AutoRetryEndEvent,
    AutoRetryStartEvent,
    CodingSessionEvent,
    QueueUpdateEvent,
    SessionAgentEndEvent,
    SessionInfoChangedEvent,
)
from baldric_coding.extensions.providers import DynamicProvider, ProviderModel
from baldric_coding.extensions.runtime import ExtensionRuntime
from baldric_coding.observability.diagnostics import (
    AgentCallDiagnosticContext,
    AgentCallDiagnosticLogger,
)
from baldric_coding.providers.config import (
    OpenAICodexProviderConfig,
    ProviderConfig,
    ProviderConfigError,
    ProviderSettings,
    load_provider_settings,
    provider_thinking_levels,
    provider_thinking_unavailable_reason,
    resolve_provider_selection,
    validate_huggingface_inference_provider,
    validate_provider_model,
)
from baldric_coding.providers.runtime import (
    ClosableModelProvider,
    create_model_provider,
)
from baldric_coding.providers.stores.codex_model_store import (
    cached_codex_model_catalog,
    save_codex_model_catalog,
)
from baldric_coding.providers.stores.models_dev_store import (
    ModelsDevRefreshResult,
    refresh_models_dev_catalog,
)
from baldric_coding.session import model_selection as _model_selection
from baldric_coding.session import runtime as _session_runtime
from baldric_coding.session.compaction.context_window import (
    DEFAULT_COMPACTION_KEEP_RECENT_TOKENS as DEFAULT_COMPACTION_KEEP_RECENT_TOKENS,
)
from baldric_coding.session.compaction.context_window import (
    DEFAULT_CONTEXT_WINDOW_TOKENS,
    ContextUsageEstimate,
    auto_compaction_threshold_for_context_window,
    estimate_context_usage,
)
from baldric_coding.session.export import (
    export_session_artifact,
    normalize_export_format,
)
from baldric_coding.session.manager import (
    InferenceProviderMode,
    SessionManager,
    normalize_session_name,
)
from baldric_coding.session.model_selection import (
    ModelChoice as ModelChoice,
)
from baldric_coding.session.model_selection import (
    ModelSelectionResult as ModelSelectionResult,
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
    _terminal_command_context_message as _terminal_command_context_message,
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
from baldric_coding.session.runtime import CompactionPlan, _GeneratedSummary, _PendingMessageWrite
from baldric_coding.session.stats import SessionStats, calculate_session_stats
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
from baldric_coding.tools.registry import ImageSupportState, create_bash_tool, create_coding_tools
from baldric_coding.trust.policy import (
    CanonicalProjectPath,
    ProjectTrustCoordinator,
    ProjectTrustResolution,
    ProjectTrustStore,
    TrustDefault,
    TrustOverride,
    TrustPrompt,
    format_trust_diagnostic,
)
from baldric_coding.update.reload import CodingReloadSummary

StreamingBehavior = Literal["steer", "follow_up"]
SESSION_NAME_SYSTEM_PROMPT = (
    "You write concise coding-agent session names. Reply with only a short title, "
    "maximum four words, no quotes, no punctuation-only output."
)
TREE_RUNNING_MESSAGE = "Baldric is still working. Press Escape to interrupt before using /tree."


async def _await_cleanup_completion[CleanupResult](
    task: asyncio.Task[CleanupResult],
) -> bool:
    """Wait through caller cancellation without forwarding it into cleanup.

    Returns whether cancellation was observed. Repeated requests remain
    contained until the independently owned cleanup task reaches a terminal
    state.
    """
    cancelled = False
    while True:
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
            if not task.done():
                continue
        except BaseException:  # cleanup outcome is inspected by its owner
            pass
        return cancelled


async def _finish_adopted_runtime_close(runtime: ExtensionRuntime) -> None:
    """Finish outgoing cleanup after publication without failing adoption."""
    task = asyncio.create_task(
        runtime.aclose(),
        name="baldric-adopted-extension-runtime-close",
    )
    await _await_cleanup_completion(task)
    # Publication is already committed. Cleanup cancellation/failure must not
    # masquerade as rollback while the task's outcome still gets retrieved.
    with suppress(BaseException):
        task.result()


async def _finish_aborted_session_close(session: CodingSession) -> None:
    """Discharge an unpublished session's resources without masking its abort."""
    task = asyncio.create_task(
        session.aclose(),
        name="baldric-aborted-coding-session-close",
    )
    await _await_cleanup_completion(task)
    # The pre-publication failure remains primary, but every owned provider was
    # attempted by CodingSession's durable, idempotent close task.
    with suppress(BaseException):
        task.result()


@dataclass(frozen=True, slots=True)
class TerminalCommandResult:
    """Result of an input-bar terminal command."""

    command: str
    output: str
    exit_code: int | None
    ok: bool
    added_to_context: bool


@dataclass(frozen=True, slots=True)
class SessionTreeChoice:
    """One branchable entry in the active session tree."""

    entry_id: str
    label: str
    active: bool = False
    is_tool_call: bool = False
    bookmark_label: str | None = None
    label_timestamp: float | None = None


@dataclass(frozen=True, slots=True)
class SessionTreeBranchResult:
    """Result of moving the active session tree leaf."""

    message: str
    input_prefill: str | None = None


@dataclass(frozen=True, slots=True)
class ManualCompactionResult:
    """Structured result from one manual compaction."""

    summary: str
    first_kept_entry_id: str
    tokens_before: int
    estimated_tokens_after: int
    replaced_entry_count: int


@dataclass(frozen=True, slots=True)
class CodingSessionConfig:
    """Configuration for a persistent coding session."""

    provider: ModelProvider | None
    model: str
    storage: SessionStorage
    cwd: Path
    system: str | None = None
    custom_system_prompt: str | None = None
    append_system_prompt: str | None = None
    context_files: tuple[ProjectContextFile, ...] = ()
    tools: list[AgentTool] | None = None
    resource_paths: BaldricResourcePaths | None = None
    session_id: str | None = None
    session_manager: SessionManager | None = None
    command_registry: CommandRegistry | None = None
    provider_name: str = "openai"
    inference_provider: str | None = None
    inference_provider_mode: InferenceProviderMode | None = None
    requested_provider: str | None = None
    requested_model: str | None = None
    session_provider_name: str | None = None
    provider_settings: ProviderSettings | None = None
    runtime_model_catalogs: Mapping[str, RuntimeModelCatalog] = field(default_factory=dict)
    runtime_provider_config: ProviderConfig | None = None
    dynamic_provider: DynamicProvider | None = None
    owns_initial_provider: bool = False
    auto_compact_token_threshold: int | None = None
    auto_compact_enabled: bool = True
    thinking_level: ThinkingLevel = DEFAULT_THINKING_LEVEL
    thinking_level_override: ThinkingLevel | None = None
    """One-shot startup override (e.g. ``--thinking``) for the session's level.

    Takes precedence over remembered per-model defaults and replayed session
    state, is validated strictly against the active model's available levels
    when the provider configuration is known, and is never persisted as a new
    remembered default.
    """
    index_on_first_persist: bool = False
    shell_command_prefix: str | None = None
    skills_enabled: bool = True
    """Whether skill discovery is enabled for this session.

    When ``True`` (the default), skills are discovered from the resource paths
    and their index is injected into the system prompt as ``<available_skills>``,
    and ``/skill:`` commands expand against them. When ``False``, skill discovery
    is suppressed for the whole session: no skills load, the ``<available_skills>``
    index is omitted, and ``/skill:`` commands find nothing to expand. This mirrors
    Pi's loader-level ``noSkills`` flag, which suppresses only skill discovery and
    leaves prompt templates and project context files (AGENTS.md) unaffected. It is
    the seam hosts use to construct skill-less sessions (e.g. a subagent type that
    gets no skills).
    """
    allowed_tool_names: frozenset[str] | None = None
    """Optional allow-list applied to the session's final tool set.

    ``tools`` only replaces the built-in tool set; extension-registered tools are
    composed on top of it afterwards. This filter is applied *after* that
    composition (on initial load and again on every reload), so it caps the
    complete tool list by name regardless of where a tool came from. An
    extension tool that overrides a built-in of the same name is subject to the
    list like any other. ``None`` (the default) disables filtering; names that
    match no tool are ignored. It is the seam hosts use to construct sessions
    with a restricted tool set (e.g. a subagent type limited to ``read``/``bash``).
    """
    extension_paths: tuple[Path, ...] = ()
    extensions_enabled: bool = True
    project_extensions_enabled: bool = False
    extension_runtime: ExtensionRuntime | None = None
    project_trust_coordinator: ProjectTrustCoordinator | None = None
    trust_override: TrustOverride | None = None
    trust_default: TrustDefault = "ask"
    trust_interactive: bool = False
    trust_prompt: TrustPrompt | None = None
    # Shared preparation keeps transcript/trust/index writes staged until
    # PreparedCodingSession.adopt() reaches its durable commit point.
    defer_authoritative_writes: bool = False


class CodingSession:
    """Baldric's coding-agent environment wrapper.

    `AgentHarness` owns the in-memory agent brain. `CodingSession` owns the
    coding-session environment around it: durable session entries, default coding
    tools, and a small command seam for later phases.
    """

    def __init__(
        self,
        config: CodingSessionConfig,
        *,
        state: SessionState,
        harness: AgentHarness,
        last_parent_id: str | None,
        skills: tuple[Skill, ...] = (),
        prompt_templates: tuple[PromptTemplate, ...] = (),
        context_files: tuple[ProjectContextFile, ...] = (),
        custom_system_prompt: str | None = None,
        custom_system_prompt_path: Path | None = None,
        append_system_prompt: str | None = None,
        append_system_prompts: tuple[str, ...] = (),
        append_system_prompt_paths: tuple[Path, ...] = (),
        resource_diagnostics: tuple[ResourceDiagnostic, ...] = (),
        command_registry: CommandRegistry | None = None,
        pending_initial_entries: tuple[SessionEntry, ...] = (),
        extension_runtime: ExtensionRuntime | None = None,
        image_support: ImageSupportState | None = None,
        project_trust_resolution: ProjectTrustResolution | None = None,
    ) -> None:
        self._config = config
        self._state = state
        self._harness = harness
        self._extension_runtime = extension_runtime or ExtensionRuntime()
        self._provider_registry = self._extension_runtime.provider_registry
        self._image_support = image_support or ImageSupportState()
        self._session_start_pending = False
        self._last_parent_id = last_parent_id
        self._pending_initial_entries = pending_initial_entries
        self._prepared_entries: list[SessionEntry] = list(pending_initial_entries)
        self._skills = skills
        self._prompt_templates = prompt_templates
        self._context_files = context_files
        self._custom_system_prompt = custom_system_prompt
        self._custom_system_prompt_path = custom_system_prompt_path
        self._append_system_prompt = append_system_prompt
        self._append_system_prompts = append_system_prompts
        self._append_system_prompt_paths = append_system_prompt_paths
        self._resource_diagnostics = resource_diagnostics
        self._command_registry = command_registry or create_default_command_registry()
        self._provider_name = config.provider_name
        self._inference_provider = config.inference_provider
        self._inference_provider_mode: InferenceProviderMode = config.inference_provider_mode or (
            "fixed" if config.inference_provider is not None else "automatic"
        )
        self._provider_settings = config.provider_settings
        self._durable_provider_settings = config.provider_settings
        self._runtime_model_catalogs = dict(config.runtime_model_catalogs)
        self._model_catalog_discovery_errors: dict[str, str] = {}
        self._runtime_provider_config = config.runtime_provider_config
        self._resource_paths = resource_paths_with_cwd(config.resource_paths, config.cwd)
        self._auto_compact_token_threshold = config.auto_compact_token_threshold
        self._auto_compact_enabled = config.auto_compact_enabled
        self._preview_model: ModelChoice | None = None
        self._preview_thinking: ThinkingLevel | None = None
        self._thinking_level = _state_thinking_level(
            state,
            default=_default_thinking_level_for_active_model(self),
        )
        self._context_usage_cache: ContextUsageEstimate | None = None
        self._session_stats_cache: tuple[SessionState, CodingSessionConfig, SessionStats] | None = None
        self._owned_providers: list[ClosableModelProvider] = []
        self._close_task: asyncio.Task[None] | None = None
        self._diagnostic_logger = AgentCallDiagnosticLogger.from_paths(self._resource_paths.paths)
        self._credential_store = FileCredentialStore(
            credentials_path(self._resource_paths.paths) if self._resource_paths.paths else None
        )
        self._last_diagnostic_log_path: Path | None = None
        self._runtime_model_limits: RuntimeModelLimits | None = None
        self._runtime_model_limits_key: tuple[str, str] | None = None
        self._model_limits_discovery_error: str | None = None
        self._project_trust_resolution = project_trust_resolution
        self._project_trust_commit_pending = False
        self._persistence_unsubscribe: Callable[[], None] | None = None
        self._persisted_message_ids: set[int] = set()
        self._ended_message_ids: set[int] = set()
        self._pending_message_writes: dict[int, _PendingMessageWrite] = {}
        self._attach_persistence_listener()

    @classmethod
    async def load(cls, config: CodingSessionConfig) -> CodingSession:
        """Load a coding session from append-only storage."""
        entries = await config.storage.read_all()
        pending_initial_entries: tuple[SessionEntry, ...] = ()
        if not entries:
            info = SessionInfoEntry(cwd=str(config.cwd))
            initial_model = _initial_model_for_config(config)
            model = ModelChangeEntry(
                parent_id=info.id,
                model=initial_model,
                provider=config.requested_provider or config.provider_name,
            )
            thinking = ThinkingLevelChangeEntry(
                parent_id=model.id,
                thinking_level=_initial_thinking_level_for_config(config, model=initial_model),
            )
            entries = [info, model, thinking]
            pending_initial_entries = (info, model, thinking)
        else:
            entries = _detach_missing_parents(entries)

        state = SessionState.from_entries(entries)
        unfiltered_resource_paths = resource_paths_with_cwd(config.resource_paths, config.cwd)

        # A runtime is cwd-bound because it may contain project registrations.
        # Always stage a fresh eligible-only runtime for a destination snapshot;
        # never reuse source-project code across replacement trust boundaries.
        previous_runtime = config.extension_runtime
        runtime_paths = unfiltered_resource_paths.paths or BaldricPaths(
            home=unfiltered_resource_paths.root,
            agents_home=unfiltered_resource_paths.agents_root or Path.home() / ".agents",
        )
        credential_store = FileCredentialStore(credentials_path(runtime_paths))
        injected_credentials = previous_runtime.provider_credentials if previous_runtime is not None else None
        extension_runtime = ExtensionRuntime(
            paths=runtime_paths,
            credentials=injected_credentials or credential_store,
            environment=(previous_runtime.provider_environment if previous_runtime is not None else None),
            built_in_credentials=(
                previous_runtime.built_in_credentials if previous_runtime is not None else None
            ),
            built_in_http_client=(
                previous_runtime.built_in_http_client if previous_runtime is not None else None
            ),
            durable_providers=(config.provider_settings.providers if config.provider_settings else ()),
        )
        extension_runtime.load(
            unfiltered_resource_paths,
            extra_paths=config.extension_paths,
            include_resource_dirs=config.extensions_enabled,
            include_project_dir=False,
        )

        coordinator = config.project_trust_coordinator or ProjectTrustCoordinator(
            ProjectTrustStore(
                unfiltered_resource_paths.paths or BaldricPaths(home=unfiltered_resource_paths.root)
            )
        )
        summary, trust_resolution = await coordinator.resolve(
            config.cwd,
            override=config.trust_override,
            default=config.trust_default,
            interactive=config.trust_interactive,
            prompt=config.trust_prompt,
            extension_deciders=(extension_runtime.decide_project_trust,),
            cache_result=False,
            persist=not config.defer_authoritative_writes,
        )
        canonical_cwd = summary.cwd.value
        resource_paths = resource_paths_with_project_trust(
            resource_paths_with_cwd(config.resource_paths, canonical_cwd),
            trusted=trust_resolution.trusted,
        )
        config = replace(
            config,
            cwd=canonical_cwd,
            resource_paths=resource_paths,
            project_trust_coordinator=coordinator,
            extension_runtime=extension_runtime,
        )
        resources = _load_session_resources(
            resource_paths,
            config.context_files,
            skills_enabled=config.skills_enabled,
            system_prompt_enabled=config.system is None,
            custom_system_prompt_explicit=config.custom_system_prompt is not None,
        )
        if summary.categories:
            resources = replace(
                resources,
                diagnostics=(
                    *resources.diagnostics,
                    ResourceDiagnostic(
                        kind="project-trust",
                        message=format_trust_diagnostic(summary, trust_resolution),
                        severity="info" if trust_resolution.trusted else "warning",
                    ),
                ),
            )

        if trust_resolution.trusted and config.project_extensions_enabled:
            extension_runtime.load(
                resource_paths,
                include_resource_dirs=True,
                include_project_dir=True,
                include_user_dir=False,
            )

        runtime_model_catalogs = dict(config.runtime_model_catalogs)
        if config.provider_settings is not None and "openai-codex" not in runtime_model_catalogs:
            codex_config = _provider_config_or_none(config.provider_settings, "openai-codex")
            if isinstance(codex_config, OpenAICodexProviderConfig):
                account_id = _codex_account_id(codex_config, credential_store)
                cached_catalog = cached_codex_model_catalog(
                    runtime_paths,
                    account_id=account_id,
                )
                if cached_catalog is not None:
                    runtime_model_catalogs["openai-codex"] = cached_catalog
        config = replace(config, runtime_model_catalogs=runtime_model_catalogs)
        selection_settings = _provider_settings_with_runtime_catalogs(
            config.provider_settings,
            runtime_model_catalogs,
        )
        selected_provider_name = config.requested_provider or state.provider or config.session_provider_name
        selected_model = config.requested_model or state.model
        rediscover_codex = False
        if selected_provider_name == "openai-codex" and config.provider_settings is not None:
            selected_config = _provider_config_or_none(
                config.provider_settings,
                selected_provider_name,
            )
            rediscover_codex = (
                isinstance(selected_config, OpenAICodexProviderConfig)
                and selected_model not in selected_config.models
            )
        preparation_settings = config.provider_settings
        startup_catalog: RuntimeModelCatalog | None = None
        effective_selected_config = (
            _provider_config_or_none(selection_settings, selected_provider_name)
            if selection_settings is not None
            else None
        )
        if (
            isinstance(effective_selected_config, OpenAICodexProviderConfig)
            and selected_model in effective_selected_config.models
        ):
            preparation_settings = selection_settings
        if config.provider is None or rediscover_codex:
            prepared = await _prepare_provider_selection(
                replace(config, provider_settings=preparation_settings),
                state=state,
                provider_registry=extension_runtime.provider_registry,
                credential_store=credential_store,
            )
            if config.provider is not None and config.owns_initial_provider:
                try:
                    await config.provider.aclose()  # type: ignore[attr-defined]
                except BaseException:
                    await prepared.provider.aclose()
                    raise
            startup_catalog = prepared.runtime_model_catalog
            if startup_catalog is not None:
                runtime_model_catalogs[prepared.provider_name] = startup_catalog
            config = replace(
                config,
                provider=prepared.provider,
                runtime_model_catalogs=runtime_model_catalogs,
                model=prepared.model,
                provider_name=prepared.provider_name,
                inference_provider=prepared.inference_provider,
                inference_provider_mode=prepared.inference_provider_mode,
                runtime_provider_config=prepared.runtime_provider_config,
                dynamic_provider=prepared.dynamic_provider,
                owns_initial_provider=True,
            )
            if pending_initial_entries:
                pending_initial_entries = tuple(
                    entry.model_copy(update={"model": config.model, "provider": config.provider_name})
                    if isinstance(entry, ModelChangeEntry)
                    else entry
                    for entry in pending_initial_entries
                )
                # Initial fallback metadata was created before live discovery.
                # Replay the corrected entries so runtime and durable selection agree.
                state = SessionState.from_entries(list(pending_initial_entries))
        assert config.provider is not None
        active_model = _runtime_model_for_state(config, state)
        image_support = ImageSupportState(supported=_configured_model_supports_images(config, active_model))
        base_tools = (
            config.tools
            if config.tools is not None
            else create_coding_tools(
                cwd=config.cwd,
                shell_command_prefix=config.shell_command_prefix,
                image_support=image_support,
            )
        )
        tools = _filter_tools(extension_runtime.compose_tools(base_tools), config.allowed_tool_names)
        system = (
            config.system
            if config.system is not None
            else build_system_prompt(
                BuildSystemPromptOptions(
                    cwd=config.cwd,
                    tools=tools,
                    skills=resources.skills,
                    custom_prompt=(
                        config.custom_system_prompt
                        if config.custom_system_prompt is not None
                        else resources.custom_system_prompt
                    ),
                    append_sections=_append_prompt_sections(
                        resources.append_system_prompts,
                        resources.append_system_prompt_paths,
                        config.append_system_prompt,
                    ),
                    context_files=resources.context_files,
                    extra_guidelines=extension_runtime.prompt_guidelines,
                    extra_sections=extension_runtime.sourced_prompt_sections,
                    custom_prompt_source=_custom_prompt_source(
                        explicit=config.custom_system_prompt is not None,
                        path=resources.custom_system_prompt_path,
                    ),
                )
            )
        )
        harness = AgentHarness(
            AgentHarnessConfig(
                provider=config.provider,
                model=active_model,
                system=system,
                tools=tools,
                session_id=config.session_id,
            ),
            messages=state.messages,
        )
        if previous_runtime is not None:
            extension_runtime.set_ui_bridge(previous_runtime.ui)
        session = cls(
            config,
            state=state,
            harness=harness,
            last_parent_id=_last_parent_id_from_state(state),
            skills=resources.skills,
            prompt_templates=resources.prompt_templates,
            context_files=resources.context_files,
            custom_system_prompt=resources.custom_system_prompt,
            custom_system_prompt_path=resources.custom_system_prompt_path,
            append_system_prompt=resources.append_system_prompt,
            append_system_prompts=resources.append_system_prompts,
            append_system_prompt_paths=resources.append_system_prompt_paths,
            resource_diagnostics=resources.diagnostics,
            command_registry=config.command_registry or extension_runtime.build_command_registry(),
            pending_initial_entries=pending_initial_entries,
            extension_runtime=extension_runtime,
            image_support=image_support,
            project_trust_resolution=trust_resolution,
        )
        if config.owns_initial_provider:
            # Ownership starts before any repair/discovery work so every
            # failure path has exactly one closer for the candidate.
            session._owned_providers.append(config.provider)  # type: ignore[arg-type]
        if startup_catalog is not None and config.provider_name == "openai-codex":
            session._persist_codex_model_catalog(
                config.provider,
                startup_catalog,
                (
                    config.runtime_provider_config
                    if isinstance(config.runtime_provider_config, OpenAICodexProviderConfig)
                    else None
                ),
            )
        await session._persist_active_tool_history_repairs()
        try:
            session._apply_runtime_model_catalogs()
            session._apply_thinking_level_override()
            session._sync_thinking_level_to_active_model()
            if not config.owns_initial_provider and config.provider is not None:
                session._refresh_runtime_provider()
            await session._refresh_runtime_model_limits()
            extension_runtime.bind(session)
            # Attach to session._harness, not the local `harness`:
            # Tool-history repair above updates the active harness before extension
            # listeners attach.
            extension_runtime.attach_harness_listener(session._harness.subscribe)
            # session_start is deferred: hosts emit it via emit_pending_session_start()
            # after installing their UI bridge.
            session._session_start_pending = True
            session._project_trust_commit_pending = not trust_resolution.cancelled
        except BaseException:
            # Once constructed, this session explicitly owns every candidate
            # provider until load returns it to the caller.
            await _finish_aborted_session_close(session)
            raise
        return session

    @property
    def cwd(self) -> Path:
        """Return the session working directory."""
        return self._config.cwd

    @property
    def model(self) -> str:
        """Return the active model for this session."""
        if self._preview_model is not None:
            return self._preview_model.model
        return self._harness.config.model

    @property
    def provider_name(self) -> str:
        """Return the active provider name."""
        if self._preview_model is not None:
            return self._preview_model.provider_name
        return self._provider_name

    @property
    def provider(self) -> ModelProvider:
        """Return the currently active runtime provider."""
        return self._harness.config.provider

    @property
    def inference_provider(self) -> str | None:
        """Return the pinned Hugging Face backing provider, if any."""
        return self._inference_provider

    @property
    def inference_provider_mode(self) -> InferenceProviderMode:
        """Return whether Hugging Face routing is automatic or explicitly fixed."""
        return self._inference_provider_mode

    @property
    def _active_dynamic_provider(self) -> DynamicProvider | None:
        effective = self._provider_registry.effective(self.provider_name)
        if effective is None or not isinstance(effective.definition, DynamicProvider):
            return None
        return effective.definition

    @property
    def _active_dynamic_model(self) -> ProviderModel | None:
        dynamic = self._active_dynamic_provider
        if dynamic is None:
            return None
        return next((model for model in dynamic.models if model.id == self.model), None)

    @property
    def available_providers(self) -> tuple[str, ...]:
        """Return provider names Baldric can call with available credentials."""
        names: list[str] = []
        if self._provider_settings is not None:
            names.extend(provider.name for provider in self._usable_provider_configs())
        for effective in self._provider_registry.effective_providers():
            if (
                isinstance(effective.definition, DynamicProvider)
                and (effective.definition.models or effective.definition.id == self._provider_name)
                and effective.definition.id not in names
            ):
                names.append(effective.definition.id)
        return tuple(names) or (self._provider_name,)

    def provider_config(self, provider_name: str) -> ProviderConfig | None:
        """Return configured metadata for a provider available to this session."""
        if self._provider_settings is None:
            return self._runtime_provider_config if provider_name == self.provider_name else None
        try:
            return self._provider_settings.get_provider(provider_name)
        except ProviderConfigError:
            return None

    @property
    def available_models(self) -> tuple[str, ...]:
        """Return model names for the active provider when it is usable."""
        dynamic = self._active_dynamic_provider
        if dynamic is not None:
            return tuple(model.id for model in dynamic.models)
        if self._provider_settings is None:
            return (self.model,)
        try:
            provider = self._provider_settings.get_provider(self.provider_name)
        except ProviderConfigError:
            return (self.model,)
        if not self._provider_is_usable(provider):
            return ()
        return provider.models

    @property
    def available_model_choices(self) -> tuple[ModelChoice, ...]:
        """Return provider/model choices from the effective runtime view."""
        choices: list[ModelChoice] = []
        dynamic_ids: set[str] = set()
        for effective in self._provider_registry.effective_providers():
            if isinstance(effective.definition, DynamicProvider):
                dynamic = effective.definition
                dynamic_ids.add(dynamic.id)
                choices.extend(ModelChoice(dynamic.id, model.id) for model in dynamic.models)
        if self._provider_settings is not None:
            choices.extend(
                ModelChoice(provider.name, model)
                for provider in self._usable_provider_configs()
                if provider.name not in dynamic_ids
                for model in provider.models
            )
        if not choices and self._provider_settings is None:
            return (ModelChoice(provider_name=self._provider_name, model=self.model),)
        return tuple(choices)

    @property
    def scoped_model_choices(self) -> tuple[ModelChoice, ...]:
        """Return scoped references, including inert trusted built-in references."""
        if self._provider_settings is None:
            return ()
        available = set(self.available_model_choices)
        choices: list[ModelChoice] = []
        for item in self._provider_settings.scoped_models:
            choice = ModelChoice(provider_name=item.provider, model=item.model)
            if choice in available or self._stable_dynamic_scoped_provider(item.provider):
                choices.append(choice)
        return tuple(choices)

    @property
    def has_stale_active_model(self) -> bool:
        """Whether the committed runtime model disappeared from the picker snapshot."""
        return ModelChoice(self._provider_name, self._harness.config.model) not in (
            self.available_model_choices
        )

    @property
    def unavailable_scoped_model_choices(self) -> tuple[ModelChoice, ...]:
        """Return persisted references that have no current provider snapshot row."""
        available = set(self.available_model_choices)
        return tuple(choice for choice in self.scoped_model_choices if choice not in available)

    def _stable_dynamic_scoped_provider(self, provider_name: str) -> bool:
        return any(
            layer.token.source_id.startswith("built-in:") and layer.provider.stable_scoped_references
            for layer in self._provider_registry.layers(provider_name)
        )

    def _effective_stable_dynamic_scoped_provider(self, provider_name: str) -> bool:
        effective = self._provider_registry.effective(provider_name)
        return bool(
            effective is not None
            and effective.source_id.startswith("built-in:")
            and isinstance(effective.definition, DynamicProvider)
            and effective.definition.stable_scoped_references
        )

    @property
    def tools(self) -> tuple[AgentTool, ...]:
        """Return the tools available to the agent."""
        return tuple(self._harness.config.tools)

    @property
    def extension_tool_sources(self) -> dict[str, str]:
        """Map active extension-provided tools to their owning extension."""
        return self._extension_runtime.extension_tool_sources

    @property
    def messages(self) -> tuple[AgentMessage, ...]:
        """Return the restored/current transcript."""
        return self._harness.messages

    @property
    def state(self) -> SessionState:
        """Return the last replayed durable session state."""
        return self._state

    async def session_entries(self) -> tuple[SessionEntry, ...]:
        """Return append-only entries for frontend session inspection."""
        return tuple(await self._read_session_entries())

    async def tree_choices(self) -> tuple[SessionTreeChoice, ...]:
        """Return branchable session entries for a tree picker."""
        entries = await self._read_session_entries()
        ordered_entries, branch_indents = _tree_layout(entries)
        labels_by_id, label_timestamps_by_id = _resolved_labels(entries)
        active_choice_id = _active_branchable_entry_id(entries, self._state.active_leaf_id)
        return tuple(
            SessionTreeChoice(
                entry_id=entry.id,
                label=_tree_choice_label(entry, branch_indent=branch_indents.get(entry.id, 0)),
                active=entry.id == active_choice_id,
                is_tool_call=_is_tool_call_tree_entry(entry),
                bookmark_label=labels_by_id.get(entry.id),
                label_timestamp=label_timestamps_by_id.get(entry.id),
            )
            for entry in ordered_entries
            if _is_branchable_tree_entry(entry)
        )

    async def set_label(self, target_id: str, label: str | None) -> LabelEntry:
        """Set or clear the bookmark on an existing session entry."""
        if self._harness.is_running:
            raise RuntimeError(TREE_RUNNING_MESSAGE)
        await self._flush_pending_message_writes(context=self._diagnostic_context())
        entries = await self._read_session_entries()
        if target_id not in {entry.id for entry in entries}:
            raise ValueError(f"Unknown session entry: {target_id}")
        normalized = label.strip() if label is not None else ""
        entry = LabelEntry(
            parent_id=self._last_parent_id,
            target_id=target_id,
            label=normalized or None,
        )
        await self._append_session_entry(entry)
        self._last_parent_id = entry.id
        await self._refresh_persisted_state(leaf_id=entry.id)
        return entry

    async def branch_to_entry(
        self,
        entry_id: str,
        *,
        summarize: bool = False,
        custom_instructions: str | None = None,
        replace_instructions: bool = False,
    ) -> SessionTreeBranchResult:
        """Move the active leaf to a previous entry, preserving existing history."""
        if self._harness.is_running:
            raise RuntimeError(TREE_RUNNING_MESSAGE)
        await self._flush_pending_message_writes(context=self._diagnostic_context())
        entries = await self._read_session_entries()
        by_id = {entry.id: entry for entry in entries}
        if entry_id not in by_id:
            raise ValueError(f"Unknown session entry: {entry_id}")
        selected_entry = by_id[entry_id]
        if not _is_branchable_tree_entry(selected_entry):
            raise ValueError(f"Session entry cannot be branched from: {entry_id}")

        target_id: str | None = entry_id
        input_prefill: str | None = None
        summary_entry: BranchSummaryEntry | None = None
        if summarize:
            abandoned_messages = _messages_after_entry_on_active_path(
                entries,
                entry_id,
                self._last_parent_id,
            )
            if abandoned_messages:
                generated = await self._summarize_branch_messages(
                    abandoned_messages,
                    custom_instructions=custom_instructions,
                    replace_instructions=replace_instructions,
                )
                summary_entry = BranchSummaryEntry(
                    parent_id=entry_id,
                    branch_root_id=entry_id,
                    summary=generated.text,
                    usage=generated.usage,
                    provider=generated.provider,
                    model=generated.model,
                    response_provider=generated.response_provider,
                )
                await self._append_session_entry(summary_entry)
                target_id = summary_entry.id
        elif selected_entry.type == "message" and isinstance(selected_entry.message, UserMessage):
            target_id = selected_entry.parent_id
            input_prefill = selected_entry.message.text

        self._preview_model = None
        self._preview_thinking = None
        self._last_parent_id = target_id

        # Plain navigation is in-memory only. A summary above is the sole write,
        # and becomes the file-order tip when present.
        await self._refresh_persisted_state(leaf_id=target_id)
        history_repair = await self._persist_active_tool_history_repairs()
        if history_repair is None:
            self._harness.replace_messages(self._state.messages)
        self._invalidate_context_usage_cache()
        self._thinking_level = _state_thinking_level(
            self._state,
            default=_default_thinking_level_for_active_model(self),
        )
        self._sync_thinking_level_to_active_model()
        self._refresh_runtime_provider()
        suffix = " with branch summary" if summary_entry is not None else ""
        if history_repair is not None:
            suffix += " and repaired malformed tool history"
        if input_prefill is not None:
            return SessionTreeBranchResult(
                message=f"Branched session before {entry_id}{suffix}.",
                input_prefill=input_prefill,
            )
        return SessionTreeBranchResult(message=f"Branched session at {target_id}{suffix}.")

    @property
    def thinking_level(self) -> ThinkingLevel:
        """Return the active thinking mode for future turns."""
        if self._preview_thinking is not None:
            return self._preview_thinking
        return self._thinking_level

    @property
    def available_thinking_levels(self) -> tuple[ThinkingLevel, ...]:
        """Return thinking modes supported by the active provider/model."""
        dynamic = self._active_dynamic_provider
        if dynamic is not None:
            model = self._active_dynamic_model
            if model is None:
                return ()
            return model.thinking_levels or ()
        if self._provider_settings is None:
            return THINKING_LEVELS
        provider = self._selected_provider_config()
        if provider is None:
            return ()
        return provider_thinking_levels(provider, model=self.model)

    @property
    def thinking_unavailable_reason(self) -> str | None:
        """Return why thinking controls are unavailable for the active model."""
        if self.available_thinking_levels:
            return None
        dynamic = self._active_dynamic_provider
        if dynamic is not None:
            model = self._active_dynamic_model
            if model is None:
                return f"{self.provider_name}:{self.model} metadata is not available"
            if model.thinking_levels is None:
                return f"{self.provider_name}:{self.model} does not declare configurable thinking levels"
            return f"{self.provider_name}:{self.model} declares no configurable thinking levels"
        provider = self._selected_provider_config()
        if provider is None:
            return "Active provider settings are not available"
        return provider_thinking_unavailable_reason(provider, model=self.model)

    @property
    def storage(self) -> SessionStorage:
        """Return the backing session storage."""
        return self._config.storage

    async def export(
        self,
        destination: Path | None = None,
        *,
        format: str | None = None,
    ) -> Path:
        """Export the current session to a user-facing artifact."""
        entries = await self._read_session_entries()
        session_path = _storage_path(self._config.storage)
        export_format = normalize_export_format(
            format or (destination.suffix.removeprefix(".") if destination else "html")
        )
        output_path = _resolve_export_destination(
            destination,
            cwd=self.cwd,
            session_path=session_path,
            format=export_format,
        )
        return export_session_artifact(
            entries,
            output_path,
            title=_session_export_title(self),
            source=str(session_path) if session_path is not None else self.session_id,
            format=export_format,
            system_prompt=self.system_prompt,
        )

    @property
    def skills(self) -> tuple[Skill, ...]:
        """Return loaded skills."""
        return self._skills

    @property
    def prompt_templates(self) -> tuple[PromptTemplate, ...]:
        """Return loaded prompt templates."""
        return self._prompt_templates

    @property
    def context_files(self) -> tuple[ProjectContextFile, ...]:
        """Return active project context files."""
        return self._context_files

    @property
    def system_prompt_files(self) -> tuple[Path, ...]:
        """Return active discovered system-prompt resource files."""
        custom_paths = (
            (self._custom_system_prompt_path,) if self._custom_system_prompt_path is not None else ()
        )
        return (*custom_paths, *self._append_system_prompt_paths)

    @property
    def context_token_estimate(self) -> int:
        """Return the best available token count for the active provider context."""
        return self.context_usage.total_tokens

    @property
    def has_provider_context_usage(self) -> bool:
        """Return whether valid provider usage anchors the active context count."""
        return self.context_usage.uses_provider_usage

    @property
    def context_usage(self) -> ContextUsageEstimate:
        """Return structured context accounting for the active provider context."""
        if self._context_usage_cache is None:
            self._context_usage_cache = estimate_context_usage(
                system=self._harness.config.system,
                messages=self._harness.messages,
                tools=tuple(self._harness.config.tools),
            )
        return self._context_usage_cache

    @property
    def system_prompt(self) -> str:
        """Return the effective system prompt sent to the model."""
        return self._harness.config.system

    @property
    def system_prompt_inspection(self) -> SystemPromptInspection:
        """Return the effective prompt with source attribution for local inspection."""
        if self._config.system is not None:
            return SystemPromptInspection(
                text=self.system_prompt,
                sources=(
                    SystemPromptSource(
                        kind="system",
                        label="System prompt override",
                        source="CodingSessionConfig.system",
                        content=self.system_prompt,
                    ),
                ),
            )
        inspection = build_system_prompt_inspection(
            BuildSystemPromptOptions(
                cwd=self.cwd,
                tools=self.tools,
                skills=self.skills,
                custom_prompt=(
                    self._config.custom_system_prompt
                    if self._config.custom_system_prompt is not None
                    else self._custom_system_prompt
                ),
                append_sections=_append_prompt_sections(
                    self._append_system_prompts,
                    self._append_system_prompt_paths,
                    self._config.append_system_prompt,
                ),
                context_files=self.context_files,
                extra_guidelines=self._extension_runtime.prompt_guidelines,
                extra_sections=self._extension_runtime.sourced_prompt_sections,
                custom_prompt_source=_custom_prompt_source(
                    explicit=self._config.custom_system_prompt is not None,
                    path=self._custom_system_prompt_path,
                ),
            )
        )
        if inspection.text == self.system_prompt:
            return inspection
        return SystemPromptInspection(
            text=self.system_prompt,
            sources=(
                SystemPromptSource(
                    kind="runtime",
                    label="Effective system prompt",
                    source="active Baldric session (runtime-composed)",
                    content=self.system_prompt,
                ),
            ),
        )

    @property
    def auto_compact_token_threshold(self) -> int | None:
        """Return the effective automatic compaction threshold, if any."""
        if not self._auto_compact_enabled:
            return None
        if self._auto_compact_token_threshold is not None:
            return self._auto_compact_token_threshold
        if self._runtime_model_limits_key == (self.provider_name, self.model):
            limits = self._runtime_model_limits
            if limits is not None:
                return limits.effective_auto_compact_token_limit
        return auto_compaction_threshold_for_context_window(self.context_window_tokens)

    def set_auto_compaction_enabled(self, enabled: bool) -> None:
        """Enable or disable automatic compaction for future turns."""
        self._auto_compact_enabled = enabled
        self._config = replace(self._config, auto_compact_enabled=enabled)

    @property
    def auto_compaction_enabled(self) -> bool:
        """Return whether automatic compaction is enabled."""
        return self._auto_compact_enabled

    @property
    def context_window_tokens(self) -> int:
        """Return the active model's discovered or configured context window."""
        if self._runtime_model_limits_key == (self.provider_name, self.model):
            limits = self._runtime_model_limits
            if limits is not None:
                return limits.context_window
        provider = self._active_provider_config()
        if provider is None:
            return DEFAULT_CONTEXT_WINDOW_TOKENS
        return provider.context_windows.get(self.model, DEFAULT_CONTEXT_WINDOW_TOKENS)

    @property
    def context_window_source(self) -> str:
        """Return where the active context-window limit came from."""
        if (
            self._runtime_model_limits_key == (self.provider_name, self.model)
            and self._runtime_model_limits is not None
        ):
            return "provider live catalog"
        return "configured catalog"

    @property
    def model_limits_discovery_error(self) -> str | None:
        """Return the last non-fatal live model-limit discovery error."""
        return self._model_limits_discovery_error

    @property
    def command_registry(self) -> CommandRegistry:
        """Return the slash-command registry used by this session."""
        return self._command_registry

    @property
    def project_trust_resolution(self) -> ProjectTrustResolution | None:
        """Return this cwd's completed project-input trust resolution."""
        return self._project_trust_resolution

    @property
    def theme_dirs(self) -> tuple[Path, ...]:
        """Return theme directories permitted by this session's trust snapshot."""
        return self._resource_paths.themes_dirs

    @property
    def resource_diagnostics(self) -> tuple[ResourceDiagnostic, ...]:
        """Return non-fatal resource and extension diagnostics."""
        trust_diagnostics: tuple[ResourceDiagnostic, ...] = ()
        if self._project_trust_resolution is not None:
            trust_diagnostics = tuple(
                ResourceDiagnostic(kind="project-trust", message=message, severity="error")
                for message in self._project_trust_resolution.diagnostics
            )
        return self._resource_diagnostics + trust_diagnostics + self._extension_runtime.diagnostics

    @property
    def extension_runtime(self) -> ExtensionRuntime:
        """Return the extension runtime bound to this session."""
        return self._extension_runtime

    @property
    def extension_names(self) -> tuple[str, ...]:
        """Return loaded extension names in load order."""
        return self._extension_runtime.extension_names

    @property
    def session_stats(self) -> SessionStats:
        """Return cumulative activity and billed usage for the active branch."""
        cached = self._session_stats_cache
        if cached is not None and cached[0] is self._state and cached[1] is self._config:
            return cached[2]
        stats = calculate_session_stats(self._state.entries, pricing=self._pricing_for_response)
        self._session_stats_cache = (self._state, self._config, stats)
        return stats

    def _pricing_for_response(
        self,
        provider_name: str,
        model: str,
        input_tokens: int,
    ) -> dict[str, float] | None:
        provider = _provider_config_for_name(self._config, provider_name)
        if provider is None or provider.name != provider_name or not hasattr(provider, "model_metadata"):
            return None
        metadata = provider.model_metadata.get(model)
        if metadata is None:
            return None
        for tier in metadata.cost_tiers:
            if tier.max_input_tokens is None or input_tokens <= tier.max_input_tokens:
                return dict(tier.cost)
        return dict(metadata.cost) if metadata.cost else None

    async def emit_pending_session_start(self) -> None:
        """Emit the `session_start` deferred by `load`, once per session.

        Hosts call this after installing their UI bridge so `session_start`
        handlers can use notifications and dialogs (Pi's ordering: the UI
        starts before extensions initialize). Idempotent; a no-op for
        sessions that adopted an already-started extension runtime.
        """
        if not self._session_start_pending:
            return
        await self._extension_runtime.emit_session_start("startup")
        self._commit_project_trust_resolution()
        self._session_start_pending = False

    def _commit_project_trust_resolution(self) -> None:
        """Publish staged trust only after the session becomes live."""
        if not self._project_trust_commit_pending:
            return
        coordinator = self._config.project_trust_coordinator
        resolution = self._project_trust_resolution
        if coordinator is not None and resolution is not None:
            coordinator.commit(CanonicalProjectPath(self.cwd), resolution)
        self._project_trust_commit_pending = False

    def queue_steering_message(
        self,
        content: str,
        *,
        custom_type: str | None = None,
        details: dict[str, JSONValue] | None = None,
    ) -> None:
        """Queue a steering user message (extension runtime seam)."""
        message: AgentMessage = (
            CustomMessage(custom_type=custom_type, content=content, details=details)
            if custom_type is not None
            else UserMessage(content=content)
        )
        self._harness.steer_message(message)

    def queue_follow_up_message(
        self,
        content: str,
        *,
        custom_type: str | None = None,
        details: dict[str, JSONValue] | None = None,
    ) -> None:
        """Queue a follow-up user message (extension runtime seam)."""
        message: AgentMessage = (
            CustomMessage(custom_type=custom_type, content=content, details=details)
            if custom_type is not None
            else UserMessage(content=content)
        )
        self._harness.follow_up_message(message)

    async def append_custom_entry(self, namespace: str, data: dict[str, JSONValue]) -> None:
        """Persist an extension-owned custom entry on the active branch path.

        The entry advances the append-only tree parent chain so it stays on the
        replayed root-to-leaf path (off-path custom entries would be invisible
        to `SessionState` after resume).
        """
        entry = CustomEntry(parent_id=self._last_parent_id, namespace=namespace, data=data)
        await self._append_session_entry(entry)
        self._last_parent_id = entry.id
        await self._refresh_persisted_state(leaf_id=entry.id)

    @property
    def session_id(self) -> str | None:
        """Return this session's manager id, if indexed."""
        return self._config.session_id

    @property
    def session_title(self) -> str | None:
        """Return this session's indexed human-friendly title, if named."""
        if self._config.session_id is None or self._config.session_manager is None:
            return None
        record = self._config.session_manager.get_session(self._config.session_id, cwd=self.cwd)
        if record is None:
            return None
        return record.title

    @property
    def session_name(self) -> str | None:
        """Return this session's indexed human-friendly name, if named."""
        return self.session_title

    @property
    def session_manager(self) -> SessionManager | None:
        """Return the session manager, if available."""
        return self._config.session_manager

    @property
    def is_running(self) -> bool:
        """Return whether this session currently has an active agent run."""
        return self._harness.is_running

    def _require_idle(self, operation: str) -> None:
        """Reject replacement-like operations until an active turn is drained."""
        if self._harness.is_running:
            raise RuntimeError(
                f"Cannot {operation} while Baldric is working. "
                "Press Escape to interrupt and wait for it to finish."
            )

    @property
    def queued_message_count(self) -> int:
        """Return the number of queued steering and follow-up messages."""
        return self._harness.pending_message_count

    @property
    def queued_messages(self) -> QueuedMessages:
        """Return queued steering and follow-up messages."""
        return self._harness.queued_messages

    @property
    def queued_steering_messages(self) -> tuple[str, ...]:
        """Return queued steering message text for UI display."""
        return tuple(message_text(message) for message in self._harness.queued_messages.steering)

    @property
    def queued_follow_up_messages(self) -> tuple[str, ...]:
        """Return queued follow-up message text for UI display."""
        return tuple(message_text(message) for message in self._harness.queued_messages.follow_up)

    @property
    def last_diagnostic_log_path(self) -> Path | None:
        """Return the last diagnostic log path written by this session."""
        return self._last_diagnostic_log_path

    def set_project_trust_prompt(self, prompt: TrustPrompt) -> None:
        """Install the active frontend's trust prompt for reload/replacement."""
        self._config = replace(
            self._config,
            trust_interactive=True,
            trust_prompt=prompt,
        )

    def cancel(self) -> None:
        """Cancel the currently running agent turn, if any."""
        self._harness.cancel()

    def queue_update_event(self) -> QueueUpdateEvent:
        """Return the current queue state as a coding-session event."""
        return QueueUpdateEvent(
            steering=self.queued_steering_messages,
            follow_up=self.queued_follow_up_messages,
        )

    def clear_queued_messages(self) -> QueuedMessages:
        """Clear queued steering and follow-up messages."""
        return self._harness.clear_queues()

    def pop_latest_follow_up_message(self) -> str | None:
        """Remove and return the most recently queued follow-up message."""
        message = self._harness.pop_latest_follow_up()
        return None if message is None else message_text(message)

    def pop_latest_steering_message(self) -> str | None:
        """Remove and return the most recently queued steering message."""
        message = self._harness.pop_latest_steering()
        return None if message is None else message_text(message)

    def set_model(self, model: str) -> None:
        return _model_selection.set_model(self, model)

    async def apply_startup_model_override(self, model: str) -> None:
        return await _model_selection.apply_startup_model_override(self, model)

    async def select_provider_model(
        self, choice: ModelChoice, *, persist_default: bool = True
    ) -> ModelSelectionResult:
        return await _model_selection.select_provider_model(self, choice, persist_default=persist_default)

    def set_inference_provider(self, route: str | None) -> str:
        return _model_selection.set_inference_provider(self, route)

    def set_model_choice(self, choice: ModelChoice) -> None:
        return _model_selection.set_model_choice(self, choice)

    def is_scoped_model(self, choice: ModelChoice) -> bool:
        return _model_selection.is_scoped_model(self, choice)

    def toggle_scoped_model(self, choice: ModelChoice) -> tuple[ModelChoice, ...]:
        return _model_selection.toggle_scoped_model(self, choice)

    @property
    def has_pending_selection(self) -> bool:
        return _model_selection.has_pending_selection(self)

    def preview_model_choice(self, choice: ModelChoice) -> None:
        return _model_selection.preview_model_choice(self, choice)

    def preview_thinking_level(self, level: str) -> str:
        return _model_selection.preview_thinking_level(self, level)

    def preview_cycle_thinking_level(self) -> str:
        return _model_selection.preview_cycle_thinking_level(self)

    def preview_cycle_scoped_model(self, *, reverse: bool = False) -> ModelChoice:
        return _model_selection.preview_cycle_scoped_model(self, reverse=reverse)

    async def _commit_preview(self) -> None:
        return await _model_selection._commit_preview(self)

    def cycle_scoped_model(self, *, reverse: bool = False) -> ModelChoice:
        return _model_selection.cycle_scoped_model(self, reverse=reverse)

    def set_provider(self, provider_name: str, *, persist_default: bool = True) -> None:
        return _model_selection.set_provider(self, provider_name, persist_default=persist_default)

    def _set_provider_model(self, provider_name: str, model: str, *, persist_default: bool = True) -> None:
        return _model_selection._set_provider_model(
            self, provider_name, model, persist_default=persist_default
        )

    async def set_thinking_level(self, level: str, *, persist_preference: bool = True) -> str:
        return await _model_selection.set_thinking_level(self, level, persist_preference=persist_preference)

    async def cycle_thinking_level(self) -> str:
        return await _model_selection.cycle_thinking_level(self)

    def _selected_provider_config(self) -> ProviderConfig | None:
        return _model_selection._selected_provider_config(self)

    def _active_provider_config(self) -> ProviderConfig | None:
        return _model_selection._active_provider_config(self)

    def _apply_thinking_level_override(self) -> None:
        return _model_selection._apply_thinking_level_override(self)

    def _sync_thinking_level_to_active_model(self) -> None:
        return _model_selection._sync_thinking_level_to_active_model(self)

    def _sync_image_support(self) -> None:
        return _model_selection._sync_image_support(self)

    def _persist_default_model_choice(self) -> None:
        return _model_selection._persist_default_model_choice(self)

    def _persist_thinking_level_choice(self) -> None:
        return _model_selection._persist_thinking_level_choice(self)

    def _observe_response_headers(self, headers: Mapping[str, str]) -> None:
        if (
            self.provider_name != "huggingface"
            or self._inference_provider_mode != "automatic"
            or self._inference_provider is not None
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
        provider, provider_config = self._build_runtime_provider(
            inference_provider=route,
        )
        # Track staged providers immediately so a later index-write failure does
        # not leak a provider-owned client. The active runtime remains unchanged.
        self._owned_providers.append(provider)
        if self._config.session_manager is not None and self._config.session_id is not None:
            self._config.session_manager.touch_session(
                self._config.session_id,
                model=self.model,
                provider_name=self.provider_name,
                inference_provider=route,
                inference_provider_mode="automatic",
                preserve_inference_provider=False,
            )
        self._inference_provider = route
        self._config = replace(
            self._config,
            inference_provider=route,
            inference_provider_mode="automatic",
        )
        self._activate_runtime_provider(provider, provider_config)

    def will_auto_retry(self, message: AssistantMessage) -> bool:
        """Return whether session orchestration will retry this assistant error."""
        return is_context_overflow_error(message) or self._should_auto_failover_huggingface_route(message)

    def _should_auto_failover_huggingface_route(
        self,
        message: AssistantMessage,
    ) -> bool:
        return (
            self.provider_name == "huggingface"
            and self._inference_provider_mode == "automatic"
            and self._inference_provider is not None
            and is_retryable_huggingface_route_error(message)
        )

    def _reset_automatic_inference_provider_for_failover(self) -> str:
        failed_route = self._inference_provider
        if failed_route is None:
            raise ProviderConfigError("Hugging Face failover requires a pinned route")
        provider, provider_config = self._build_runtime_provider(inference_provider=None)
        self._owned_providers.append(provider)
        if self._config.session_manager is not None and self._config.session_id is not None:
            self._config.session_manager.touch_session(
                self._config.session_id,
                model=self.model,
                provider_name=self.provider_name,
                inference_provider=None,
                inference_provider_mode="automatic",
                preserve_inference_provider=False,
            )
        self._inference_provider = None
        self._config = replace(
            self._config,
            inference_provider=None,
            inference_provider_mode="automatic",
        )
        self._activate_runtime_provider(provider, provider_config)
        return failed_route

    async def _run_huggingface_route_failover(
        self,
        *,
        context: AgentCallDiagnosticContext,
    ) -> AsyncIterator[CodingSessionEvent]:
        """Retry the interrupted run once through unsuffixed Hugging Face routing."""
        failed_route = self._reset_automatic_inference_provider_for_failover()
        retry_start = AutoRetryStartEvent(
            attempt=1,
            max_attempts=1,
            delay_ms=0,
            error_message=f"Hugging Face route {failed_route} failed; rerouting automatically",
        )
        await self._extension_runtime.emit_event(retry_start)
        yield retry_start

        retry_events = self._harness.continue_()
        self._invalidate_context_usage_cache()
        final_error: str | None = None
        try:
            async for retry_event in retry_events:
                if isinstance(retry_event, ToolExecutionEndEvent):
                    self._invalidate_context_usage_cache()
                if (
                    isinstance(retry_event, MessageEndEvent)
                    and isinstance(retry_event.message, AssistantMessage)
                    and retry_event.message.stop_reason in {"error", "aborted"}
                ):
                    final_error = retry_event.message.error_message or "Provider request aborted"
                    if retry_event.message.stop_reason == "error":
                        self._last_diagnostic_log_path = self._diagnostic_logger.log_assistant_error(
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
        self._last_diagnostic_log_path = self._diagnostic_logger.log_huggingface_route_failover(
            context=context,
            failed_route=failed_route,
            replacement_route=self._inference_provider,
            success=failover_succeeded,
            error_message=final_error,
        )
        retry_end = AutoRetryEndEvent(
            success=failover_succeeded,
            attempt=1,
            final_error=final_error,
        )
        await self._extension_runtime.emit_event(retry_end)
        yield retry_end

    def _build_runtime_provider(
        self,
        *,
        inference_provider: str | None,
    ) -> tuple[ClosableModelProvider, ProviderConfig]:
        if self._runtime_provider_config is None:
            raise ProviderConfigError("Runtime provider configuration is unavailable")
        provider_config = self._active_provider_config() or self._runtime_provider_config
        committed_model = self._harness.config.model
        validate_provider_model(provider_config, committed_model)
        try:
            provider = _create_runtime_provider(
                provider_config,
                credential_store=self._credential_store,
                model=committed_model,
                thinking_level=self._thinking_level,
                inference_provider=inference_provider,
                response_headers_observer=(
                    self._observe_response_headers if provider_config.name == "huggingface" else None
                ),
            )
        except RuntimeError as exc:
            raise ProviderConfigError(str(exc)) from exc
        return provider, provider_config

    def _activate_runtime_provider(
        self,
        provider: ClosableModelProvider,
        provider_config: ProviderConfig,
    ) -> None:
        self._harness.config.provider = provider
        self._runtime_provider_config = provider_config
        self._invalidate_runtime_model_limits()

    def _refresh_runtime_provider(self) -> None:
        if self._runtime_provider_config is None:
            return
        provider, provider_config = self._build_runtime_provider(
            inference_provider=self._inference_provider,
        )
        self._owned_providers.append(provider)
        self._activate_runtime_provider(provider, provider_config)

    def _invalidate_runtime_model_limits(self) -> None:
        self._runtime_model_limits = None
        self._runtime_model_limits_key = None
        self._model_limits_discovery_error = None

    async def _refresh_runtime_model_limits(self) -> None:
        key = (self.provider_name, self.model)
        if self._runtime_model_limits_key == key:
            return
        self._runtime_model_limits = None
        self._runtime_model_limits_key = key
        self._model_limits_discovery_error = None
        provider = self._harness.config.provider
        if (
            self.provider_name == "openai-codex"
            and isinstance(provider, ModelCatalogProvider)
            and environ.get("BALDRIC_OFFLINE") is not None
        ):
            return
        try:
            cached_catalog = self._runtime_model_catalogs.get(self.provider_name)
            if self.provider_name == "openai-codex" and cached_catalog is not None:
                model = cached_catalog.model(self.model)
                self._runtime_model_limits = model.limits if model is not None else None
                return
            if isinstance(provider, ModelCatalogProvider):
                catalog = await provider.discover_models()
                self._publish_runtime_model_catalog(self.provider_name, catalog)
                if self.provider_name == "openai-codex":
                    self._persist_codex_model_catalog(provider, catalog)
            if isinstance(provider, ModelLimitsProvider):
                self._runtime_model_limits = await provider.discover_model_limits(self.model)
        except Exception as exc:  # noqa: BLE001 - static catalog remains the safe fallback
            error = f"{type(exc).__name__}: {exc}"
            self._model_limits_discovery_error = error
            if isinstance(provider, ModelCatalogProvider):
                self._model_catalog_discovery_errors[self.provider_name] = error

    async def reload(self) -> CodingReloadSummary:
        """Stage and atomically publish a complete replacement snapshot."""
        self._require_idle("reload")
        before_skills = _skill_signatures(self._skills)
        before_prompt_templates = _prompt_template_signatures(self._prompt_templates)
        before_context_files = _context_file_signatures(self._context_files)
        before_diagnostics = _diagnostic_signatures(self.resource_diagnostics)
        before_system_prompt_inputs = _system_prompt_resource_signatures(
            skills=self._skills,
            context_files=self._context_files,
            custom_system_prompt=self._custom_system_prompt,
            custom_system_prompt_path=self._custom_system_prompt_path,
            append_system_prompt=self._append_system_prompt,
            append_system_prompt_paths=self._append_system_prompt_paths,
        )
        before_extensions = _extension_signatures(self._extension_runtime)
        before_tool_names = tuple(tool.name for tool in self._harness.config.tools)
        before_guidelines = self._extension_runtime.prompt_guidelines
        before_sections = self._extension_runtime.sourced_prompt_sections

        # Nothing below mutates the live session. Eligible extensions are loaded
        # first so project code cannot import before the destination decision.
        unfiltered_paths = resource_paths_with_cwd(self._config.resource_paths, self.cwd)
        previous_ui = self._extension_runtime.ui
        staged_runtime = ExtensionRuntime(
            durable_providers=(self._provider_settings.providers if self._provider_settings else ()),
            credentials=self._extension_runtime.provider_credentials or self._credential_store,
            environment=self._extension_runtime.provider_environment,
            built_in_credentials=self._extension_runtime.built_in_credentials,
            built_in_http_client=self._extension_runtime.built_in_http_client,
            paths=(
                self._resource_paths.paths
                or BaldricPaths(
                    home=self._resource_paths.root,
                    agents_home=self._resource_paths.agents_root or Path.home() / ".agents",
                )
            ),
        )
        staged_runtime.load(
            unfiltered_paths,
            extra_paths=self._config.extension_paths,
            include_resource_dirs=self._config.extensions_enabled,
            include_project_dir=False,
        )

        staged_resolution = self._project_trust_resolution
        staged_paths = self._resource_paths
        coordinator = self._config.project_trust_coordinator
        trust_summary = None
        if coordinator is not None:
            trust_summary, staged_resolution = await coordinator.resolve(
                self.cwd,
                override=self._config.trust_override,
                default=self._config.trust_default,
                interactive=self._config.trust_interactive,
                prompt=self._config.trust_prompt,
                extension_deciders=(staged_runtime.decide_project_trust,),
                refresh=True,
                cache_result=False,
            )
            if staged_resolution.cancelled:
                raise ValueError("Project trust decision cancelled; keeping current resources")
            staged_paths = resource_paths_with_project_trust(
                resource_paths_with_cwd(self._config.resource_paths, trust_summary.cwd.value),
                trusted=staged_resolution.trusted,
            )

        resources = _load_session_resources(
            staged_paths,
            self._config.context_files,
            skills_enabled=self._config.skills_enabled,
            system_prompt_enabled=self._config.system is None,
            custom_system_prompt_explicit=self._config.custom_system_prompt is not None,
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
            and self._config.project_extensions_enabled
        ):
            staged_runtime.load(
                staged_paths,
                include_resource_dirs=True,
                include_project_dir=True,
                include_user_dir=False,
            )

        base_tools = (
            self._config.tools
            if self._config.tools is not None
            else create_coding_tools(
                cwd=self._config.cwd,
                shell_command_prefix=self._config.shell_command_prefix,
                image_support=self._image_support,
            )
        )
        staged_tools = _filter_tools(
            staged_runtime.compose_tools(base_tools), self._config.allowed_tool_names
        )
        staged_commands = self._config.command_registry or staged_runtime.build_command_registry()
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
        system_prompt_rebuilt = self._config.system is None and (
            before_system_prompt_inputs != after_system_prompt_inputs
            or before_tool_names != tuple(tool.name for tool in staged_tools)
            or before_guidelines != after_guidelines
            or before_sections != after_sections
        )
        staged_system = self._harness.config.system
        if system_prompt_rebuilt:
            staged_system = build_system_prompt(
                BuildSystemPromptOptions(
                    cwd=self._config.cwd,
                    tools=staged_tools,
                    skills=resources.skills,
                    custom_prompt=(
                        self._config.custom_system_prompt
                        if self._config.custom_system_prompt is not None
                        else resources.custom_system_prompt
                    ),
                    append_sections=_append_prompt_sections(
                        resources.append_system_prompts,
                        resources.append_system_prompt_paths,
                        self._config.append_system_prompt,
                    ),
                    context_files=resources.context_files,
                    extra_guidelines=after_guidelines,
                    extra_sections=after_sections,
                    custom_prompt_source=_custom_prompt_source(
                        explicit=self._config.custom_system_prompt is not None,
                        path=resources.custom_system_prompt_path,
                    ),
                )
            )

        # Cancellable lifecycle work stays before the publication boundary. The
        # staged runtime may inspect the still-live session during session_start;
        # cancellation leaves that prior snapshot/runtime/cache untouched.
        old_runtime = self._extension_runtime
        await old_runtime.emit_session_shutdown("reload")
        old_runtime.clear_ui_components()
        staged_runtime.set_ui_bridge(previous_ui)
        staged_runtime.bind(self)
        await staged_runtime.emit_session_start("reload")

        # Publication is synchronous: cancellation can no longer report failure
        # after only part of the live snapshot or trust cache was adopted.
        if coordinator is not None and trust_summary is not None:
            assert staged_resolution is not None
            coordinator.commit(trust_summary.cwd, staged_resolution)
        old_runtime.retire()
        self._resource_paths = staged_paths
        self._config = replace(
            self._config,
            cwd=staged_paths.cwd or self._config.cwd,
            resource_paths=staged_paths,
            extension_runtime=staged_runtime,
        )
        self._project_trust_resolution = staged_resolution
        self._skills = resources.skills
        self._prompt_templates = resources.prompt_templates
        self._context_files = resources.context_files
        self._custom_system_prompt = resources.custom_system_prompt
        self._custom_system_prompt_path = resources.custom_system_prompt_path
        self._append_system_prompt = resources.append_system_prompt
        self._append_system_prompts = resources.append_system_prompts
        self._append_system_prompt_paths = resources.append_system_prompt_paths
        self._resource_diagnostics = resources.diagnostics
        self._command_registry = staged_commands
        self._extension_runtime = staged_runtime
        self._provider_registry = staged_runtime.provider_registry
        self._harness.config.tools = staged_tools
        self._harness.config.system = staged_system
        if system_prompt_rebuilt:
            self._invalidate_context_usage_cache()
        staged_runtime.attach_harness_listener(self._harness.subscribe)
        # Retirement invalidates publication synchronously; async close then
        # waits for cooperative provider callback cleanup or reports bounded
        # containment while the outgoing runtime still owns every task handle.
        # Caller cancellation at this committed seam is contained so reload
        # cannot report failure after the fresh snapshot became active.
        await _finish_adopted_runtime_close(old_runtime)

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
                before_diagnostics, _diagnostic_signatures(self.resource_diagnostics)
            ),
            system_prompt_rebuilt=system_prompt_rebuilt,
        )

    async def refresh_model_catalogs(self, *, force: bool = False) -> ModelsDevRefreshResult:
        """Refresh public and authenticated catalogs and publish them to this session."""
        public_error: Exception | None = None
        result: ModelsDevRefreshResult | None = None
        try:
            result = await refresh_models_dev_catalog(
                paths=self._resource_paths.paths,
                force=force,
            )
            self.reload_provider_settings()
        except Exception as error:  # noqa: BLE001 - authenticated refresh still runs
            public_error = error
        await self._refresh_codex_model_catalog()
        if public_error is not None:
            raise public_error
        assert result is not None
        return result

    async def _refresh_codex_model_catalog(self) -> None:
        """Refresh the account-specific Codex inventory without making it durable."""
        if environ.get("BALDRIC_OFFLINE") is not None or self._durable_provider_settings is None:
            return
        try:
            provider_config = self._durable_provider_settings.get_provider("openai-codex")
        except ProviderConfigError:
            return
        if not isinstance(provider_config, OpenAICodexProviderConfig):
            return
        if not self._provider_is_usable(provider_config):
            return

        # Use a fresh provider even when Codex is active. The active provider caches
        # its startup snapshot so reusing it would make `/model` unable to discover
        # versions or models released during a long-running Baldric process.
        temporary_provider = create_model_provider(
            provider_config,
            credential_store=self._credential_store,
            model=None,
            thinking_level=None,
        )
        if not isinstance(temporary_provider, ModelCatalogProvider):
            await temporary_provider.aclose()
            return
        try:
            catalog = await temporary_provider.discover_models()
            self._publish_runtime_model_catalog(provider_config.name, catalog)
            self._persist_codex_model_catalog(temporary_provider, catalog, provider_config)
        except Exception as exc:  # noqa: BLE001 - static catalog remains the safe fallback
            self._model_catalog_discovery_errors[provider_config.name] = f"{type(exc).__name__}: {exc}"
        finally:
            await temporary_provider.aclose()

    def _persist_codex_model_catalog(
        self,
        provider: object,
        catalog: RuntimeModelCatalog,
        provider_config: OpenAICodexProviderConfig | None = None,
    ) -> None:
        config = provider_config or (
            self._runtime_provider_config
            if isinstance(self._runtime_provider_config, OpenAICodexProviderConfig)
            else None
        )
        if config is None:
            return
        account_id = getattr(provider, "account_id", None) or _codex_account_id(
            config,
            self._credential_store,
        )
        if not isinstance(account_id, str) or not account_id:
            return
        with suppress(OSError, TypeError, ValueError):
            save_codex_model_catalog(
                catalog,
                account_id=account_id,
                paths=self._resource_paths.paths,
            )

    def _publish_runtime_model_catalog(
        self,
        provider_name: str,
        catalog: RuntimeModelCatalog,
    ) -> None:
        if not catalog.models:
            raise ValueError("provider returned an empty model catalog")
        self._runtime_model_catalogs[provider_name] = catalog
        self._model_catalog_discovery_errors.pop(provider_name, None)
        self._invalidate_runtime_model_limits()
        self._apply_runtime_model_catalogs()

    def _apply_runtime_model_catalogs(self) -> None:
        settings = self._durable_provider_settings
        if settings is None:
            self._provider_settings = None
            return
        providers = tuple(
            _provider_with_runtime_model_catalog(
                provider,
                self._runtime_model_catalogs.get(provider.name),
            )
            for provider in settings.providers
        )
        self._provider_settings = replace(settings, providers=providers)

    def reload_provider_settings(self) -> None:
        """Reload provider settings for login and model-selection flows."""
        if self._provider_settings is None:
            return
        previous_settings = self._provider_settings
        previous_durable_settings = self._durable_provider_settings
        previous_thinking_level = self._thinking_level
        self._durable_provider_settings = load_provider_settings(self._resource_paths.paths)
        self._apply_runtime_model_catalogs()
        active_config = self._active_provider_config()
        if active_config is None or self._harness.config.model not in active_config.models:
            # The refreshed picker snapshot is authoritative for new selections,
            # but cannot invalidate an already constructed, working provider.
            return
        try:
            self._sync_thinking_level_to_active_model()
            self._refresh_runtime_provider()
            self._sync_image_support()
        except ProviderConfigError:
            self._provider_settings = previous_settings
            self._durable_provider_settings = previous_durable_settings
            self._thinking_level = previous_thinking_level
            raise

    async def resume(self, session_id: str) -> str:
        """Replace this session's active state with another indexed session."""
        self._require_idle("resume")
        await self._flush_pending_message_writes(context=self._diagnostic_context())
        manager = self._config.session_manager
        if manager is None:
            raise ValueError("Session manager is not available")
        record = manager.get_session(session_id)
        if record is None:
            raise ValueError(f"Unknown session: {session_id}")

        provider_name = self._provider_name
        runtime_provider_config = self._runtime_provider_config
        model = self.model
        restore_record_model = False
        dynamic_resume = False
        if record.provider_name:
            effective = self._provider_registry.effective(record.provider_name)
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
                if self._provider_settings is None:
                    # The destination runtime may provide a process-local
                    # definition even when the source session did not.
                    dynamic_resume = True
                    runtime_provider_config = None
                else:
                    try:
                        runtime_provider_config = self._provider_settings.get_provider(record.provider_name)
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

        replacement = await type(self).load(
            CodingSessionConfig(
                provider=None if dynamic_resume else self._harness.config.provider,
                model=model,
                cwd=record.cwd,
                storage=jsonl_session_storage(record.path),
                system=self._config.system,
                custom_system_prompt=self._config.custom_system_prompt,
                append_system_prompt=self._config.append_system_prompt,
                context_files=self._config.context_files,
                resource_paths=self._config.resource_paths,
                session_id=record.id,
                session_manager=manager,
                command_registry=self._config.command_registry,
                provider_name=provider_name,
                inference_provider=None if dynamic_resume else record.inference_provider,
                inference_provider_mode=record.inference_provider_mode,
                requested_provider=provider_name if dynamic_resume else None,
                requested_model=model if dynamic_resume else None,
                session_provider_name=record.provider_name,
                provider_settings=self._durable_provider_settings,
                runtime_provider_config=runtime_provider_config,
                auto_compact_token_threshold=self._auto_compact_token_threshold,
                auto_compact_enabled=self._auto_compact_enabled,
                thinking_level=self._thinking_level,
                shell_command_prefix=self._config.shell_command_prefix,
                skills_enabled=self._config.skills_enabled,
                allowed_tool_names=self._config.allowed_tool_names,
                extension_paths=self._config.extension_paths,
                extensions_enabled=self._config.extensions_enabled,
                project_extensions_enabled=self._config.project_extensions_enabled,
                extension_runtime=self._extension_runtime,
                project_trust_coordinator=self._config.project_trust_coordinator,
                trust_override=self._config.trust_override,
                trust_default=self._config.trust_default,
                trust_interactive=self._config.trust_interactive,
                trust_prompt=self._config.trust_prompt,
                defer_authoritative_writes=dynamic_resume,
                owns_initial_provider=dynamic_resume,
            )
        )
        try:
            if not restore_record_model:
                # Only provider-less legacy records inherit the source model.
                # The staged loader has already resolved provider-aware records
                # against the destination's (possibly freshly discovered) catalog.
                replacement._harness.config.model = self._harness.config.model
                replacement._sync_thinking_level_to_active_model()
                replacement._refresh_runtime_provider()
                replacement._sync_image_support()
        except BaseException:
            # resume owns the loaded candidate until adoption takes ownership.
            await _finish_aborted_session_close(replacement)
            raise
        await self._adopt_replacement(replacement, reason="resume")
        return f"Resumed session: {record.id}"

    async def set_session_name(self, name: str) -> str:
        """Persist a session name and notify extensions after it changes."""
        normalized = normalize_session_name(name)
        persisted = self._persist_session_name(
            normalized,
            only_if_unnamed=False,
            index_if_missing=True,
        )
        if persisted is None:
            return normalized
        await self._extension_runtime.emit_event(SessionInfoChangedEvent(name=persisted))
        return persisted

    def _persist_session_name(
        self,
        name: str,
        *,
        only_if_unnamed: bool,
        index_if_missing: bool,
    ) -> str | None:
        """Persist and return a changed name; return None for a no-op."""
        normalized = normalize_session_name(name)
        manager = self._config.session_manager
        session_id = self._config.session_id
        if manager is None or session_id is None:
            raise ValueError("Session manager is not available")
        record = manager.get_session(session_id)
        if record is None and index_if_missing:
            self.ensure_session_indexed()
            record = manager.get_session(session_id)
        if record is None:
            return None
        if only_if_unnamed and record.title:
            return None
        if record.title == normalized:
            return None
        updated = manager.touch_session(
            session_id,
            model=self.model,
            provider_name=self.provider_name,
            title=normalized,
        )
        if updated is None:
            if index_if_missing:
                raise ValueError(f"Unknown session: {session_id}")
            return None
        return updated.title or normalized

    async def new_session(self) -> str:
        """Replace this session's active state with a pending unindexed session."""
        self._require_idle("start a new session")
        await self._flush_pending_message_writes(context=self._diagnostic_context())
        manager = self._config.session_manager
        if manager is None:
            raise ValueError("Session manager is not available")

        provider_name = self._provider_name
        model = self._harness.config.model
        runtime_provider_config = self._runtime_provider_config
        thinking_level = self._thinking_level
        if self._provider_settings is not None:
            selection = resolve_provider_selection(self._provider_settings)
            provider_name = selection.provider.name
            model = selection.model
            runtime_provider_config = selection.provider
            thinking_level = _coerced_thinking_level(
                selection.provider,
                model=model,
                current=self._thinking_level,
            )

        effective = self._provider_registry.effective(provider_name)
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
                cwd=self.cwd,
                model=model,
                provider_name=provider_name,
                inference_provider=inference_provider,
                inference_provider_mode=inference_provider_mode,
            )
            if inference_provider is not None
            else manager.prepare_session(
                cwd=self.cwd,
                model=model,
                provider_name=provider_name,
            )
        )
        replacement = await type(self).load(
            replace(
                self._config,
                # The old runtime may belong to a different provider. Stage a
                # fresh runtime for the new session's default provider/model.
                provider=(self._harness.config.provider if self._provider_settings is None else None),
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
                provider_settings=self._durable_provider_settings,
                runtime_provider_config=runtime_provider_config,
                dynamic_provider=dynamic_provider,
                owns_initial_provider=False,
                defer_authoritative_writes=dynamic_provider is not None,
                thinking_level=thinking_level,
                index_on_first_persist=True,
                extension_runtime=self._extension_runtime,
            )
        )
        await self._adopt_replacement(replacement, reason="new")
        return f"Started new session: {record.id}"

    async def _adopt_replacement(
        self,
        replacement: CodingSession,
        *,
        reason: Literal["new", "resume", "branch"],
    ) -> None:
        """Adopt a replacement session's state and re-bind the extension runtime.

        The extension runtime is long-lived and shared with the replacement; it
        must be re-bound to this outer session object because later state
        (transcript persistence, parent ids) mutates here, not on the discarded
        replacement instance.
        """
        old_runtime = self._extension_runtime
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
            await _finish_aborted_session_close(replacement)
            raise

        # Every cancellable boundary has completed. Adopt synchronously so a
        # reported cancellation cannot expose only part of the destination.
        old_runtime.retire()
        self._config = replacement._config
        self._state = replacement._state
        self._harness = replacement._harness
        self._preview_model = None
        self._preview_thinking = None
        # Detach the replacement's persistence listener so writes advance
        # this session's parent pointers, not the discarded replacement's.
        if replacement._persistence_unsubscribe is not None:
            replacement._persistence_unsubscribe()
            replacement._persistence_unsubscribe = None
        self._attach_persistence_listener()
        self._invalidate_context_usage_cache()
        self._last_parent_id = replacement._last_parent_id
        self._skills = replacement._skills
        self._prompt_templates = replacement._prompt_templates
        self._context_files = replacement._context_files
        self._custom_system_prompt = replacement._custom_system_prompt
        self._custom_system_prompt_path = replacement._custom_system_prompt_path
        self._append_system_prompt = replacement._append_system_prompt
        self._append_system_prompts = replacement._append_system_prompts
        self._append_system_prompt_paths = replacement._append_system_prompt_paths
        self._resource_diagnostics = replacement._resource_diagnostics
        self._command_registry = replacement._command_registry
        self._provider_name = replacement._provider_name
        self._inference_provider = replacement._inference_provider
        self._inference_provider_mode = replacement._inference_provider_mode
        self._provider_settings = replacement._provider_settings
        self._durable_provider_settings = replacement._durable_provider_settings
        self._runtime_model_catalogs = replacement._runtime_model_catalogs
        self._model_catalog_discovery_errors = replacement._model_catalog_discovery_errors
        self._runtime_provider_config = replacement._runtime_provider_config
        self._resource_paths = replacement._resource_paths
        self._auto_compact_token_threshold = replacement._auto_compact_token_threshold
        self._auto_compact_enabled = replacement._auto_compact_enabled
        self._thinking_level = replacement._thinking_level
        self._pending_initial_entries = replacement._pending_initial_entries
        self._pending_message_writes = replacement._pending_message_writes
        self._extension_runtime = replacement._extension_runtime
        self._provider_registry = replacement._provider_registry
        self._credential_store = replacement._credential_store
        self._diagnostic_logger = replacement._diagnostic_logger
        self._runtime_model_limits = replacement._runtime_model_limits
        self._runtime_model_limits_key = replacement._runtime_model_limits_key
        self._model_limits_discovery_error = replacement._model_limits_discovery_error
        self._prepared_entries = replacement._prepared_entries
        self._owned_providers.extend(replacement._owned_providers)
        replacement._owned_providers.clear()
        self._image_support = replacement._image_support
        self._project_trust_resolution = replacement._project_trust_resolution
        self._project_trust_commit_pending = False
        self._session_start_pending = False
        self._extension_runtime.bind(self)
        self._extension_runtime.attach_harness_listener(self._harness.subscribe)
        # Adoption is already committed. Finish outgoing cleanup under a
        # shielded owner and contain cancellation rather than reporting that
        # the requested destination failed to replace the source session.
        await _finish_adopted_runtime_close(old_runtime)

    async def compact_detailed(self, instructions: str | None = None) -> ManualCompactionResult:
        """Compact older context while preserving a real recent-entry boundary."""
        await self._flush_pending_message_writes(context=self._diagnostic_context())
        plan = self._recent_preserving_compaction_plan()
        if plan is None:
            raise ValueError("Not enough context to compact while preserving recent entries")
        tokens_before = self.context_token_estimate
        generated = await self._generate_compaction_summary(
            plan.messages_to_summarize,
            custom_instructions=instructions,
        )
        await self._append_compaction(
            generated.text,
            first_kept_entry_id=plan.first_kept_entry_id,
            tokens_before=tokens_before,
            usage=generated.usage,
            provider=generated.provider,
            model=generated.model,
            response_provider=generated.response_provider,
        )
        return ManualCompactionResult(
            summary=generated.text,
            first_kept_entry_id=plan.first_kept_entry_id,
            tokens_before=tokens_before,
            estimated_tokens_after=self.context_token_estimate,
            replaced_entry_count=plan.replaced_entry_count,
        )

    async def compact(self, instructions: str | None = None) -> str:
        """Generate a manual compaction summary and rebuild active context."""
        result = await self.compact_detailed(instructions)
        return f"Compacted {result.replaced_entry_count} context entries."

    async def aclose(self) -> None:
        """Close every owned extension/provider resource exactly once.

        Caller cancellation is remembered but cannot cancel the durable close
        task. The first call propagates it only after all ownership ledgers are
        discharged; later calls observe the same completed task idempotently.
        """
        close_task = self._close_task
        if close_task is None:
            close_task = asyncio.create_task(
                self._close_owned_resources(),
                name="baldric-coding-session-close",
            )
            self._close_task = close_task

        cancelled = await _await_cleanup_completion(close_task)
        error: BaseException | None = None
        try:
            close_task.result()
        except BaseException as exc:  # all resources were attempted before this outcome
            error = exc
        if cancelled:
            raise asyncio.CancelledError
        if error is not None:
            raise error

    async def _close_owned_resources(self) -> None:
        """Run the sole close pass, continuing after individual failures."""
        error: BaseException | None = None
        try:
            if self._extension_runtime.active:
                await self._extension_runtime.emit_session_shutdown("quit")
        except BaseException as exc:
            error = exc

        # Final close has no successor sharing the UI bridge. Remove any
        # source-owned widgets/interceptors before invalidating the API.
        try:
            self._extension_runtime.clear_ui_components()
        except BaseException as exc:
            if error is None:
                error = exc

        # A runtime may already be synchronously retired by replacement. Close
        # still owns the async drain/containment step and must never skip it.
        try:
            await self._extension_runtime.aclose()
        except BaseException as exc:
            if error is None:
                error = exc

        # Remove each provider from the ownership ledger before its only close
        # attempt. One hostile provider cannot prevent later providers closing.
        providers = tuple(self._owned_providers)
        self._owned_providers.clear()
        for provider in providers:
            try:
                await provider.aclose()
            except BaseException as exc:
                if error is None:
                    error = exc

        if error is not None:
            raise error

    def handle_command(self, text: str) -> CommandResult:
        """Handle coding-session slash commands.

        Prompt-template slash commands are expansion directives, so they remain
        unhandled here and flow through `prompt()` for on-the-fly replacement.
        """
        if expand_prompt_template_command(text, self._prompt_templates) is not None:
            return CommandResult(handled=False)
        return self._command_registry.execute(self, text)

    def ensure_session_indexed(self) -> None:
        """Persist pending session metadata and add this session to the resume index."""
        if self._config.session_id is None or self._config.session_manager is None:
            return
        if self._config.session_manager.get_session(self._config.session_id) is None:
            self._config.session_manager.create_session(
                cwd=self.cwd,
                model=self.model,
                provider_name=self.provider_name,
                inference_provider=self._inference_provider,
                inference_provider_mode=self._inference_provider_mode,
                session_id=self._config.session_id,
            )
        self._config = replace(self._config, index_on_first_persist=False)
        self._ensure_session_file_initialized()

    def expand_prompt_text(self, text: str) -> str:
        """Expand prompt text using loaded markdown resources."""
        expanded_prompt = expand_prompt_template_command(text, self._prompt_templates)
        if expanded_prompt is not None:
            return expanded_prompt
        expanded_skill = expand_skill_command(text, self._skills)
        return expanded_skill if expanded_skill is not None else text

    async def run_terminal_command(
        self,
        command: str,
        *,
        add_to_context: bool,
    ) -> TerminalCommandResult:
        """Run a shell command in the session cwd, optionally adding output to context."""
        normalized_command = command.strip()
        if not normalized_command:
            raise ValueError("Terminal command cannot be empty")

        bash_tool = create_bash_tool(
            cwd=self.cwd,
            shell_command_prefix=self._config.shell_command_prefix,
        )
        result = await bash_tool.execute("terminal-command", {"command": normalized_command})
        exit_code = None
        if isinstance(result.details, dict):
            raw_exit_code = result.details.get("exit_code")
            exit_code = raw_exit_code if isinstance(raw_exit_code, int) else None

        if add_to_context:
            await self._flush_pending_message_writes(context=self._diagnostic_context())
            context_message = UserMessage(
                content=_terminal_command_context_message(
                    normalized_command,
                    result.text,
                )
            )
            self._harness.append_message(context_message)
            self._invalidate_context_usage_cache()
            await self._persist_message(context_message)

        return TerminalCommandResult(
            command=normalized_command,
            output=result.text,
            exit_code=exit_code,
            ok=exit_code == 0,
            added_to_context=add_to_context,
        )

    async def prompt(
        self,
        content: str,
        *,
        streaming_behavior: StreamingBehavior | None = None,
        source: Literal["interactive", "extension"] = "interactive",
        custom_type: str | None = None,
        details: dict[str, JSONValue] | None = None,
    ) -> AsyncIterator[CodingSessionEvent]:
        stream = _session_runtime.prompt(
            self,
            content,
            streaming_behavior=streaming_behavior,
            source=source,
            custom_type=custom_type,
            details=details,
        )
        try:
            async for item in stream:
                yield item
        finally:
            await stream.aclose()

    async def continue_(self) -> AsyncIterator[CodingSessionEvent]:
        stream = _session_runtime.continue_(self)
        try:
            async for item in stream:
                yield item
        finally:
            await stream.aclose()

    async def _dispatch_agent_settled(self) -> AgentSettledEvent:
        return await _session_runtime._dispatch_agent_settled(self)

    def _diagnostic_context(self) -> AgentCallDiagnosticContext:
        return _session_runtime._diagnostic_context(self)

    async def _persist_active_tool_history_repairs(self) -> ToolHistoryRepair | None:
        return await _session_runtime._persist_active_tool_history_repairs(self)

    def _attach_persistence_listener(self) -> None:
        return _session_runtime._attach_persistence_listener(self)

    async def _persist_on_message_end(self, event: AgentEvent) -> None:
        return await _session_runtime._persist_on_message_end(self, event)

    async def _persist_message(self, message: AgentMessage) -> None:
        return await _session_runtime._persist_message(self, message)

    async def _reconcile_run_persistence(
        self, events: AsyncIterator[AgentEvent] | None, *, context: AgentCallDiagnosticContext
    ) -> None:
        return await _session_runtime._reconcile_run_persistence(self, events, context=context)

    async def _flush_pending_message_writes(self, *, context: AgentCallDiagnosticContext) -> None:
        return await _session_runtime._flush_pending_message_writes(self, context=context)

    def _log_persistence_failure(self, *, context: AgentCallDiagnosticContext, exc: BaseException) -> None:
        return _session_runtime._log_persistence_failure(self, context=context, exc=exc)

    def _invalidate_context_usage_cache(self) -> None:
        return _session_runtime._invalidate_context_usage_cache(self)

    async def _refresh_persisted_state(self, *, leaf_id: str | None) -> None:
        return await _session_runtime._refresh_persisted_state(self, leaf_id=leaf_id)

    async def _read_session_entries(self) -> list[SessionEntry]:
        return await _session_runtime._read_session_entries(self)

    async def _commit_prepared_entries(self) -> None:
        return await _session_runtime._commit_prepared_entries(self)

    async def _append_session_entry(self, entry: SessionEntry) -> None:
        return await _session_runtime._append_session_entry(self, entry)

    async def _append_session_batch(self, entries: Sequence[SessionEntry]) -> None:
        return await _session_runtime._append_session_batch(self, entries)

    async def _close_replaced_provider(self, provider: ModelProvider) -> None:
        """Close a Baldric-owned provider once after a committed publication."""
        if provider not in self._owned_providers:
            return
        self._owned_providers.remove(provider)
        close = getattr(provider, "aclose", None)
        if close is not None:
            await close()

    async def _ensure_session_initialized(self) -> None:
        return await _session_runtime._ensure_session_initialized(self)

    async def _write_pending_initial_entries(self) -> None:
        return await _session_runtime._write_pending_initial_entries(self)

    def _ensure_session_file_initialized(self) -> None:
        return _session_runtime._ensure_session_file_initialized(self)

    def _record_session_index_diagnostic(self, exc: BaseException) -> None:
        return _session_runtime._record_session_index_diagnostic(self, exc)

    def _index_current_session(self) -> None:
        return _session_runtime._index_current_session(self)

    async def _try_auto_compact(
        self, *, context: AgentCallDiagnosticContext, phase: str
    ) -> AsyncIterator[CodingSessionEvent]:
        stream = _session_runtime._try_auto_compact(self, context=context, phase=phase)
        try:
            async for item in stream:
                yield item
        finally:
            await stream.aclose()

    async def _try_overflow_compact(self, *, context: AgentCallDiagnosticContext) -> bool:
        return await _session_runtime._try_overflow_compact(self, context=context)

    async def _try_auto_name_session(
        self, first_message: str, *, context: AgentCallDiagnosticContext
    ) -> None:
        return await _session_runtime._try_auto_name_session(self, first_message, context=context)

    def _should_auto_name_session(self) -> bool:
        return _session_runtime._should_auto_name_session(self)

    async def _generate_session_name(
        self, first_message: str, *, provider: ModelProvider, model: str
    ) -> str | None:
        return await _session_runtime._generate_session_name(
            self, first_message, provider=provider, model=model
        )

    def _provider_is_usable(self, provider: ProviderConfig) -> bool:
        return _session_runtime._provider_is_usable(self, provider)

    def _usable_provider_configs(self) -> tuple[ProviderConfig, ...]:
        return _session_runtime._usable_provider_configs(self)

    def _auto_compaction_plan(self) -> CompactionPlan | None:
        return _session_runtime._auto_compaction_plan(self)

    async def _run_compaction_plan(self, plan: CompactionPlan) -> None:
        return await _session_runtime._run_compaction_plan(self, plan)

    async def _generate_compaction_summary(
        self, messages: tuple[AgentMessage, ...], *, custom_instructions: str | None = None
    ) -> _GeneratedSummary:
        return await _session_runtime._generate_compaction_summary(
            self, messages, custom_instructions=custom_instructions
        )

    async def _summarize_branch_messages(
        self,
        messages: tuple[AgentMessage, ...],
        *,
        custom_instructions: str | None = None,
        replace_instructions: bool = False,
    ) -> _GeneratedSummary:
        return await _session_runtime._summarize_branch_messages(
            self, messages, custom_instructions=custom_instructions, replace_instructions=replace_instructions
        )

    def _recent_preserving_compaction_plan(self) -> CompactionPlan | None:
        return _session_runtime._recent_preserving_compaction_plan(self)

    def _active_context_rows(self) -> tuple[tuple[str, AgentMessage], ...]:
        return _session_runtime._active_context_rows(self)

    async def _append_compaction(
        self,
        summary: str,
        *,
        first_kept_entry_id: str,
        tokens_before: int | None = None,
        usage: Usage | None = None,
        provider: str | None = None,
        model: str | None = None,
        response_provider: str | None = None,
    ) -> CompactionEntry:
        return await _session_runtime._append_compaction(
            self,
            summary,
            first_kept_entry_id=first_kept_entry_id,
            tokens_before=tokens_before,
            usage=usage,
            provider=provider,
            model=model,
            response_provider=response_provider,
        )
