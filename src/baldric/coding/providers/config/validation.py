"""Durable provider configuration for Baldric coding sessions."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

from baldric.ai.env import (
    DEFAULT_OPENAI_COMPATIBLE_MAX_RETRIES,
    DEFAULT_OPENAI_COMPATIBLE_MAX_RETRY_DELAY_SECONDS,
    DEFAULT_OPENAI_COMPATIBLE_TIMEOUT_SECONDS,
)
from baldric.coding.config.paths import BaldricPaths
from baldric.coding.context.thinking import (
    ThinkingLevel,
    ThinkingParameter,
    normalize_thinking_level,
    normalize_thinking_levels,
)
from baldric.coding.providers.catalog import (
    ModelCostTier,
    ProviderApi,
)
from baldric.coding.providers.config.catalog import _effective_provider_configs
from baldric.coding.providers.config.models import (
    PROVIDER_SETTINGS_SCHEMA_VERSION,
    AnthropicProviderConfig,
    OpenAICodexProviderConfig,
    OpenAICompatibleProviderConfig,
    ProviderConfig,
    ProviderConfigError,
    ProviderModelMetadata,
    ProviderSettings,
    ScopedModelConfig,
    _default_api_for_kind,
    _reject_codex_legacy_compat,
    _validate_inference_providers,
    _validate_json_value,
    _validate_runtime_cost_tiers,
    validate_huggingface_inference_provider,
)


def provider_settings_from_json(
    data: dict[str, Any],
    *,
    paths: BaldricPaths | None = None,
) -> ProviderSettings:
    """Parse provider preferences from JSON-compatible data.

    The current providers.json shape stores runtime preferences under
    provider_preferences. The older providers[] shape is still accepted for
    migration and compatibility; saves rewrite it to provider_preferences and
    move custom provider definitions to catalog.toml.
    """
    schema_version = data.get("schema_version")
    if schema_version not in (None, PROVIDER_SETTINGS_SCHEMA_VERSION):
        raise ProviderConfigError(f"Unsupported provider settings schema_version: {schema_version!r}")
    default_provider = _string(data.get("default_provider"), "default_provider")
    scoped_models = _scoped_models_from_json(data.get("scoped_models"))
    if "provider_preferences" in data:
        providers = _providers_with_preferences(
            data.get("provider_preferences"),
            paths=paths,
        )
        return ProviderSettings(
            default_provider=default_provider,
            providers=providers,
            scoped_models=scoped_models,
        )

    providers_data = data.get("providers")
    if not isinstance(providers_data, list) or not providers_data:
        raise ProviderConfigError("Provider settings must include provider_preferences or legacy providers")
    providers = tuple(_provider_from_json(item) for item in providers_data)
    names = [provider.name for provider in providers]
    if len(set(names)) != len(names):
        raise ProviderConfigError("Provider names must be unique")
    return ProviderSettings(
        default_provider=default_provider,
        providers=providers,
        scoped_models=scoped_models,
    )


def _providers_with_preferences(
    value: object,
    *,
    paths: BaldricPaths | None,
) -> tuple[ProviderConfig, ...]:
    if not isinstance(value, dict):
        raise ProviderConfigError("Provider settings field must be an object: provider_preferences")
    catalog_configs = {provider.name: provider for provider in _effective_provider_configs(paths)}
    providers = []
    seen: set[str] = set()
    for name, preference_data in value.items():
        if not isinstance(name, str) or not name.strip():
            raise ProviderConfigError("Provider preference names must be non-empty strings")
        provider_name = name.strip()
        if provider_name in seen:
            raise ProviderConfigError("Provider preference names must be unique")
        if provider_name not in catalog_configs:
            # Preferences contain runtime overrides, not provider definitions. A
            # catalog entry may be removed independently, leaving an orphaned
            # preference behind. Ignore it so one stale entry cannot prevent Baldric
            # from starting or running `baldric setup` to register it again.
            continue
        providers.append(
            _apply_provider_preference(
                catalog_configs[provider_name],
                preference_data,
            )
        )
        seen.add(provider_name)
    return tuple(providers)


def _apply_provider_preference(
    provider: ProviderConfig,
    value: object,
) -> ProviderConfig:
    if not isinstance(value, dict):
        raise ProviderConfigError("Provider preference entries must be objects")
    # Provider preferences are user-level state shared across Baldric versions.
    # Ignore options introduced by newer versions while continuing to validate
    # every recognized option below.
    default_model = (
        _string(value.get("default_model"), f"provider_preferences.{provider.name}.default_model")
        if "default_model" in value
        else provider.default_model
    )
    if default_model not in provider.models:
        default_model = provider.default_model
    headers = (
        _string_dict(value.get("headers"), f"provider_preferences.{provider.name}.headers")
        if "headers" in value
        else provider.headers
    )
    timeout_seconds = (
        _positive_float(
            value.get("timeout_seconds"),
            f"provider_preferences.{provider.name}.timeout_seconds",
        )
        if "timeout_seconds" in value
        else provider.timeout_seconds
    )
    max_retries = (
        _non_negative_int(
            value.get("max_retries"),
            f"provider_preferences.{provider.name}.max_retries",
        )
        if "max_retries" in value
        else provider.max_retries
    )
    max_retry_delay_seconds = (
        _non_negative_float(
            value.get("max_retry_delay_seconds"),
            f"provider_preferences.{provider.name}.max_retry_delay_seconds",
        )
        if "max_retry_delay_seconds" in value
        else provider.max_retry_delay_seconds
    )
    thinking_defaults = (
        _thinking_defaults_dict(
            value.get("thinking_defaults"),
            provider,
            f"provider_preferences.{provider.name}.thinking_defaults",
            ignore_unknown_models=True,
            ignore_unavailable=True,
        )
        if "thinking_defaults" in value
        else provider.thinking_defaults
    )
    if isinstance(provider, OpenAICompatibleProviderConfig):
        inference_providers = (
            _inference_providers_dict(
                value.get("inference_providers"),
                provider,
                f"provider_preferences.{provider.name}.inference_providers",
            )
            if "inference_providers" in value
            else provider.inference_providers
        )
        default_inference_provider = (
            _default_inference_provider(
                value.get("default_inference_provider"),
                provider,
                f"provider_preferences.{provider.name}.default_inference_provider",
            )
            if "default_inference_provider" in value
            else provider.default_inference_provider
        )
        return replace(
            provider,
            default_model=default_model,
            headers=headers,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            max_retry_delay_seconds=max_retry_delay_seconds,
            thinking_defaults=thinking_defaults,
            inference_providers=inference_providers,
            default_inference_provider=default_inference_provider,
        )
    return replace(
        provider,
        default_model=default_model,
        headers=headers,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        max_retry_delay_seconds=max_retry_delay_seconds,
        thinking_defaults=thinking_defaults,
    )


def _inference_providers_dict(
    value: object,
    provider: OpenAICompatibleProviderConfig,
    field_name: str,
) -> dict[str, str]:
    routes = _string_dict(value, field_name)
    routes = {model: route.strip() for model, route in routes.items() if model in provider.models}
    _validate_inference_providers(provider.name, provider.models, routes)
    return routes


def _default_inference_provider(
    value: object,
    provider: OpenAICompatibleProviderConfig,
    field_name: str,
) -> str | None:
    """Parse a provider-wide Hugging Face route; an explicit null opts out."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ProviderConfigError(f"{field_name} must be a non-empty string or null")
    if provider.name != "huggingface":
        raise ProviderConfigError("default_inference_provider is only supported for the huggingface provider")
    return validate_huggingface_inference_provider(value)


