"""Persistent coding-session wrapper built on AgentHarness."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from baldric.agent.events import AgentEvent
from baldric.agent.harness import AgentHarness, AgentHarnessConfig, QueuedMessages
from baldric.agent.tool_calls import BeforeToolCall
from baldric.agent.tool_history import ToolHistoryRepair
from baldric.ai.hooks import HookableProvider
from baldric.ai.model_catalog import RuntimeModelCatalog
from baldric.ai.model_limits import RuntimeModelLimits
from baldric.runtime.app import build_runtime, prepare_runtime_for_load
from baldric.runtime.commands.registry import CommandRegistry, CommandResult, create_default_command_registry
from baldric.runtime.config.paths import BaldricPaths
from baldric.runtime.context.prompts import (
    PromptTemplate,
)
from baldric.runtime.context.resources import (
    BaldricResourcePaths,
    ResourceDiagnostic,
    resource_paths_with_cwd,
    resource_paths_with_project_trust,
)
from baldric.runtime.context.skills.skills import Skill
from baldric.runtime.context.system_prompt import (
    BuildSystemPromptOptions,
    ProjectContextFile,
    SystemPromptInspection,
    SystemPromptSource,
    build_system_prompt,
    build_system_prompt_inspection,
)
from baldric.runtime.context.thinking import (
    DEFAULT_THINKING_LEVEL,
    THINKING_LEVELS,
    ThinkingLevel,
)
from baldric.runtime.events import (
    AgentSettledEvent,
    CodingSessionEvent,
    ModelSelectEvent,
    QueueUpdateEvent,
)
from baldric.runtime.observability.diagnostics import (
    AgentCallDiagnosticContext,
    AgentCallDiagnosticLogger,
)
from baldric.runtime.providers.auth.credentials import FileCredentialStore, credentials_path
from baldric.runtime.providers.contracts import DynamicProvider, ProviderModel

if TYPE_CHECKING:
    from baldric.runtime.platform.runtime import ExtensionRuntime

from baldric.protocol.messages import (
    AgentMessage,
    AssistantMessage,
    CustomMessage,
    Usage,
    UserMessage,
    message_text,
)
from baldric.protocol.provider import ModelProvider
from baldric.protocol.session import (
    CompactionEntry,
    CustomEntry,
    LabelEntry,
    ModelChangeEntry,
    SessionInfoEntry,
    ThinkingLevelChangeEntry,
)
from baldric.protocol.session.entries import SessionEntry
from baldric.protocol.tools import AgentTool
from baldric.protocol.types import JSONValue
from baldric.runtime.providers.config import (
    OpenAICodexProviderConfig,
    ProviderConfig,
    ProviderConfigError,
    ProviderSettings,
    provider_thinking_levels,
    provider_thinking_unavailable_reason,
)
from baldric.runtime.providers.config import (
    load_provider_settings as load_provider_settings,
)
from baldric.runtime.providers.runtime import (
    ClosableModelProvider,
)
from baldric.runtime.providers.runtime import (
    create_model_provider as create_model_provider,
)
from baldric.runtime.providers.stores.codex_model_store import (
    cached_codex_model_catalog,
)
from baldric.runtime.providers.stores.models_dev_store import (
    ModelsDevRefreshResult,
)
from baldric.runtime.session import SessionState, SessionStorage
from baldric.runtime.session import branching as _branching
from baldric.runtime.session import lifecycle as _lifecycle
from baldric.runtime.session import model_runtime as _model_runtime
from baldric.runtime.session import model_selection as _model_selection
from baldric.runtime.session import runtime as _session_runtime
from baldric.runtime.session.branching import (
    TREE_RUNNING_MESSAGE as TREE_RUNNING_MESSAGE,
)
from baldric.runtime.session.branching import (
    SessionTreeBranchResult as SessionTreeBranchResult,
)
from baldric.runtime.session.branching import (
    SessionTreeChoice as SessionTreeChoice,
)
from baldric.runtime.session.compaction.context_window import (
    DEFAULT_COMPACTION_KEEP_RECENT_TOKENS as DEFAULT_COMPACTION_KEEP_RECENT_TOKENS,
)
from baldric.runtime.session.compaction.context_window import (
    DEFAULT_CONTEXT_WINDOW_TOKENS,
    ContextUsageEstimate,
    auto_compaction_threshold_for_context_window,
    estimate_context_usage,
)
from baldric.runtime.session.export import (
    export_session_artifact,
    normalize_export_format,
)
from baldric.runtime.session.manager import (
    InferenceProviderMode,
    SessionManager,
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
    _terminal_command_context_message as _terminal_command_context_message,
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
from baldric.runtime.session.runtime import CompactionPlan, _GeneratedSummary, _PendingMessageWrite
from baldric.runtime.session.stats import SessionStats, calculate_session_stats
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
from baldric.runtime.tools.registry import ImageSupportState, create_coding_tools
from baldric.runtime.trust.policy import (
    CanonicalProjectPath,
    ProjectTrustCoordinator,
    ProjectTrustResolution,
    ProjectTrustStore,
    TrustDefault,
    TrustOverride,
    TrustPrompt,
    format_trust_diagnostic,
)
from baldric.runtime.update.reload import CodingReloadSummary

StreamingBehavior = Literal["steer", "follow_up"]
SESSION_NAME_SYSTEM_PROMPT = (
    "You write concise coding-agent session names. Reply with only a short title, "
    "maximum four words, no quotes, no punctuation-only output."
)


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
    shell: str = "auto"
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
    disabled_built_in_extensions: frozenset[str] = frozenset()
    """Built-in extension names this session must not load.

    A host composes capabilities per session: a subagent child passes
    ``frozenset({"mcp"})`` so the bundled MCP client never boots inside it.
    Unknown names are ignored; filesystem extensions are unaffected (they are
    gated by ``extensions_enabled``).
    """
    extension_runtime: ExtensionRuntime | None = None
    before_tool_call: BeforeToolCall | None = None
    """Harness gate run before every tool execution.

    Returns ``(blocked, reason)``; a blocked call never executes and the model
    sees *reason* as the tool error. This is the seam the opt-in approval mode
    uses to pause mutating tool calls for an in-terminal decision.
    """
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
        system_builder: Callable[[], str] | None = None,
    ) -> None:
        self._config = config
        self._state = state
        self._harness = harness
        self._extension_runtime = extension_runtime or build_runtime()
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
        self._system_prompt_builder = system_builder
        self._persistence_unsubscribe: Callable[[], None] | None = None
        # Per-message index writes are throttled by their caller; the record's
        # own ordering contract still writes on every explicit touch.
        self._last_record_touch_key: tuple[object, ...] | None = None
        self._last_record_touch_at: float = 0.0
        self._persisted_message_ids: set[int] = set()
        self._ended_message_ids: set[int] = set()
        self._pending_message_writes: dict[int, _PendingMessageWrite] = {}
        # Session-level events (title, thinking level) are published to
        # extensions immediately but have no stream of their own; queue them so
        # the next prompt's event stream can hand them to a frontend.
        self._pending_frontend_events: deque[CodingSessionEvent] = deque()
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

        # A runtime is cwd-bound because it may contain project registrations.
        # Always stage a fresh eligible-only runtime for a destination snapshot;
        # never reuse source-project code across replacement trust boundaries.
        # The construction lives in the composition root (runtime.app) so this
        # core module no longer statically imports the platform runtime.
        previous_runtime = config.extension_runtime
        runtime_prep = prepare_runtime_for_load(config, previous_runtime)
        extension_runtime = runtime_prep.extension_runtime
        unfiltered_resource_paths = runtime_prep.unfiltered_resource_paths
        runtime_paths = runtime_prep.runtime_paths
        credential_store = runtime_prep.credential_store

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
                shell=config.shell,
                image_support=image_support,
            )
        )
        tools = _filter_tools(extension_runtime.compose_tools(base_tools), config.allowed_tool_names)
        extension_runtime.bind_live_tools(tools, config.allowed_tool_names)

        def _build_system_prompt() -> str:
            return build_system_prompt(
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

        system = config.system if config.system is not None else _build_system_prompt()
        initial_provider = config.provider
        if initial_provider is not None and extension_runtime.has_provider_hooks():
            initial_provider = HookableProvider(initial_provider, extension_runtime.build_provider_hooks())
        harness = AgentHarness(
            AgentHarnessConfig(
                provider=initial_provider,
                model=active_model,
                system=system,
                tools=tools,
                session_id=config.session_id,
                before_tool_call=config.before_tool_call,
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
            system_builder=None if config.system is not None else _build_system_prompt,
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
            # A frontend that bootstraps its own provider cannot pass the routing
            # observer: the observer is a method of the session, which does not
            # exist yet. Rebuild through the path the print and RPC frontends use,
            # or Hugging Face sticky routing and failover silently never engage.
            # Only Hugging Face reads the observer, so every other provider keeps
            # the provider its frontend built.
            owns_provider_without_observer = (
                config.owns_initial_provider
                and config.provider is not None
                and session.provider_name == "huggingface"
            )
            if config.provider is not None and (
                not config.owns_initial_provider or owns_provider_without_observer
            ):
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
    def shell(self) -> str:
        """Return the shell preference used to build this session's bash tool."""
        return self._config.shell

    @property
    def shell_command_prefix(self) -> str | None:
        """Return the shell command prefix applied to this session's bash tool."""
        return self._config.shell_command_prefix

    @property
    def before_tool_call(self) -> BeforeToolCall | None:
        """Return the harness tool gate, so child sessions can inherit it."""
        return self._config.before_tool_call

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
        return await _branching.session_entries(self)

    async def tree_choices(self) -> tuple[SessionTreeChoice, ...]:
        """Return branchable session entries for a tree picker."""
        return await _branching.tree_choices(self)

    async def set_label(self, target_id: str, label: str | None) -> LabelEntry:
        """Set or clear the bookmark on an existing session entry."""
        return await _branching.set_label(self, target_id, label)

    async def branch_to_entry(
        self,
        entry_id: str,
        *,
        summarize: bool = False,
        custom_instructions: str | None = None,
        replace_instructions: bool = False,
    ) -> SessionTreeBranchResult:
        """Move the active leaf to a previous entry, preserving existing history."""
        return await _branching.branch_to_entry(
            self,
            entry_id,
            summarize=summarize,
            custom_instructions=custom_instructions,
            replace_instructions=replace_instructions,
        )

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

    def refresh_system_prompt(self) -> None:
        """Rebuild the system prompt from current registries (extension seam).

        Only sessions whose prompt was built here can refresh: an explicit
        ``config.system`` leaves nothing to rebuild.
        """
        if self._system_prompt_builder is None:
            return
        self._harness.update_system_prompt(self._system_prompt_builder())

    def _adopt_system_prompt_builder(self, replacement: CodingSession) -> None:
        """Take over the replacement's prompt closure during adoption.

        The replacement built its own closure during its load; the surviving
        session must refresh through it, not through the pre-adoption one.
        """
        self._system_prompt_builder = replacement._system_prompt_builder

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
        return _model_runtime.pricing_for_response(self, provider_name, model, input_tokens)

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

    def queue_frontend_event(self, event: CodingSessionEvent) -> None:
        """Queue one session-level event for the next frontend stream."""
        self._pending_frontend_events.append(event)

    def drain_frontend_events(self) -> tuple[CodingSessionEvent, ...]:
        """Return and clear the session-level events queued for a frontend."""
        drained = tuple(self._pending_frontend_events)
        self._pending_frontend_events.clear()
        return drained

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

    def set_thinking_state(self, level: ThinkingLevel) -> None:
        """Set the active thinking level.

        Internal state writer: the command path goes through
        :meth:`set_thinking_level`, which also persists the choice.
        """
        self._thinking_level = level

    def should_touch_record(self, key: tuple[object, ...], *, interval: float) -> bool:
        """Return whether a record touch should write, and remember the attempt.

        The per-message caller touches the session index; a write is a temp file
        plus fsync plus replace, so an unchanged key inside ``interval`` skips it.
        """
        from time import monotonic

        now = monotonic()
        if key == self._last_record_touch_key and now - self._last_record_touch_at < interval:
            return False
        self._last_record_touch_key = key
        self._last_record_touch_at = now
        return True

    def set_active_leaf_id(self, entry_id: str | None) -> None:
        """Point the session at the entry the next append attaches to."""
        self._last_parent_id = entry_id

    def set_preview_model(self, choice: ModelChoice | None) -> None:
        """Set or clear the model a preview (picker) currently shows."""
        self._preview_model = choice

    def set_preview_thinking(self, level: ThinkingLevel | None) -> None:
        """Set or clear the thinking level a preview currently shows."""
        self._preview_thinking = level

    def set_model(self, model: str) -> None:
        return _model_selection.set_model(self, model)

    async def notify_model_selected(self, previous_model: str | None) -> None:
        """Queue and dispatch the ``model_select`` notification.

        Ports Pi's model_select: fired on an explicit selection for every
        frontend and extension. Session restores replay entries instead, so they
        never call this.
        """
        event = ModelSelectEvent(model=self.model, previous_model=previous_model)
        self.queue_frontend_event(event)
        await self._extension_runtime.emit_event(event)

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
        _model_runtime.observe_response_headers(self, headers)

    def will_auto_retry(self, message: AssistantMessage) -> bool:
        """Return whether session orchestration will retry this assistant error."""
        return _model_runtime.will_auto_retry(self, message)

    def _should_auto_failover_huggingface_route(
        self,
        message: AssistantMessage,
    ) -> bool:
        return _model_runtime.should_auto_failover_huggingface_route(self, message)

    def _reset_automatic_inference_provider_for_failover(self) -> str:
        return _model_runtime.reset_automatic_inference_provider_for_failover(self)

    async def _run_huggingface_route_failover(
        self,
        *,
        context: AgentCallDiagnosticContext,
    ) -> AsyncIterator[CodingSessionEvent]:
        """Retry the interrupted run once through unsuffixed Hugging Face routing."""
        async for event in _model_runtime.run_huggingface_route_failover(self, context=context):
            yield event

    def _build_runtime_provider(
        self,
        *,
        inference_provider: str | None,
    ) -> tuple[ClosableModelProvider, ProviderConfig]:
        return _model_runtime.build_runtime_provider(self, inference_provider=inference_provider)

    def _activate_runtime_provider(
        self,
        provider: ClosableModelProvider,
        provider_config: ProviderConfig,
    ) -> None:
        return _model_runtime.activate_runtime_provider(self, provider, provider_config)

    def _refresh_runtime_provider(self) -> None:
        return _model_runtime.refresh_runtime_provider(self)

    def _invalidate_runtime_model_limits(self) -> None:
        return _model_runtime.invalidate_runtime_model_limits(self)

    def _apply_provider_hooks(self, provider: ClosableModelProvider) -> ClosableModelProvider:
        """Wrap a provider with extension provider seams, or return it unchanged.

        Every place the session assigns ``_harness.config.provider`` funnels
        through here so an extension's provider-level hooks (context / headers /
        payload / response / stream) are applied uniformly, independent of which
        code path set the provider. Returns the provider untouched when no
        extension registered a provider seam (zero overhead).
        """
        if not self._extension_runtime.has_provider_hooks():
            return provider
        return HookableProvider(provider, self._extension_runtime.build_provider_hooks())

    async def _refresh_runtime_model_limits(self) -> None:
        await _model_runtime.refresh_runtime_model_limits(self)

    async def reload(self) -> CodingReloadSummary:
        return await _lifecycle.reload(self)

    async def refresh_model_catalogs(self, *, force: bool = False) -> ModelsDevRefreshResult:
        return await _lifecycle.refresh_model_catalogs(self, force=force)

    async def _refresh_codex_model_catalog(self) -> None:
        return await _lifecycle._refresh_codex_model_catalog(self)

    def _persist_codex_model_catalog(
        self,
        provider: object,
        catalog: RuntimeModelCatalog,
        provider_config: OpenAICodexProviderConfig | None = None,
    ) -> None:
        return _lifecycle._persist_codex_model_catalog(self, provider, catalog, provider_config)

    def _publish_runtime_model_catalog(self, provider_name: str, catalog: RuntimeModelCatalog) -> None:
        return _lifecycle._publish_runtime_model_catalog(self, provider_name, catalog)

    def _apply_runtime_model_catalogs(self) -> None:
        return _lifecycle._apply_runtime_model_catalogs(self)

    def reload_provider_settings(self) -> None:
        return _lifecycle.reload_provider_settings(self)

    async def resume(self, session_id: str) -> str:
        return await _lifecycle.resume(self, session_id)

    async def set_session_name(self, name: str) -> str:
        return await _lifecycle.set_session_name(self, name)

    def _persist_session_name(
        self, name: str, *, only_if_unnamed: bool, index_if_missing: bool
    ) -> str | None:
        return _lifecycle._persist_session_name(
            self, name, only_if_unnamed=only_if_unnamed, index_if_missing=index_if_missing
        )

    async def new_session(self) -> str:
        return await _lifecycle.new_session(self)

    async def _adopt_replacement(
        self, replacement: CodingSession, *, reason: Literal["new", "resume", "branch"]
    ) -> None:
        return await _lifecycle._adopt_replacement(self, replacement, reason=reason)

    async def compact_detailed(self, instructions: str | None = None) -> ManualCompactionResult:
        return await _lifecycle.compact_detailed(self, instructions)

    async def compact(self, instructions: str | None = None) -> str:
        return await _lifecycle.compact(self, instructions)

    async def aclose(self) -> None:
        return await _lifecycle.aclose(self)

    async def _close_owned_resources(self) -> None:
        return await _lifecycle._close_owned_resources(self)

    def handle_command(self, text: str) -> CommandResult:
        return _lifecycle.handle_command(self, text)

    def ensure_session_indexed(self) -> None:
        return _lifecycle.ensure_session_indexed(self)

    def expand_prompt_text(self, text: str) -> str:
        return _lifecycle.expand_prompt_text(self, text)

    async def run_terminal_command(self, command: str, *, add_to_context: bool) -> TerminalCommandResult:
        return await _lifecycle.run_terminal_command(self, command, add_to_context=add_to_context)

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
        return await _model_runtime.close_replaced_provider(self, provider)

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

    async def _run_compaction_plan(self, plan: CompactionPlan, *, reason: str = "manual") -> None:
        return await _session_runtime._run_compaction_plan(self, plan, reason=reason)

    async def _generate_compaction_summary(
        self,
        messages: tuple[AgentMessage, ...],
        *,
        custom_instructions: str | None = None,
        reason: str = "manual",
    ) -> _GeneratedSummary:
        return await _session_runtime._generate_compaction_summary(
            self, messages, custom_instructions=custom_instructions, reason=reason
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
