"""Durable provider configuration for Baldric coding sessions."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import replace
from json import dumps, loads
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from baldric_coding.config.paths import BaldricPaths
from baldric_coding.context.thinking import (
    ThinkingLevel,
    normalize_thinking_level,
)
from baldric_coding.providers.catalog import (
    BUILTIN_PROVIDER_CATALOG,
    ProviderCatalogEntry,
)
from baldric_coding.providers.config.catalog import (
    _append_catalog_providers,
    _catalog_entry_from_provider,
    _effective_provider_configs,
    _merge_provider_config,
    _save_provider_definitions_to_catalog,
)
from baldric_coding.providers.config.models import (
    DEFAULT_PROVIDER_NAME,
    OpenAICompatibleProviderConfig,
    ProviderConfig,
    ProviderConfigError,
    ProviderSettings,
    ScopedModelConfig,
    _provider_preference_to_json,
)
from baldric_coding.providers.config.selection import (
    provider_thinking_levels,
    validate_provider_model,
)
from baldric_coding.providers.config.validation import (
    _apply_provider_preference,
    provider_settings_from_json,
)
from baldric_coding.providers.loader import effective_catalog


def _provider_config_module() -> Any:
    import baldric_coding.providers.config as provider_config

    return provider_config


def provider_settings_path(paths: BaldricPaths | None = None) -> Path:
    """Return the durable provider settings path."""
    return (paths or BaldricPaths()).home / "providers.json"


def load_provider_settings(paths: BaldricPaths | None = None) -> ProviderSettings:
    """Load durable provider settings, falling back to env-compatible defaults."""
    resolved_paths = paths or BaldricPaths()
    path = provider_settings_path(resolved_paths)
    if not path.exists():
        return ProviderSettings(providers=_effective_provider_configs(resolved_paths))
    raw = loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ProviderConfigError("Provider settings must be a JSON object")
    settings = provider_settings_from_json(raw, paths=resolved_paths)
    if "provider_preferences" not in raw:
        settings = _migrate_legacy_provider_settings(settings, paths=resolved_paths)
        _save_migrated_provider_settings(settings, paths=resolved_paths)
        return settings
    return _with_builtin_catalog_models(settings, paths=resolved_paths)


def save_provider_settings(settings: ProviderSettings, paths: BaldricPaths | None = None) -> Path:
    """Write durable provider preferences and return the path."""
    resolved_paths = paths or BaldricPaths()
    _save_provider_definitions_to_catalog(settings, paths=resolved_paths)
    path = provider_settings_path(resolved_paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    _provider_config_module()._write_provider_settings(settings, path=path, backup=True)
    return path


def save_default_provider_model(
    *,
    provider_name: str,
    model: str,
    paths: BaldricPaths | None = None,
    fallback_settings: ProviderSettings | None = None,
) -> ProviderSettings:
    """Reload settings, persist one default provider/model change, and return them."""
    settings = _load_provider_settings_for_write(paths, fallback_settings=fallback_settings)
    updated = set_default_provider_model(settings, provider_name=provider_name, model=model)
    save_provider_settings(updated, paths)
    return updated


def save_provider_thinking_level(
    *,
    provider_name: str,
    model: str,
    thinking_level: ThinkingLevel,
    paths: BaldricPaths | None = None,
    fallback_settings: ProviderSettings | None = None,
) -> ProviderSettings:
    """Reload settings, persist one provider/model thinking preference, and return them."""
    settings = _load_provider_settings_for_write(paths, fallback_settings=fallback_settings)
    updated = set_provider_thinking_level(
        settings,
        provider_name=provider_name,
        model=model,
        thinking_level=thinking_level,
    )
    save_provider_settings(updated, paths)
    return updated


def toggle_saved_stable_scoped_model(
    *,
    provider_name: str,
    model: str,
    paths: BaldricPaths | None = None,
    fallback_settings: ProviderSettings | None = None,
) -> ProviderSettings:
    """Toggle an already-authorized stable reference without saving a definition.

    Callers must restrict this path to trusted built-in dynamic providers.  The
    durable value is only the exact provider/model pair; availability continues
    to come from the process-local provider snapshot.
    """
    settings = _load_provider_settings_for_write(paths, fallback_settings=fallback_settings)
    target = ScopedModelConfig(provider=provider_name, model=model)
    existing = list(settings.scoped_models)
    if target in existing:
        existing = [item for item in existing if item != target]
    else:
        existing.append(target)
    updated = replace(settings, scoped_models=tuple(existing))
    save_provider_settings(updated, paths)
    return updated


def toggle_saved_scoped_model(
    *,
    provider_name: str,
    model: str,
    paths: BaldricPaths | None = None,
    fallback_settings: ProviderSettings | None = None,
) -> ProviderSettings:
    """Reload settings, toggle one scoped model, persist them, and return them."""
    settings = _load_provider_settings_for_write(paths, fallback_settings=fallback_settings)
    provider = settings.get_provider(provider_name)
    if model not in provider.models:
        raise ProviderConfigError(f"Model is not configured: {provider_name}:{model}")

    existing = list(settings.scoped_models)
    target = ScopedModelConfig(provider=provider_name, model=model)
    if target in existing:
        existing = [item for item in existing if item != target]
    else:
        existing.append(target)
    updated = replace(settings, scoped_models=tuple(existing))
    save_provider_settings(updated, paths)
    return updated


def upsert_saved_provider(
    provider: ProviderConfig,
    *,
    set_default: bool = False,
    paths: BaldricPaths | None = None,
    fallback_settings: ProviderSettings | None = None,
) -> ProviderSettings:
    """Reload settings, upsert one provider entry, persist them, and return them."""
    settings = _load_provider_settings_for_write(paths, fallback_settings=fallback_settings)
    updated = upsert_provider(settings, provider, set_default=set_default)
    save_provider_settings(updated, paths)
    return updated


def _load_provider_settings_for_write(
    paths: BaldricPaths | None,
    *,
    fallback_settings: ProviderSettings | None = None,
) -> ProviderSettings:
    """Load the latest on-disk settings, falling back only when no file exists."""
    resolved_paths = paths or BaldricPaths()
    if provider_settings_path(resolved_paths).exists():
        return load_provider_settings(resolved_paths)
    if fallback_settings is not None:
        return fallback_settings
    return load_provider_settings(resolved_paths)


def set_default_provider_model(
    settings: ProviderSettings,
    *,
    provider_name: str,
    model: str,
) -> ProviderSettings:
    """Return settings with the default provider/model preference updated."""
    provider = settings.get_provider(provider_name)
    validate_provider_model(provider, model)
    updated_provider = replace(provider, default_model=model)
    providers = tuple(updated_provider if item.name == provider_name else item for item in settings.providers)
    return ProviderSettings(
        default_provider=provider_name,
        providers=providers,
        scoped_models=settings.scoped_models,
    )


def set_provider_thinking_level(
    settings: ProviderSettings,
    *,
    provider_name: str,
    model: str,
    thinking_level: ThinkingLevel,
) -> ProviderSettings:
    """Return settings with a remembered thinking level for one provider/model."""
    provider = settings.get_provider(provider_name)
    validate_provider_model(provider, model)
    normalized = normalize_thinking_level(thinking_level)
    available = provider_thinking_levels(provider, model=model)
    if normalized not in available:
        modes = ", ".join(available) or "none"
        raise ProviderConfigError(
            f"Thinking mode {normalized} is not available for "
            f"{provider_name}:{model}. Available modes: {modes}"
        )
    updated_provider = replace(
        provider,
        thinking_defaults={**provider.thinking_defaults, model: normalized},
    )
    providers = tuple(updated_provider if item.name == provider_name else item for item in settings.providers)
    return ProviderSettings(
        default_provider=settings.default_provider,
        providers=providers,
        scoped_models=settings.scoped_models,
    )


def upsert_openai_compatible_provider(
    settings: ProviderSettings,
    provider: OpenAICompatibleProviderConfig,
    *,
    set_default: bool = False,
) -> ProviderSettings:
    """Return settings with an OpenAI-compatible provider added or replaced."""
    return upsert_provider(settings, provider, set_default=set_default)


def upsert_provider(
    settings: ProviderSettings,
    provider: ProviderConfig,
    *,
    set_default: bool = False,
) -> ProviderSettings:
    """Return settings with a provider added or replaced."""
    providers_by_name = {item.name: item for item in settings.providers}
    builtin_names = {entry.name for entry in BUILTIN_PROVIDER_CATALOG}
    if provider.name in providers_by_name and provider.name in builtin_names:
        provider = _merge_provider_config(providers_by_name[provider.name], provider)
    providers_by_name[provider.name] = provider
    default_provider = provider.name if set_default else settings.default_provider
    providers = tuple(providers_by_name[name] for name in sorted(providers_by_name))
    updated = ProviderSettings(
        default_provider=default_provider,
        providers=providers,
        scoped_models=settings.scoped_models,
    )
    updated.get_provider(default_provider)
    return updated


def _with_builtin_catalog_models(
    settings: ProviderSettings,
    *,
    paths: BaldricPaths | None = None,
) -> ProviderSettings:
    """Return settings with the current provider catalog merged in."""
    catalog_configs = {config.name: config for config in _effective_provider_configs(paths)}
    providers = tuple(
        _merge_provider_config(provider, catalog_configs[provider.name])
        if provider.name in catalog_configs
        else provider
        for provider in settings.providers
    )
    providers = _append_catalog_providers(providers, catalog_configs, paths=paths)
    default_provider = settings.default_provider
    if default_provider not in {provider.name for provider in providers}:
        default_provider = providers[0].name if providers else DEFAULT_PROVIDER_NAME
    return ProviderSettings(
        default_provider=default_provider,
        providers=providers,
        scoped_models=settings.scoped_models,
    )


def _migrate_legacy_provider_settings(
    settings: ProviderSettings,
    *,
    paths: BaldricPaths,
) -> ProviderSettings:
    """Move legacy full provider records onto catalog-owned definitions.

    Built-in and user-catalog provider capabilities come exclusively from the
    current effective catalog. Legacy records contribute only runtime
    preferences. Providers absent from the catalog remain intact so the
    migration can persist them as custom catalog entries.
    """
    catalog_configs = {config.name: config for config in _effective_provider_configs(paths)}
    providers: list[ProviderConfig] = []
    for legacy in settings.providers:
        catalog_provider = catalog_configs.get(legacy.name)
        if catalog_provider is None:
            providers.append(legacy)
            continue
        preferences = _provider_preference_to_json(legacy)
        if legacy.default_model not in catalog_provider.models:
            preferences.pop("default_model")
        preferences["thinking_defaults"] = {
            model: level
            for model, level in legacy.thinking_defaults.items()
            if model in catalog_provider.models
            and level in provider_thinking_levels(catalog_provider, model=model)
        }
        providers.append(_apply_provider_preference(catalog_provider, preferences))

    merged = _append_catalog_providers(tuple(providers), catalog_configs, paths=paths)
    names = {provider.name for provider in merged}
    default_provider = settings.default_provider
    if default_provider not in names:
        default_provider = merged[0].name if merged else DEFAULT_PROVIDER_NAME
    return ProviderSettings(
        default_provider=default_provider,
        providers=merged,
        scoped_models=tuple(
            scoped
            for scoped in settings.scoped_models
            if scoped.provider in names
            and scoped.model
            in next(provider.models for provider in merged if provider.name == scoped.provider)
        ),
    )


def _save_migrated_provider_settings(settings: ProviderSettings, *, paths: BaldricPaths) -> None:
    """Persist one legacy migration after creating its required recovery backup."""
    path = provider_settings_path(paths)
    _backup_provider_settings(path, strict=True)
    catalog_names = {entry.name for entry in effective_catalog(paths)}
    custom_entries = [
        _catalog_entry_from_provider(provider)
        for provider in settings.providers
        if provider.name not in catalog_names
    ]
    if custom_entries:
        _provider_config_module().save_user_catalog_entries(custom_entries, paths=paths)
    _provider_config_module()._write_provider_settings(settings, path=path, backup=False)


def _backup_provider_settings(path: Path, *, strict: bool) -> None:
    """Copy existing settings to the recovery path, optionally requiring success."""
    if not path.exists():
        return
    if strict:
        _provider_config_module().copy2(path, path.with_suffix(path.suffix + ".bak"))
        return
    with suppress(OSError):
        _provider_config_module().copy2(path, path.with_suffix(path.suffix + ".bak"))


def _write_provider_settings(
    settings: ProviderSettings,
    *,
    path: Path,
    backup: bool,
) -> None:
    """Atomically write preferences, optionally retaining the previous file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if backup:
        _backup_provider_settings(path, strict=False)
    _atomic_write_text(path, dumps(settings.to_json(), indent=2, sort_keys=True) + "\n")


_EFFECTIVE_PROVIDER_CONFIGS: tuple[tuple[ProviderCatalogEntry, ...], tuple[ProviderConfig, ...]] | None = None


def _atomic_write_text(path: Path, text: str) -> None:
    """Write text through a sibling temp file and atomically replace the target."""
    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            "w",
            dir=path.parent,
            encoding="utf-8",
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(text)
            temp_file.flush()
        temp_path.replace(path)
    except Exception:
        if temp_path is not None:
            with suppress(OSError):
                temp_path.unlink()
        raise