def _thinking_defaults_dict(
    value: object,
    provider: ProviderConfig,
    field_name: str,
    *,
    ignore_unknown_models: bool = False,
    ignore_unavailable: bool = False,
) -> dict[str, ThinkingLevel]:
    from baldric.coding.providers.config.selection import (
        provider_thinking_levels,
        validate_provider_model,
    )

    raw = _raw_thinking_defaults_dict(value, field_name)
    if ignore_unknown_models:
        raw = {model: level for model, level in raw.items() if model in provider.models}
    valid: dict[str, ThinkingLevel] = {}
    for model, thinking_level in raw.items():
        validate_provider_model(provider, model)
        available = provider_thinking_levels(provider, model=model)
        if thinking_level not in available:
            if ignore_unavailable:
                continue
            modes = ", ".join(available) or "none"
            raise ProviderConfigError(
                f"Provider thinking default {thinking_level} is not available for "
                f"{provider.name}:{model}. Available modes: {modes}"
            )
        valid[model] = thinking_level
    return valid


def _raw_thinking_defaults_dict(value: object, field_name: str) -> dict[str, ThinkingLevel]:
    if not isinstance(value, dict):
        raise ProviderConfigError(f"Provider field must be a thinking mode object: {field_name}")
    defaults: dict[str, ThinkingLevel] = {}
    for key, item in value.items():
        model = _string(key, field_name)
        thinking_level = _optional_thinking_level(item, f"{field_name}.{model}")
        if thinking_level is None:
            raise ProviderConfigError(f"Provider field must be a thinking mode: {field_name}")
        defaults[model] = thinking_level
    return defaults


