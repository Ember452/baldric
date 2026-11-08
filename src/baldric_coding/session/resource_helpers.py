"""Persistent coding-session wrapper built on AgentHarness."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from os import environ
from pathlib import Path

from baldric_agent.tool_history import ToolHistoryRepair, repair_tool_history
from baldric_ai.model_catalog import RuntimeModel, RuntimeModelCatalog
from baldric_coding.auth.credentials import FileCredentialStore
from baldric_coding.auth.oauth import account_id_from_access_token
from baldric_coding.config.paths import BaldricPaths
from baldric_coding.context.project import discover_project_context_with_diagnostics
from baldric_coding.context.prompts import (
    PromptTemplate,
    load_prompt_templates_with_diagnostics,
)
from baldric_coding.context.resources import (
    BaldricResourcePaths,
    ResourceDiagnostic,
    discover_system_prompt_resources,
)
from baldric_coding.context.skills.skills import Skill, load_skills_with_diagnostics
from baldric_coding.context.system_prompt import (
    ProjectContextFile,
    PromptSection,
)
from baldric_coding.context.thinking import (
    THINKING_LEVELS,
    ThinkingLevel,
)
from baldric_coding.extensions.runtime import ExtensionRuntime
from baldric_coding.providers.config import (
    OpenAICodexProviderConfig,
    ProviderConfig,
    ProviderConfigError,
    ProviderModelMetadata,
    ProviderSettings,
)
from baldric_coding.session import JsonlSessionStorage, SessionStorage
from baldric_coding.update.reload import ReloadCategorySummary
from baldric_protocol.messages import (
    AgentMessage,
)
from baldric_protocol.session.entries import SessionEntry
from baldric_protocol.session.jsonl import entry_to_json_line


@dataclass(frozen=True, slots=True)
class TerminalCommandRequest:
    """Parsed input-bar terminal command request."""

    command: str
    add_to_context: bool


@dataclass(frozen=True, slots=True)
class SessionResources:
    """Baldric-owned resources loaded around a coding session."""

    skills: tuple[Skill, ...]
    prompt_templates: tuple[PromptTemplate, ...]
    context_files: tuple[ProjectContextFile, ...]
    custom_system_prompt: str | None
    custom_system_prompt_path: Path | None
    append_system_prompt: str | None
    append_system_prompts: tuple[str, ...]
    append_system_prompt_paths: tuple[Path, ...]
    diagnostics: tuple[ResourceDiagnostic, ...]


def parse_terminal_command(text: str) -> TerminalCommandRequest | None:
    """Parse input-bar terminal command syntax."""
    stripped = text.strip()
    if stripped.startswith("!!"):
        command = stripped[2:].strip()
        if not command:
            return None
        return TerminalCommandRequest(command=command, add_to_context=False)
    if stripped.startswith("!"):
        command = stripped[1:].strip()
        if not command:
            return None
        return TerminalCommandRequest(command=command, add_to_context=True)
    return None


def _category_summary(
    before: tuple[tuple[object, ...], ...],
    after: tuple[tuple[object, ...], ...],
) -> ReloadCategorySummary:
    return ReloadCategorySummary(
        before=len(before),
        after=len(after),
        changed=before != after,
    )


def _skill_signatures(skills: tuple[Skill, ...]) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            skill.name,
            str(skill.path),
            skill.description,
            skill.content,
            skill.disable_model_invocation,
        )
        for skill in skills
    )


def _prompt_template_signatures(
    prompt_templates: tuple[PromptTemplate, ...],
) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (template.name, str(template.path), template.description, template.content)
        for template in prompt_templates
    )


def _context_file_signatures(
    context_files: tuple[ProjectContextFile, ...],
) -> tuple[tuple[object, ...], ...]:
    return tuple((context_file.path, context_file.content) for context_file in context_files)


def _diagnostic_signatures(
    diagnostics: tuple[ResourceDiagnostic, ...],
) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            diagnostic.kind,
            diagnostic.message,
            str(diagnostic.path) if diagnostic.path is not None else None,
            diagnostic.name,
            diagnostic.severity,
        )
        for diagnostic in diagnostics
    )


def _extension_signatures(runtime: ExtensionRuntime) -> tuple[tuple[object, ...], ...]:
    return tuple((name,) for name in runtime.extension_names)


def _system_prompt_resource_signatures(
    *,
    skills: tuple[Skill, ...],
    context_files: tuple[ProjectContextFile, ...],
    custom_system_prompt: str | None,
    custom_system_prompt_path: Path | None,
    append_system_prompt: str | None,
    append_system_prompt_paths: tuple[Path, ...],
) -> tuple[object, ...]:
    prompt_skills = tuple(
        (skill.name, str(skill.path), skill.description, skill.disable_model_invocation)
        for skill in sorted(skills, key=lambda item: item.name)
    )
    return (
        prompt_skills,
        _context_file_signatures(context_files),
        custom_system_prompt,
        str(custom_system_prompt_path) if custom_system_prompt_path is not None else None,
        append_system_prompt,
        tuple(str(path) for path in append_system_prompt_paths),
    )


def _provider_config_or_none(
    settings: ProviderSettings | None,
    provider_name: str | None,
) -> ProviderConfig | None:
    if settings is None or provider_name is None:
        return None
    try:
        return settings.get_provider(provider_name)
    except ProviderConfigError:
        return None


def _codex_account_id(
    provider: OpenAICodexProviderConfig,
    credential_store: FileCredentialStore,
) -> str | None:
    if provider.credential_name:
        credential = credential_store.get_oauth(provider.credential_name)
        if credential is not None and credential.account_id:
            return credential.account_id
    return account_id_from_access_token(environ.get(provider.api_key_env, ""))


def _provider_settings_with_runtime_catalogs(
    settings: ProviderSettings | None,
    catalogs: Mapping[str, RuntimeModelCatalog],
) -> ProviderSettings | None:
    if settings is None or not catalogs:
        return settings
    providers = tuple(
        _provider_with_runtime_model_catalog(provider, catalogs.get(provider.name))
        for provider in settings.providers
    )
    return replace(settings, providers=providers)


def _provider_with_runtime_model_catalog(
    provider: ProviderConfig,
    catalog: RuntimeModelCatalog | None,
) -> ProviderConfig:
    """Overlay one account-specific catalog without changing durable settings."""
    if catalog is None or not isinstance(provider, OpenAICodexProviderConfig):
        return provider

    models = tuple(model.id for model in catalog.models)
    metadata = {model.id: _runtime_provider_model_metadata(provider, model) for model in catalog.models}
    context_windows = {
        model.id: (
            model.limits.context_window if model.limits is not None else provider.context_windows[model.id]
        )
        for model in catalog.models
        if model.limits is not None or model.id in provider.context_windows
    }
    return replace(
        provider,
        models=models,
        default_model=(provider.default_model if provider.default_model in models else models[0]),
        context_windows=context_windows,
        model_metadata=metadata,
        thinking_models=tuple(model.id for model in catalog.models if model.thinking_levels),
        thinking_defaults=_runtime_model_thinking_defaults(provider, catalog),
    )


def _runtime_model_thinking_defaults(
    provider: OpenAICodexProviderConfig,
    catalog: RuntimeModelCatalog,
) -> dict[str, ThinkingLevel]:
    defaults: dict[str, ThinkingLevel] = {}
    for model in catalog.models:
        default = provider.thinking_defaults.get(model.id) or model.default_thinking_level
        if default is not None:
            defaults[model.id] = default
    return defaults


def _runtime_provider_model_metadata(
    provider: OpenAICodexProviderConfig,
    model: RuntimeModel,
) -> ProviderModelMetadata:
    existing = provider.model_metadata.get(model.id, ProviderModelMetadata())
    supported = set(model.thinking_levels)
    thinking_level_map = {
        level: ("none" if level == "off" else level) if level in supported else None
        for level in THINKING_LEVELS
    }
    return replace(
        existing,
        name=model.name or existing.name,
        reasoning=True if model.thinking_levels else existing.reasoning,
        input=model.input_modalities,
        context_window=(model.limits.context_window if model.limits is not None else existing.context_window),
        max_tokens=(
            model.limits.max_output_tokens
            if model.limits is not None and model.limits.max_output_tokens is not None
            else existing.max_tokens
        ),
        thinking_level_map=thinking_level_map,
    )


def _load_session_resources(
    resource_paths: BaldricResourcePaths,
    explicit_context_files: tuple[ProjectContextFile, ...],
    *,
    skills_enabled: bool = True,
    system_prompt_enabled: bool = True,
    custom_system_prompt_explicit: bool = False,
) -> SessionResources:
    loaded_skills: list[Skill]
    skill_diagnostics: list[ResourceDiagnostic]
    if skills_enabled:
        loaded_skills, skill_diagnostics = load_skills_with_diagnostics(resource_paths)
    else:
        loaded_skills, skill_diagnostics = [], []
    loaded_prompt_templates, prompt_diagnostics = load_prompt_templates_with_diagnostics(resource_paths)
    discovered_context, context_diagnostics = discover_project_context_with_diagnostics(resource_paths)
    system_prompts = discover_system_prompt_resources(
        resource_paths,
        custom_prompt_explicit=custom_system_prompt_explicit,
        enabled=system_prompt_enabled,
    )
    return SessionResources(
        skills=tuple(loaded_skills),
        prompt_templates=tuple(loaded_prompt_templates),
        context_files=_merge_context_files(explicit_context_files, discovered_context),
        custom_system_prompt=system_prompts.custom_prompt,
        custom_system_prompt_path=system_prompts.custom_prompt_path,
        append_system_prompt=system_prompts.append_prompt,
        append_system_prompts=system_prompts.append_prompts,
        append_system_prompt_paths=system_prompts.append_prompt_paths,
        diagnostics=tuple(
            [
                *skill_diagnostics,
                *prompt_diagnostics,
                *context_diagnostics,
                *system_prompts.diagnostics,
            ]
        ),
    )


def _append_prompt_sections(
    prompts: tuple[str, ...],
    paths: tuple[Path, ...],
    explicit_prompt: str | None,
) -> tuple[PromptSection, ...]:
    """Pair append content with its file or CLI origin in composition order."""
    sections = [
        PromptSection(title=None, body=prompt, source=str(path))
        for prompt, path in zip(prompts, paths, strict=True)
    ]
    if explicit_prompt is not None:
        sections.append(
            PromptSection(
                title=None,
                body=explicit_prompt,
                source="CLI --append-system-prompt",
            )
        )
    return tuple(sections)


def _custom_prompt_source(*, explicit: bool, path: Path | None) -> str:
    if explicit:
        return "CLI --system-prompt"
    return str(path) if path is not None else "runtime configuration"


def _merge_context_files(
    explicit: tuple[ProjectContextFile, ...],
    discovered: tuple[ProjectContextFile, ...],
) -> tuple[ProjectContextFile, ...]:
    merged: list[ProjectContextFile] = []
    seen: set[str] = set()
    for context_file in (*explicit, *discovered):
        if context_file.path in seen:
            continue
        seen.add(context_file.path)
        merged.append(context_file)
    return tuple(merged)


def _tool_history_repair_plan(
    messages: tuple[AgentMessage, ...],
    *,
    context_entry_ids: tuple[str, ...],
    entries: tuple[SessionEntry, ...],
) -> tuple[str | None, tuple[AgentMessage, ...], ToolHistoryRepair] | None:
    repair = repair_tool_history(messages)
    if not repair.changed:
        return None

    common_prefix_length = 0
    for old_message, repaired_message in zip(messages, repair.messages, strict=False):
        if old_message != repaired_message:
            break
        common_prefix_length += 1

    if common_prefix_length > 0:
        parent_id: str | None = context_entry_ids[common_prefix_length - 1]
    elif context_entry_ids:
        entries_by_id = {entry.id: entry for entry in entries}
        first_entry = entries_by_id.get(context_entry_ids[0])
        parent_id = first_entry.parent_id if first_entry is not None else None
    else:
        parent_id = None

    return parent_id, repair.messages[common_prefix_length:], repair


def default_session_path(cwd: Path) -> Path:
    """Return Baldric's default user-home session path for a project cwd."""
    return BaldricPaths().default_session_path(cwd)


def jsonl_session_storage(path: str | Path) -> JsonlSessionStorage:
    """Convenience factory for local JSONL coding-session storage."""
    return JsonlSessionStorage(path)


def _append_session_entry_sync(storage: SessionStorage, entry: SessionEntry) -> None:
    """Append an entry synchronously for slash commands that cannot await storage."""
    if isinstance(storage, JsonlSessionStorage):
        storage.path.parent.mkdir(parents=True, exist_ok=True)
        with storage.path.open("a", encoding="utf-8") as file:
            file.write(entry_to_json_line(entry))
        return
    raise RuntimeError("Session storage does not support synchronous initialization")