def _scoped_models_from_json(value: object) -> tuple[ScopedModelConfig, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ProviderConfigError("Provider settings field must be a list: scoped_models")
    scoped: list[ScopedModelConfig] = []
    seen: set[tuple[str, str]] = set()
    for item in value:
        if not isinstance(item, dict):
            raise ProviderConfigError("Provider scoped_models entries must be objects")
        provider = _string(item.get("provider"), "scoped_models.provider")
        model = _string(item.get("model"), "scoped_models.model")
        key = (provider, model)
        if key not in seen:
            scoped.append(ScopedModelConfig(provider=provider, model=model))
            seen.add(key)
    return tuple(scoped)


def _provider_from_json(data: object) -> ProviderConfig:
    if not isinstance(data, dict):
        raise ProviderConfigError("Provider entries must be JSON objects")
    provider_type = _string(data.get("type"), "providers[].type")
    if provider_type not in {
        "openai-compatible",
        "anthropic",
        "openai-codex",
        "google-generative-ai",
        "mistral-conversations",
    }:
        raise ProviderConfigError(f"Unsupported provider type: {provider_type}")
    name = _string(data.get("name"), "providers[].name")
    base_url = _string(data.get("base_url"), f"providers[{name}].base_url").rstrip("/")
    api = _optional_provider_api(data.get("api"), f"providers[{name}].api")
    api_key_env = _string(data.get("api_key_env"), f"providers[{name}].api_key_env")
    credential_name = _optional_string(data.get("credential_name"), f"providers[{name}].credential_name")
    models = _string_tuple(data.get("models"), f"providers[{name}].models")
    default_model = _string(data.get("default_model"), f"providers[{name}].default_model")
    context_windows = _context_window_dict(
        data.get("context_windows", {}), f"providers[{name}].context_windows"
    )
    headers = _string_dict(data.get("headers", {}), f"providers[{name}].headers")
    compat = _json_dict(data.get("compat", {}), f"providers[{name}].compat")
    model_metadata = _model_metadata_dict(
        data.get("model_metadata", {}),
        models,
        f"providers[{name}].model_metadata",
    )
    timeout_seconds = _positive_float(
        data.get("timeout_seconds", DEFAULT_OPENAI_COMPATIBLE_TIMEOUT_SECONDS),
        f"providers[{name}].timeout_seconds",
    )
    max_retries = _non_negative_int(
        data.get("max_retries", DEFAULT_OPENAI_COMPATIBLE_MAX_RETRIES),
        f"providers[{name}].max_retries",
    )
    max_retry_delay_seconds = _non_negative_float(
        data.get(
            "max_retry_delay_seconds",
            DEFAULT_OPENAI_COMPATIBLE_MAX_RETRY_DELAY_SECONDS,
        ),
        f"providers[{name}].max_retry_delay_seconds",
    )
    thinking_levels = _optional_thinking_levels(
        data.get("thinking_levels"), f"providers[{name}].thinking_levels"
    )
    thinking_models = _optional_string_tuple(
        data.get("thinking_models"), f"providers[{name}].thinking_models"
    )
    thinking_default = _optional_thinking_level(
        data.get("thinking_default"), f"providers[{name}].thinking_default"
    )
    thinking_parameter = _optional_thinking_parameter(
        data.get("thinking_parameter"), f"providers[{name}].thinking_parameter"
    )
    thinking_defaults = _raw_thinking_defaults_dict(
        data.get("thinking_defaults", {}), f"providers[{name}].thinking_defaults"
    )
    if default_model not in models:
        models = (*models, default_model)
    if provider_type == "anthropic":
        return AnthropicProviderConfig(
            name=name,
            base_url=base_url,
            api=api or "anthropic-messages",
            api_key_env=api_key_env,
            credential_name=credential_name,
            models=models,
            default_model=default_model,
            context_windows=context_windows,
            headers=headers,
            compat=compat,
            model_metadata=model_metadata,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            max_retry_delay_seconds=max_retry_delay_seconds,
            thinking_levels=thinking_levels,
            thinking_models=thinking_models,
            thinking_default=thinking_default,
            thinking_parameter=thinking_parameter,
            thinking_defaults=thinking_defaults,
        )
    if provider_type == "openai-codex":
        _reject_codex_legacy_compat(compat)
        return OpenAICodexProviderConfig(
            name=name,
            base_url=base_url,
            api_key_env=api_key_env,
            credential_name=credential_name,
            models=models,
            default_model=default_model,
            context_windows=context_windows,
            headers=headers,
            model_metadata=model_metadata,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            max_retry_delay_seconds=max_retry_delay_seconds,
            thinking_levels=thinking_levels,
            thinking_models=thinking_models,
            thinking_default=thinking_default,
            thinking_parameter=thinking_parameter,
            thinking_defaults=thinking_defaults,
        )
    return OpenAICompatibleProviderConfig(
        name=name,
        base_url=base_url,
        api=api or _default_api_for_kind(provider_type),
        api_key_env=api_key_env,
        credential_name=credential_name,
        models=models,
        default_model=default_model,
        context_windows=context_windows,
        headers=headers,
        compat=compat,
        model_metadata=model_metadata,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        max_retry_delay_seconds=max_retry_delay_seconds,
        thinking_levels=thinking_levels,
        thinking_models=thinking_models,
        thinking_default=thinking_default,
        thinking_parameter=thinking_parameter,
        thinking_defaults=thinking_defaults,
    )


def _optional_provider_api(value: object, field_name: str) -> ProviderApi | None:
    if value is None:
        return None
    if value in {
        "openai-completions",
        "openai-responses",
        "anthropic-messages",
        "openai-codex-responses",
        "google-generative-ai",
        "mistral-conversations",
    }:
        return cast(ProviderApi, value)
    raise ProviderConfigError(f"Provider field has unsupported API: {field_name}")


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ProviderConfigError(f"Provider field must be a non-empty string: {field_name}")
    return value.strip()


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProviderConfigError(f"Provider field must be a non-empty string: {field_name}")
    return value.strip()


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ProviderConfigError(f"Provider field must be a non-empty string list: {field_name}")
    items = tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    if len(items) != len(value):
        raise ProviderConfigError(f"Provider field must be a string list: {field_name}")
    return items


def _optional_string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ProviderConfigError(f"Provider field must be a string list: {field_name}")
    items = tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    if len(items) != len(value):
        raise ProviderConfigError(f"Provider field must be a string list: {field_name}")
    return items


def _optional_thinking_levels(
    value: object,
    field_name: str,
) -> tuple[ThinkingLevel, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ProviderConfigError(f"Provider field must be a thinking mode list: {field_name}")
    try:
        return normalize_thinking_levels(value)
    except ValueError as exc:
        raise ProviderConfigError(str(exc)) from exc


def _optional_thinking_level(value: object, field_name: str) -> ThinkingLevel | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProviderConfigError(f"Provider field must be a thinking mode: {field_name}")
    try:
        return normalize_thinking_level(value)
    except ValueError as exc:
        raise ProviderConfigError(str(exc)) from exc


def _optional_thinking_parameter(
    value: object,
    field_name: str,
) -> ThinkingParameter | None:
    if value is None:
        return None
    if value == "reasoning_effort":
        return "reasoning_effort"
    if value == "reasoning.effort":
        return "reasoning.effort"
    if value == "anthropic.thinking":
        return "anthropic.thinking"
    raise ProviderConfigError(
        f"Provider field must be reasoning_effort, reasoning.effort, or anthropic.thinking: {field_name}"
    )


def _string_dict(value: object, field_name: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ProviderConfigError(f"Provider field must be a string object: {field_name}")
    items: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ProviderConfigError(f"Provider field must be a string object: {field_name}")
        if not isinstance(item, str) or not item.strip():
            raise ProviderConfigError(f"Provider field must be a string object: {field_name}")
        items[key.strip()] = item.strip()
    return items


def _json_dict(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProviderConfigError(f"Provider field must be an object: {field_name}")
    items: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ProviderConfigError(f"Provider field must have string keys: {field_name}")
        _validate_json_value(item, f"{field_name}.{key}")
        items[key.strip()] = item
    return items


def _model_metadata_dict(
    value: object,
    models: tuple[str, ...],
    field_name: str,
) -> dict[str, ProviderModelMetadata]:
    if not isinstance(value, dict):
        raise ProviderConfigError(f"Provider field must be an object: {field_name}")
    model_names = set(models)
    items: dict[str, ProviderModelMetadata] = {}
    for key, item in value.items():
        model = _string(key, field_name)
        if model not in model_names:
            raise ProviderConfigError(f"Provider model_metadata key is not in models: {model}")
        if not isinstance(item, dict):
            raise ProviderConfigError(f"Provider model_metadata entries must be objects: {field_name}")
        items[model] = ProviderModelMetadata(
            name=_optional_string(item.get("name"), f"{field_name}.{model}.name"),
            api=_optional_provider_api(item.get("api"), f"{field_name}.{model}.api"),
            base_url=_optional_string(item.get("base_url"), f"{field_name}.{model}.base_url"),
            reasoning=_optional_bool(item.get("reasoning"), f"{field_name}.{model}.reasoning"),
            input=_optional_string_tuple(item.get("input"), f"{field_name}.{model}.input"),
            cost=_float_dict(item.get("cost", {}), f"{field_name}.{model}.cost"),
            cost_tiers=_cost_tiers(item.get("cost_tiers", []), f"{field_name}.{model}.cost_tiers"),
            context_window=_optional_positive_int(
                item.get("context_window"), f"{field_name}.{model}.context_window"
            ),
            max_tokens=_optional_positive_int(item.get("max_tokens"), f"{field_name}.{model}.max_tokens"),
            headers=_string_dict(item.get("headers", {}), f"{field_name}.{model}.headers"),
            compat=_json_dict(item.get("compat", {}), f"{field_name}.{model}.compat"),
            thinking_level_map=_thinking_level_map_dict(
                item.get("thinking_level_map", {}),
                f"{field_name}.{model}.thinking_level_map",
            ),
        )
    return items


def _cost_tiers(value: object, field_name: str) -> tuple[ModelCostTier, ...]:
    if not isinstance(value, list):
        raise ProviderConfigError(f"Provider field must be an array: {field_name}")
    tiers: list[ModelCostTier] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ProviderConfigError(f"Provider cost tiers must be objects: {field_name}")
        tier_field = f"{field_name}.{index}"
        allowed = {
            "max_input_tokens",
            "input",
            "output",
            "cacheRead",
            "cacheWrite",
            "cacheWrite1h",
        }
        if set(item) - allowed:
            raise ProviderConfigError(f"Provider cost tier has unknown fields: {tier_field}")
        cost = {
            key: _non_negative_float(item.get(key), f"{tier_field}.{key}")
            for key in ("input", "output", "cacheRead", "cacheWrite")
        }
        if item.get("cacheWrite1h") is not None:
            cost["cacheWrite1h"] = _non_negative_float(item.get("cacheWrite1h"), f"{tier_field}.cacheWrite1h")
        tiers.append(
            ModelCostTier(
                max_input_tokens=_optional_positive_int(
                    item.get("max_input_tokens"), f"{tier_field}.max_input_tokens"
                ),
                cost=cost,
            )
        )
    result = tuple(tiers)
    _validate_runtime_cost_tiers(result)
    return result


def _thinking_level_map_dict(
    value: object,
    field_name: str,
) -> dict[ThinkingLevel, str | None]:
    if not isinstance(value, dict):
        raise ProviderConfigError(f"Provider field must be an object: {field_name}")
    items: dict[ThinkingLevel, str | None] = {}
    for key, item in value.items():
        level = _optional_thinking_level(key, field_name)
        if level is None:
            raise ProviderConfigError(f"Provider field must be a thinking mode: {field_name}")
        if item is not None and (not isinstance(item, str) or not item.strip()):
            raise ProviderConfigError(f"Provider field values must be strings or null: {field_name}")
        items[level] = item.strip() if isinstance(item, str) else None
    return items


def _float_dict(value: object, field_name: str) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ProviderConfigError(f"Provider field must be a number object: {field_name}")
    items: dict[str, float] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ProviderConfigError(f"Provider field must be a number object: {field_name}")
        if not isinstance(item, int | float) or isinstance(item, bool) or item < 0:
            raise ProviderConfigError(f"Provider field values must be non-negative: {field_name}")
        items[key.strip()] = float(item)
    return items


def _optional_bool(value: object, field_name: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ProviderConfigError(f"Provider field must be a boolean: {field_name}")
    return value


def _optional_positive_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ProviderConfigError(f"Provider field must be a positive integer: {field_name}")
    return value


def _context_window_dict(value: object, field_name: str) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ProviderConfigError(f"Provider field must be an integer object: {field_name}")
    items: dict[str, int] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ProviderConfigError(f"Provider field must be an integer object: {field_name}")
        if not isinstance(item, int) or isinstance(item, bool) or item <= 0:
            raise ProviderConfigError(f"Provider field values must be positive integers: {field_name}")
        items[key.strip()] = item
    return items


def _positive_float(value: object, field_name: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ProviderConfigError(f"Provider field must be a positive number: {field_name}")
    converted = float(value)
    if converted <= 0:
        raise ProviderConfigError(f"Provider field must be greater than 0: {field_name}")
    return converted


def _non_negative_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ProviderConfigError(f"Provider field must be a non-negative integer: {field_name}")
    if value < 0:
        raise ProviderConfigError(f"Provider field must be 0 or greater: {field_name}")
    return value


def _non_negative_float(value: object, field_name: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ProviderConfigError(f"Provider field must be a non-negative number: {field_name}")
    converted = float(value)
    if converted < 0:
        raise ProviderConfigError(f"Provider field must be 0 or greater: {field_name}")
    return converted
